"""API des promotions (suivi de cohorte) et des etudiants (fiche, mise a jour, devenir reel)."""
import csv
import io
import json
from functools import lru_cache

import numpy as np
from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import and_, delete, func, select

import db
from auth import interdit_en_demo, mode_demo, connexion_requise, role_requis, utilisateur_courant
from metier import dossiers as suivi
from metier.evaluations import reevaluer
from metier.journal import tracer
from metier.regles import MOTIFS_CLOTURE, STATUTS, TYPES_ACTION, TYPES_AUTOMATIQUES
from moteur import fiabilite
from moteur.conseils import generer_conseils
from moteur.referentiels import CHAMPS_FORMULAIRE, CHAMPS_OUI_NON, DEVENIRS, FILIERES, LIBELLES_CHAMPS, SEUIL_ALERTE
from moteur.scoring import categorie

bp = Blueprint("api_cohortes", __name__, url_prefix="/api/cohortes")


@lru_cache(maxsize=1)
def references_jeu_de_test() -> frozenset:
    with open(db.RACINE / "data" / db.FICHIER_JEU_DE_TEST, encoding="utf-8", newline="") as f:
        return frozenset(ligne["Reference"] for ligne in csv.DictReader(f))


def lire_promotion(c, promotion_id):
    return db.ligne(c.execute(
        select(db.promotion, func.count(db.etudiant.c.id).label("effectif"), func.max(db.etudiant.c.maj_le).label("derniere_maj"))
        .select_from(db.promotion.outerjoin(db.etudiant, db.etudiant.c.promotion_id == db.promotion.c.id))
        .where(db.promotion.c.id == promotion_id).group_by(db.promotion.c.id)))


def lister_promotions(c):
    return db.lignes(c.execute(
        select(db.promotion, func.count(db.etudiant.c.id).label("effectif"), func.max(db.etudiant.c.maj_le).label("derniere_maj"))
        .select_from(db.promotion.outerjoin(db.etudiant, db.etudiant.c.promotion_id == db.promotion.c.id))
        .group_by(db.promotion.c.id).order_by(db.promotion.c.id)))


def lignes_promotion(c, promotion_id):
    conseiller = db.utilisateur.alias("conseiller")
    requete = (
        select(db.etudiant.c.id, db.etudiant.c.matricule.label("reference"), db.etudiant.c.nom, db.etudiant.c.filiere,
               db.etudiant.c.genre, db.etudiant.c.age, db.etudiant.c.boursier, db.etudiant.c.debiteur,
               db.etudiant.c.frais_a_jour, db.etudiant.c.note_s1, db.etudiant.c.note_s2, db.etudiant.c.inscrites_s1,
               db.etudiant.c.validees_s1, db.etudiant.c.inscrites_s2, db.etudiant.c.validees_s2, db.etudiant.c.facteur,
               db.etudiant.c.domaine_facteur, db.etudiant.c.devenir_reel, db.etudiant.c.abandon_reel,
               db.etudiant.c.probabilite_noyau.label("p_noyau"), db.etudiant.c.probabilite.label("p_ml"),
               db.etudiant.c.moment.label("mode"), db.dossier.c.id.label("dossier_id"), db.dossier.c.statut.label("dossier_statut"),
               db.dossier.c.echeance, db.dossier.c.relance, conseiller.c.nom.label("conseiller"))
        .select_from(db.etudiant
                     .outerjoin(db.dossier, and_(db.dossier.c.etudiant_id == db.etudiant.c.id, db.dossier.c.statut != "clos"))
                     .outerjoin(conseiller, conseiller.c.id == db.dossier.c.conseiller_id))
        .where(db.etudiant.c.promotion_id == promotion_id).order_by(db.etudiant.c.id))
    sortie = []
    for l in db.lignes(c.execute(requete)):
        l["c_noyau"], l["c_ml"] = categorie(l["p_noyau"]), categorie(l["p_ml"])
        l["echeance"] = l["echeance"].isoformat() if l["echeance"] else None
        sortie.append(l)
    return sortie


@bp.get("")
@connexion_requise
def lister():
    with db.connexion() as c:
        return jsonify([{**p, "cree_le": p["cree_le"].isoformat(), "derniere_maj": p["derniere_maj"].isoformat() if p["derniere_maj"] else None}
                        for p in lister_promotions(c)])


@bp.get("/<int:cohorte_id>")
@connexion_requise
def lire(cohorte_id):
    with db.connexion() as c:
        promo = lire_promotion(c, cohorte_id)
        if promo is None:
            return jsonify({"erreur": "Promotion introuvable."}), 404
        lignes = lignes_promotion(c, cohorte_id)
    etiquetees = [l for l in lignes if l["abandon_reel"] is not None]
    metriques = {}
    if len(etiquetees) >= 30:
        metriques = current_app.moteur.metriques(np.array([l["abandon_reel"] for l in etiquetees]),
                                                 np.array([l["p_noyau"] for l in etiquetees]),
                                                 np.array([l["p_ml"] for l in etiquetees]))
        if metriques:
            metriques["effectif"] = len(etiquetees)
    est_test = len(lignes) == len(references_jeu_de_test()) and {l["reference"] for l in lignes} == references_jeu_de_test()
    promo = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in promo.items()}
    return jsonify({"cohorte": promo, "lignes": lignes, "metriques": metriques,
                    "reference": current_app.moteur.valeurs_reference() if est_test else None})


@bp.post("/jeu-de-test")
@role_requis("responsable", "admin")
def charger_jeu_de_test():
    return jsonify({"cohorte_id": current_app.charger_jeu_de_test()})


@bp.delete("/<int:cohorte_id>")
@role_requis("admin")
def supprimer(cohorte_id):
    with db.connexion() as c:
        promo = db.ligne(c.execute(select(db.promotion).where(db.promotion.c.id == cohorte_id)))
        if promo is None:
            return jsonify({"erreur": "Promotion introuvable."}), 404
        if mode_demo() and promo["origine"] == "demonstration":
            return jsonify({"erreur": "Cette promotion de démonstration est partagée et ne peut pas être supprimée."}), 403
        c.execute(delete(db.promotion).where(db.promotion.c.id == cohorte_id))
        tracer(c, utilisateur_courant(), "suppression_promotion", "promotion", cohorte_id, {"nom": promo["nom"]})
    return jsonify({"ok": True})


@bp.post("/vider")
@role_requis("admin")
@interdit_en_demo
def vider():
    with db.connexion() as c:
        c.execute(delete(db.promotion))
        tracer(c, utilisateur_courant(), "vidage_base")
    return jsonify({"ok": True})


@bp.get("/<int:cohorte_id>/export.csv")
@connexion_requise
def exporter(cohorte_id):
    """La file d'accompagnement d'une promotion, classee par risque, pour un tableur."""
    with db.connexion() as c:
        promo = lire_promotion(c, cohorte_id)
        if promo is None:
            return jsonify({"erreur": "Promotion introuvable."}), 404
        lignes = sorted(lignes_promotion(c, cohorte_id), key=lambda l: (-l["p_ml"], l["id"]))
        tracer(c, utilisateur_courant(), "export", "promotion", cohorte_id, {"lignes": len(lignes)})
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(["Rang", "Matricule", "Nom", "Filière", "Risque (%)", "Niveau", "En alerte", "Facteur principal",
                "Statut du dossier", "Conseiller", "Échéance"])
    for rang, l in enumerate(lignes, start=1):
        w.writerow([rang, l["reference"], l["nom"] or "", l["filiere"] or "", f"{100 * l['p_ml']:.1f}".replace(".", ","),
                    {"eleve": "Élevé", "moyen": "Moyen", "faible": "Faible"}[l["c_ml"]],
                    "Oui" if round(l["p_ml"], 3) >= round(SEUIL_ALERTE, 3) else "Non", l["facteur"] or "",
                    STATUTS.get(l["dossier_statut"], ""), l["conseiller"] or "", l["echeance"] or ""])
    nom = "".join(ch if ch.isalnum() else "_" for ch in promo["nom"])[:60]
    return Response("﻿" + sortie.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=file_accompagnement_{nom}.csv"})


# ---------------------------------------------------------------- fiche d'un etudiant
bp_etudiants = Blueprint("api_etudiants", __name__, url_prefix="/api/etudiants")


def _profil(valeurs):
    profil = []
    for champ in CHAMPS_FORMULAIRE:
        v = valeurs.get(champ)
        if v is None:
            affichee = None
        elif champ in CHAMPS_OUI_NON:
            affichee = "Oui" if v == 1 else "Non"
        elif champ == "Course":
            affichee = FILIERES.get(int(v), f"Code {int(v)}")
        else:
            affichee = int(v) if float(v).is_integer() else round(v, 2)
        profil.append({"variable": LIBELLES_CHAMPS[champ], "champ": champ, "valeur": affichee, "brute": v,
                       "fournie": v is not None})
    return profil


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def dossier_detaille(c, d):
    if d is None:
        return None
    conseiller = db.ligne(c.execute(select(db.utilisateur.c.nom).where(db.utilisateur.c.id == d["conseiller_id"]))) if d["conseiller_id"] else None
    chrono = [{**a, "cree_le": _iso(a["cree_le"]),
               "libelle": TYPES_ACTION.get(a["type"]) or TYPES_AUTOMATIQUES.get(a["type"], a["type"]),
               "statut_avant": STATUTS.get(a["statut_avant"]), "statut_apres": STATUTS.get(a["statut_apres"])}
              for a in suivi.chronologie(c, d["id"])]
    return {**{k: _iso(v) for k, v in d.items()}, "libelle_statut": STATUTS[d["statut"]],
            "conseiller": conseiller["nom"] if conseiller else None,
            "motif": MOTIFS_CLOTURE.get(d["motif_cloture"]), "chronologie": chrono}


def fiche_etudiant(c, etudiant_id: int, u: dict) -> dict | None:
    e = db.ligne(c.execute(select(db.etudiant).where(db.etudiant.c.id == etudiant_id)))
    if e is None:
        return None
    promo = db.ligne(c.execute(select(db.promotion).where(db.promotion.c.id == e["promotion_id"])))
    valeurs = json.loads(e["caracteristiques"] or "{}")
    resultat = current_app.moteur.expliquer(valeurs)
    reel = e["abandon_reel"]
    verification = None
    if reel is not None:
        verification = {cle: ((p >= round(SEUIL_ALERTE, 3)) == (reel == 1))
                        for cle, p in (("noyau", resultat["probabilite_noyau"]), ("ml", resultat["probabilite_ml"]))}
    ouvert = db.ligne(c.execute(select(db.dossier).where(and_(db.dossier.c.etudiant_id == etudiant_id, db.dossier.c.statut != "clos"))))
    clos = db.lignes(c.execute(select(db.dossier).where(and_(db.dossier.c.etudiant_id == etudiant_id, db.dossier.c.statut == "clos"))
                               .order_by(db.dossier.c.clos_le.desc())))
    historique = [{"date": _iso(h["cree_le"]), "moment": h["moment"], "probabilite": h["probabilite"],
                   "categorie": h["categorie"], "par": h["par"], "import": h["lot_id"] is not None}
                  for h in db.lignes(c.execute(
                      select(db.evaluation.c.cree_le, db.evaluation.c.moment, db.evaluation.c.probabilite,
                             db.evaluation.c.categorie, db.evaluation.c.lot_id, db.utilisateur.c.nom.label("par"))
                      .select_from(db.evaluation.outerjoin(db.utilisateur, db.utilisateur.c.id == db.evaluation.c.utilisateur_id))
                      .where(db.evaluation.c.etudiant_id == etudiant_id).order_by(db.evaluation.c.cree_le, db.evaluation.c.id)))]
    referent = db.ligne(c.execute(select(db.utilisateur.c.id, db.utilisateur.c.nom).where(db.utilisateur.c.id == e["referent_id"]))) if e["referent_id"] else None
    conseillers = db.lignes(c.execute(select(db.utilisateur.c.id, db.utilisateur.c.nom, db.utilisateur.c.role)
                                      .where(db.utilisateur.c.actif.is_(True)).order_by(db.utilisateur.c.nom)))
    gestion = u["role"] in ("responsable", "admin")
    return {
        "id": e["id"], "reference": e["matricule"], "nom": e["nom"], "email": e["email"], "telephone": e["telephone"],
        "cohorte": promo["nom"], "cohorte_id": promo["id"],
        "avertissements": fiabilite.avertissements(current_app.moteur, valeurs),
        "devenir": DEVENIRS.get(e["devenir_reel"]) or ("Abandon" if reel == 1 else "Pas d'abandon" if reel == 0 else None),
        "devenir_reel": e["devenir_reel"], "abandon_reel": reel, "verification": verification,
        "resultat": resultat, "conseils": generer_conseils(valeurs), "profil": _profil(valeurs),
        "historique": historique, "referent": referent,
        "dossier": dossier_detaille(c, ouvert),
        "dossiers_clos": [{"id": d["id"], "ouvert_le": _iso(d["ouvert_le"]), "clos_le": _iso(d["clos_le"]),
                           "motif": MOTIFS_CLOTURE.get(d["motif_cloture"])} for d in clos],
        "droits": {"modifier_dossier": bool(ouvert) and suivi.peut_modifier(u, ouvert), "gerer": gestion,
                   "mettre_a_jour": True, "ouvrir": ouvert is None},
        "conseillers": conseillers if gestion else [c_ for c_ in conseillers if c_["id"] == u["id"]],
        "types_action": TYPES_ACTION, "statuts": STATUTS, "motifs": MOTIFS_CLOTURE,
    }


@bp_etudiants.get("/<int:etudiant_id>")
@connexion_requise
def fiche(etudiant_id):
    u = utilisateur_courant()
    with db.connexion() as c:
        d = fiche_etudiant(c, etudiant_id, u)
        if d is None:
            return jsonify({"erreur": "Étudiant introuvable."}), 404
        tracer(c, u, "consultation_fiche", "etudiant", etudiant_id)
    return jsonify(d)


def _operation(etudiant_id, fonction):
    """Execute une operation sur la fiche puis renvoie la fiche a jour (ou l'erreur a afficher)."""
    u = utilisateur_courant()
    try:
        with db.connexion() as c:
            if db.ligne(c.execute(select(db.etudiant.c.id).where(db.etudiant.c.id == etudiant_id))) is None:
                return jsonify({"erreur": "Étudiant introuvable."}), 404
            fonction(c, u)
            d = fiche_etudiant(c, etudiant_id, u)
    except suivi.Refus as e:
        return jsonify({"erreur": str(e)}), e.code
    except ValueError as e:
        return jsonify({"erreur": str(e)}), 400
    return jsonify(d)


@bp_etudiants.post("/<int:etudiant_id>/evaluations")
@connexion_requise
def mettre_a_jour(etudiant_id):
    donnees = request.get_json(silent=True) or {}

    def faire(c, u):
        r = reevaluer(c, current_app.moteur, etudiant_id, donnees, u)
        tracer(c, u, "mise_a_jour_resultats", "etudiant", etudiant_id, {"probabilite": r["probabilite"], "effet": r["effet"]})
    return _operation(etudiant_id, faire)


@bp_etudiants.post("/<int:etudiant_id>/dossier")
@connexion_requise
def ouvrir(etudiant_id):
    texte = (request.get_json(silent=True) or {}).get("texte")

    def faire(c, u):
        d = suivi.ouvrir_manuellement(c, etudiant_id, texte, u)
        tracer(c, u, "ouverture_dossier", "dossier", d["id"])
    return _operation(etudiant_id, faire)


@bp_etudiants.post("/<int:etudiant_id>/devenir")
@role_requis("responsable", "admin")
def devenir(etudiant_id):
    valeur = (request.get_json(silent=True) or {}).get("devenir") or None
    if valeur not in (None, "Dropout", "Graduate", "Enrolled"):
        return jsonify({"erreur": "Devenir inconnu."}), 400

    def faire(c, u):
        c.execute(db.etudiant.update().where(db.etudiant.c.id == etudiant_id).values(
            devenir_reel=valeur, abandon_reel=None if valeur is None else int(valeur == "Dropout"),
            devenir_saisi_le=db.maintenant() if valeur else None))
        tracer(c, u, "saisie_devenir", "etudiant", etudiant_id, {"devenir": valeur})
    return _operation(etudiant_id, faire)


@bp_etudiants.post("/<int:etudiant_id>/referent")
@role_requis("responsable", "admin")
def referent(etudiant_id):
    cid = (request.get_json(silent=True) or {}).get("conseiller_id")

    def faire(c, u):
        if cid is not None and db.ligne(c.execute(select(db.utilisateur.c.id).where(
                and_(db.utilisateur.c.id == cid, db.utilisateur.c.actif.is_(True))))) is None:
            raise suivi.Refus("Conseiller introuvable ou désactivé.")
        c.execute(db.etudiant.update().where(db.etudiant.c.id == etudiant_id).values(referent_id=cid))
        tracer(c, u, "referent", "etudiant", etudiant_id, {"conseiller_id": cid})
    return _operation(etudiant_id, faire)
