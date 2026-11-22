"""Mode demonstration : comptes fictifs et suivi deja engage sur les cohortes 2015 a 2017.

Tout est fictif et reproductible (tirage aleatoire fixe) : les noms des comptes, les actions et les dates.
Le devenir reel des etudiants, lui, est celui du jeu de donnees : il alimente la surveillance du modele.
"""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select
from werkzeug.security import generate_password_hash

import db
from .regles import DELAIS, MOTIFS_CLOTURE

MOT_DE_PASSE_DEMO = "demo"
COMPTES_DEMO = [
    ("admin", "Administrateur (démo)", "admin"),
    ("responsable", "Responsable de la scolarité (démo)", "responsable"),
    ("conseiller1", "Conseiller A (démo)", "conseiller"),
    ("conseiller2", "Conseiller B (démo)", "conseiller"),
]

ACTIONS = [
    ("appel", "Appel passé : l'étudiant confirme des difficultés en {matiere}. Entretien fixé."),
    ("entretien", "Entretien réalisé : charge de travail mal évaluée, {matiere} à rattraper."),
    ("tutorat", "Inscrit au tutorat de {matiere}, deux séances par semaine."),
    ("financier", "Orienté vers le service financier pour un échéancier."),
    ("amenagement", "Report d'une unité au semestre suivant, validé avec le responsable de filière."),
    ("note", "Point d'étape : assiduité en hausse, à revoir après les partiels."),
]
MATIERES = ["mathématiques", "statistiques", "comptabilité", "anatomie", "méthodologie", "langue"]


def creer_comptes(c) -> dict:
    ids = {}
    for identifiant, nom, role in COMPTES_DEMO:
        r = db.ligne(c.execute(select(db.utilisateur.c.id).where(db.utilisateur.c.identifiant == identifiant)))
        if r:
            ids[identifiant] = r["id"]
            continue
        ids[identifiant] = c.execute(db.utilisateur.insert().values(
            identifiant=identifiant, nom=nom, role=role, mdp_hache=generate_password_hash(MOT_DE_PASSE_DEMO),
            actif=True, doit_changer_mdp=False, cree_le=db.maintenant())).inserted_primary_key[0]
    return ids


def engager_le_suivi(c, promotion_id: int, ids: dict) -> None:
    """Fait vieillir les dossiers ouverts automatiquement et simule quelques semaines de travail des conseillers."""
    hasard = random.Random(2026)
    maintenant = db.maintenant()
    dossiers = db.lignes(c.execute(
        select(db.dossier.c.id, db.dossier.c.probabilite_ouverture)
        .join(db.etudiant, db.etudiant.c.id == db.dossier.c.etudiant_id)
        .where(db.etudiant.c.promotion_id == promotion_id).order_by(db.dossier.c.probabilite_ouverture.desc())))
    conseillers = [ids["conseiller1"], ids["conseiller2"]]
    # 260 dossiers tires au hasard ont ete attribues puis plus ou moins avances ; les autres viennent d'arriver
    attribues = set(hasard.sample(range(len(dossiers)), min(260, len(dossiers))))
    for rang, d in enumerate(dossiers):
        recent = rang not in attribues
        ouvert = maintenant - (timedelta(days=hasard.randint(0, 5), hours=hasard.randint(0, 20)) if recent
                               else timedelta(days=hasard.randint(6, 40), hours=hasard.randint(0, 9)))
        c.execute(db.action.update().where(db.action.c.dossier_id == d["id"]).values(cree_le=ouvert))
        if recent:
            c.execute(db.dossier.update().where(db.dossier.c.id == d["id"]).values(
                ouvert_le=ouvert, maj_le=ouvert, echeance=(ouvert + timedelta(days=DELAIS["a_contacter"])).date()))
            continue
        conseiller = conseillers[len([x for x in attribues if x < rang]) % 2]
        etape = hasard.choices(["a_contacter", "contacte", "entretien", "accompagnement", "clos"], [14, 18, 22, 30, 16])[0]
        quand = ouvert + timedelta(hours=hasard.randint(2, 30))
        c.execute(db.action.insert().values(dossier_id=d["id"], utilisateur_id=ids["responsable"], type="attribution",
                                            texte="Dossier attribué.", cree_le=quand))
        statut, premier_contact, chemin = "a_contacter", None, ["contacte", "entretien", "accompagnement", "clos"]
        cible = ["a_contacter", "contacte", "entretien", "accompagnement", "clos"].index(etape)
        matiere = hasard.choice(MATIERES)
        for pas in range(cible):
            quand = quand + timedelta(days=hasard.randint(1, 9))
            if quand >= maintenant:
                quand = maintenant - timedelta(hours=hasard.randint(1, 20))
            nouveau = chemin[pas]
            if nouveau == "clos":
                motif = hasard.choice(["accompagnement_termine", "accompagnement_termine", "risque_ecarte", "injoignable", "reorientation"])
                c.execute(db.action.insert().values(dossier_id=d["id"], utilisateur_id=conseiller, type="cloture",
                                                    texte=MOTIFS_CLOTURE[motif] + ".", statut_avant=statut, statut_apres="clos", cree_le=quand))
                c.execute(db.dossier.update().where(db.dossier.c.id == d["id"]).values(
                    statut="clos", clos_le=quand, motif_cloture=motif, probabilite_cloture=d["probabilite_ouverture"], echeance=None))
                statut = "clos"
                break
            type_, texte = ACTIONS[min(pas + (pas >= 1) * hasard.randint(0, 3), len(ACTIONS) - 1)]
            c.execute(db.action.insert().values(dossier_id=d["id"], utilisateur_id=conseiller, type="statut",
                                                statut_avant=statut, statut_apres=nouveau, cree_le=quand))
            c.execute(db.action.insert().values(dossier_id=d["id"], utilisateur_id=conseiller, type=type_,
                                                texte=texte.format(matiere=matiere), cree_le=quand + timedelta(minutes=5)))
            premier_contact = premier_contact or quand
            statut = nouveau
        valeurs = {"conseiller_id": conseiller, "ouvert_le": ouvert, "premier_contact_le": premier_contact,
                   "maj_le": quand}
        if statut != "clos":
            valeurs.update(statut=statut, echeance=(quand + timedelta(days=DELAIS[statut])).date())
        c.execute(db.dossier.update().where(db.dossier.c.id == d["id"]).values(**valeurs))
