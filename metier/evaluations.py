"""Enregistrement des estimations et regles d'alerte.

Chaque fois qu'un etudiant recoit une nouvelle estimation (import d'un fichier, mise a jour de ses resultats sur
sa fiche), la meme regle s'applique :
  - risque >= 1/6 et aucun dossier ouvert : un dossier de suivi s'ouvre, statut « a contacter », avec une echeance ;
  - dossier deja ouvert et risque en hausse d'au moins 10 points (ou passage en risque eleve) : le dossier est
    signale « a revoir » et la hausse est inscrite dans son journal ;
  - dossier ouvert et risque repasse sous le seuil : c'est inscrit au journal, le conseiller decide de la cloture.
Aucune decision n'est prise automatiquement au-dela de l'ouverture d'un dossier.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pandas as pd
from sqlalchemy import and_, select

import db
from moteur.referentiels import FILIERES
from moteur.scoring import categorie
from .regles import DELAIS, SEUIL_ALERTE, SEUIL_ELEVE, SEUIL_RELANCE

DEVENIRS_TEXTE = {"dropout": "Dropout", "abandon": "Dropout", "graduate": "Graduate", "diplome": "Graduate",
                  "diplômé": "Graduate", "enrolled": "Enrolled", "inscrit": "Enrolled"}


def en_alerte(p: float) -> bool:
    return round(float(p), 3) >= round(SEUIL_ALERTE, 3)


def _entier(v):
    return None if v is None or pd.isna(v) else int(round(float(v)))


def _reel(v):
    return None if v is None or pd.isna(v) else round(float(v), 2)


def colonnes_resume(v: dict) -> dict:
    """Colonnes de l'etudiant tirees de ses valeurs (pour lister sans relire le JSON)."""
    course = _entier(v.get("Course"))
    genre = v.get("Gender")
    return {
        "filiere": FILIERES.get(course, f"Code {course}") if course is not None else None,
        "genre": None if genre is None or pd.isna(genre) else ("Homme" if genre == 1 else "Femme"),
        "age": _reel(v.get("Age at enrollment")),
        "boursier": _entier(v.get("Scholarship holder")), "debiteur": _entier(v.get("Debtor")),
        "frais_a_jour": _entier(v.get("Tuition fees up to date")),
        "note_s1": _reel(v.get("Curricular units 1st sem (grade)")),
        "note_s2": _reel(v.get("Curricular units 2nd sem (grade)")),
        "inscrites_s1": _entier(v.get("Curricular units 1st sem (enrolled)")),
        "validees_s1": _entier(v.get("Curricular units 1st sem (approved)")),
        "inscrites_s2": _entier(v.get("Curricular units 2nd sem (enrolled)")),
        "validees_s2": _entier(v.get("Curricular units 2nd sem (approved)")),
    }


def _ouvrir_dossier(c, etudiant_id, evaluation_id, p, referent_id, utilisateur_id=None, texte=None):
    maintenant = db.maintenant()
    dossier_id = c.execute(db.dossier.insert().values(
        etudiant_id=etudiant_id, statut="a_contacter", conseiller_id=referent_id,
        echeance=(maintenant + timedelta(days=DELAIS["a_contacter"])).date(), ouvert_le=maintenant,
        ouvert_par=utilisateur_id, evaluation_id=evaluation_id, probabilite_ouverture=p, relance=False,
        maj_le=maintenant)).inserted_primary_key[0]
    c.execute(db.action.insert().values(
        dossier_id=dossier_id, utilisateur_id=utilisateur_id, type="ouverture",
        texte=texte or f"Ouverture automatique : risque estimé à {round(100 * p)} %, au-dessus du seuil d'alerte.",
        statut_apres="a_contacter", cree_le=maintenant))
    return dossier_id


def appliquer_regles(c, etudiant_id: int, evaluation_id: int, p_avant: float | None, p: float, referent_id,
                     dossier_ouvert: dict | None, utilisateur_id=None, dernier_clos: dict | None = None) -> str | None:
    """Rend 'ouvert', 'relance' ou None selon l'effet de la nouvelle estimation sur le suivi.
    Apres une cloture, un nouveau dossier ne s'ouvre que si le risque a encore monte d'au moins 10 points :
    un etudiant deja vu en entretien n'est pas re-signale a chaque import pour le meme niveau de risque."""
    maintenant = db.maintenant()
    if dossier_ouvert is None:
        deja_traite = (dernier_clos is not None and dernier_clos["probabilite_cloture"] is not None
                       and p < dernier_clos["probabilite_cloture"] + SEUIL_RELANCE)
        if en_alerte(p) and not deja_traite:
            _ouvrir_dossier(c, etudiant_id, evaluation_id, p, referent_id)
            return "ouvert"
        return None
    if p_avant is not None and abs(p - p_avant) < 0.02:
        return None
    texte = f"Nouvelle estimation : {round(100 * p)} %" + (f" (contre {round(100 * p_avant)} % auparavant)." if p_avant is not None else ".")
    relance = (p - (dossier_ouvert["probabilite_ouverture"] or 0) >= SEUIL_RELANCE
               or (p >= SEUIL_ELEVE > (p_avant if p_avant is not None else 1)))
    if not en_alerte(p):
        texte += " Le risque est repassé sous le seuil d'alerte : le dossier peut être clos si l'accompagnement le permet."
    c.execute(db.action.insert().values(dossier_id=dossier_ouvert["id"], utilisateur_id=utilisateur_id,
                                        type="reevaluation", texte=texte, cree_le=maintenant))
    valeurs = {"maj_le": maintenant}
    if relance and not dossier_ouvert["relance"]:
        valeurs["relance"] = True
    c.execute(db.dossier.update().where(db.dossier.c.id == dossier_ouvert["id"]).values(**valeurs))
    return "relance" if relance else None


def enregistrer_lot(c, moteur, promotion_id: int, df: pd.DataFrame, colonnes: dict, fichier: str | None,
                    utilisateur_id=None) -> dict:
    """Score `df` et enregistre une evaluation par ligne valide. Les etudiants deja connus de la promotion
    (meme matricule) sont mis a jour ; les autres sont crees. Rend le compte rendu de l'import."""
    df = df.reset_index(drop=True)
    valeurs, erreurs = moteur.nettoyer(df)
    valides = valeurs.drop(index=list(erreurs))
    if valides.empty:
        raise ValueError("Aucune ligne exploitable dans le fichier.")
    scores = moteur.scorer_valeurs(valides)
    maintenant = db.maintenant()

    connus = {r["matricule"]: r for r in db.lignes(c.execute(
        select(db.etudiant.c.id, db.etudiant.c.matricule, db.etudiant.c.probabilite, db.etudiant.c.referent_id)
        .where(db.etudiant.c.promotion_id == promotion_id)))}
    ouverts = {r["etudiant_id"]: r for r in db.lignes(c.execute(
        select(db.dossier).join(db.etudiant, db.etudiant.c.id == db.dossier.c.etudiant_id)
        .where(and_(db.etudiant.c.promotion_id == promotion_id, db.dossier.c.statut != "clos"))))}

    clos = {}
    for r in db.lignes(c.execute(
            select(db.dossier).join(db.etudiant, db.etudiant.c.id == db.dossier.c.etudiant_id)
            .where(and_(db.etudiant.c.promotion_id == promotion_id, db.dossier.c.statut == "clos"))
            .order_by(db.dossier.c.clos_le))):
        clos[r["etudiant_id"]] = r  # le plus recent l'emporte

    lot_id = c.execute(db.lot.insert().values(
        promotion_id=promotion_id, fichier=fichier, effectif=len(valides), ignorees=len(erreurs),
        utilisateur_id=utilisateur_id, cree_le=maintenant)).inserted_primary_key[0]

    nouveaux = mis_a_jour = ouverts_compte = relances = 0
    vus = set()
    for i in valides.index:
        v, s = valides.loc[i], scores.loc[i]
        matricule = str(df.at[i, colonnes["reference"]]).strip() if colonnes.get("reference") else ""
        matricule = matricule or f"L{lot_id}-{i + 1:04d}"
        if matricule in vus:
            raise ValueError(f"Le matricule « {matricule} » apparaît plusieurs fois dans le fichier.")
        vus.add(matricule)
        connues = {k: float(x) for k, x in v.items() if not pd.isna(x)}
        resume = colonnes_resume(connues)
        if resume["filiere"] is None and colonnes.get("filiere"):
            resume["filiere"] = str(df.at[i, colonnes["filiere"]]).strip() or None
        devenir = abandon = None
        if colonnes.get("devenir"):
            devenir = DEVENIRS_TEXTE.get(moteur.normaliser(df.at[i, colonnes["devenir"]]))
            abandon = None if devenir is None else int(devenir == "Dropout")
        elif colonnes.get("abandon"):
            abandon = {"1": 1, "1.0": 1, "0": 0, "0.0": 0, "oui": 1, "non": 0}.get(str(df.at[i, colonnes["abandon"]]).strip().lower())
        contact = {k: (str(df.at[i, colonnes[k]]).strip() or None) for k in ("nom", "email", "telephone") if colonnes.get(k)}
        p, p_nw = float(s["probabilite_ml"]), float(s["probabilite_noyau"])
        courant = {"probabilite": p, "probabilite_noyau": p_nw, "categorie": s["categorie_ml"], "moment": s["mode_calcul"],
                   "facteur": s["facteur"], "domaine_facteur": s["domaine_facteur"]}
        existant = connus.get(matricule)
        if existant is None:
            etudiant_id = c.execute(db.etudiant.insert().values(
                promotion_id=promotion_id, matricule=matricule, caracteristiques=json.dumps(connues),
                cree_le=maintenant, maj_le=maintenant, **resume, **contact, **courant)).inserted_primary_key[0]
            nouveaux += 1
            p_avant, referent = None, None
        else:
            etudiant_id, p_avant, referent = existant["id"], existant["probabilite"], existant["referent_id"]
            c.execute(db.etudiant.update().where(db.etudiant.c.id == etudiant_id).values(
                caracteristiques=json.dumps(connues), maj_le=maintenant, **resume, **contact, **courant))
            mis_a_jour += 1
        if devenir is not None or abandon is not None:
            c.execute(db.etudiant.update().where(db.etudiant.c.id == etudiant_id).values(
                devenir_reel=devenir, abandon_reel=abandon, devenir_saisi_le=maintenant))
        evaluation_id = c.execute(db.evaluation.insert().values(
            etudiant_id=etudiant_id, lot_id=lot_id, utilisateur_id=utilisateur_id, moment=s["mode_calcul"],
            probabilite=p, probabilite_noyau=p_nw, categorie=s["categorie_ml"], facteur=s["facteur"],
            domaine_facteur=s["domaine_facteur"], nb_estimees=int(s["nb_estimees"]), caracteristiques=json.dumps(connues),
            modele_version=moteur.version, cree_le=maintenant)).inserted_primary_key[0]
        c.execute(db.etudiant.update().where(db.etudiant.c.id == etudiant_id).values(evaluation_id=evaluation_id))
        effet = appliquer_regles(c, etudiant_id, evaluation_id, p_avant, p, referent, ouverts.get(etudiant_id), utilisateur_id,
                                 clos.get(etudiant_id))
        ouverts_compte += effet == "ouvert"
        relances += effet == "relance"

    c.execute(db.lot.update().where(db.lot.c.id == lot_id).values(
        nouveaux=nouveaux, mis_a_jour=mis_a_jour, alertes_ouvertes=ouverts_compte))
    return {
        "lot_id": lot_id, "cohorte_id": promotion_id, "effectif": len(valides),
        "nouveaux": nouveaux, "mis_a_jour": mis_a_jour, "dossiers_ouverts": ouverts_compte, "relances": relances,
        "erreurs": erreurs, "scores": scores,
    }


def reevaluer(c, moteur, etudiant_id: int, reponses: dict, utilisateur: dict) -> dict:
    """Mise a jour des resultats d'un etudiant depuis sa fiche : les valeurs saisies remplacent les anciennes,
    les autres sont conservees ; une nouvelle estimation est enregistree et la regle d'alerte s'applique."""
    e = db.ligne(c.execute(select(db.etudiant).where(db.etudiant.c.id == etudiant_id)))
    valeurs = json.loads(e["caracteristiques"] or "{}")
    for cle, v in reponses.items():
        if v is None or str(v).strip() == "":
            valeurs.pop(cle, None)
        else:
            valeurs[cle] = v
    resultat = moteur.scorer_un(valeurs)  # leve ValueError si incoherent
    nettoyees, _ = moteur.nettoyer(pd.DataFrame([valeurs]))
    connues = {k: float(x) for k, x in nettoyees.iloc[0].items() if not pd.isna(x)}
    scores = moteur.scorer_valeurs(nettoyees).iloc[0]
    p, p_nw = float(scores["probabilite_ml"]), float(scores["probabilite_noyau"])
    maintenant = db.maintenant()
    evaluation_id = c.execute(db.evaluation.insert().values(
        etudiant_id=etudiant_id, utilisateur_id=utilisateur["id"], moment=scores["mode_calcul"], probabilite=p,
        probabilite_noyau=p_nw, categorie=categorie(p), facteur=scores["facteur"], domaine_facteur=scores["domaine_facteur"],
        nb_estimees=int(scores["nb_estimees"]), caracteristiques=json.dumps(connues), modele_version=moteur.version,
        cree_le=maintenant)).inserted_primary_key[0]
    c.execute(db.etudiant.update().where(db.etudiant.c.id == etudiant_id).values(
        caracteristiques=json.dumps(connues), maj_le=maintenant, evaluation_id=evaluation_id, probabilite=p,
        probabilite_noyau=p_nw, categorie=categorie(p), moment=scores["mode_calcul"], facteur=scores["facteur"],
        domaine_facteur=scores["domaine_facteur"], **colonnes_resume(connues)))
    ouvert = db.ligne(c.execute(select(db.dossier).where(and_(db.dossier.c.etudiant_id == etudiant_id, db.dossier.c.statut != "clos"))))
    dernier_clos = db.ligne(c.execute(select(db.dossier).where(and_(db.dossier.c.etudiant_id == etudiant_id, db.dossier.c.statut == "clos"))
                                      .order_by(db.dossier.c.clos_le.desc())))
    effet = appliquer_regles(c, etudiant_id, evaluation_id, e["probabilite"], p, e["referent_id"], ouvert, utilisateur["id"],
                             dernier_clos)
    return {"evaluation_id": evaluation_id, "probabilite": round(p, 3), "effet": effet, "resultat": resultat}
