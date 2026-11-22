"""Suivi apres alerte : statuts, attribution, echeances, actions, cloture.

Parcours d'un dossier : a contacter -> contacte -> entretien realise -> accompagnement en cours -> clos.
On peut avancer de plusieurs etapes ou revenir en arriere (une erreur de saisie se corrige), mais on ne
clot qu'avec un motif. Chaque changement est inscrit dans le journal du dossier, avec son auteur.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import and_, select

import db
from .regles import DELAIS, MOTIFS_CLOTURE, STATUTS_OUVERTS, TYPES_ACTION


class Refus(Exception):
    """Operation interdite ou invalide : le message est destine a l'utilisateur."""

    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def lire(c, dossier_id: int) -> dict:
    d = db.ligne(c.execute(select(db.dossier).where(db.dossier.c.id == dossier_id)))
    if d is None:
        raise Refus("Dossier introuvable.", 404)
    return d


def peut_modifier(utilisateur: dict, d: dict) -> bool:
    """Responsable et administrateur : tous les dossiers. Conseiller : ses dossiers, et ceux qui ne sont
    encore attribues a personne (il peut les prendre en charge)."""
    if utilisateur["role"] in ("responsable", "admin"):
        return True
    return d["conseiller_id"] in (None, utilisateur["id"])


def _verifier(utilisateur, d, ouvert=True):
    if not peut_modifier(utilisateur, d):
        raise Refus("Ce dossier est suivi par un autre conseiller.", 403)
    if ouvert and d["statut"] == "clos":
        raise Refus("Ce dossier est clos.")


def _journal(c, dossier_id, utilisateur, type_, texte=None, avant=None, apres=None):
    c.execute(db.action.insert().values(dossier_id=dossier_id, utilisateur_id=utilisateur["id"], type=type_, texte=texte,
                                        statut_avant=avant, statut_apres=apres, cree_le=db.maintenant()))


def changer_statut(c, dossier_id: int, statut: str, utilisateur: dict, texte: str | None = None) -> dict:
    d = lire(c, dossier_id)
    _verifier(utilisateur, d)
    if statut not in STATUTS_OUVERTS:
        raise Refus("Statut inconnu (pour clore un dossier, indiquez un motif).")
    if statut == d["statut"]:
        return d
    maintenant = db.maintenant()
    valeurs = {"statut": statut, "maj_le": maintenant,
               "echeance": (maintenant + timedelta(days=DELAIS[statut])).date()}
    if d["premier_contact_le"] is None and statut != "a_contacter":
        valeurs["premier_contact_le"] = maintenant
    if d["conseiller_id"] is None and utilisateur["role"] == "conseiller":
        valeurs["conseiller_id"] = utilisateur["id"]  # agir sur un dossier libre revient a le prendre en charge
    c.execute(db.dossier.update().where(db.dossier.c.id == dossier_id).values(**valeurs))
    _journal(c, dossier_id, utilisateur, "statut", texte, d["statut"], statut)
    return lire(c, dossier_id)


def attribuer(c, dossier_id: int, conseiller_id: int | None, utilisateur: dict) -> dict:
    d = lire(c, dossier_id)
    _verifier(utilisateur, d)
    if utilisateur["role"] == "conseiller" and conseiller_id not in (utilisateur["id"], None):
        raise Refus("Un conseiller ne peut attribuer un dossier qu'à lui-même.", 403)
    nom = "personne"
    if conseiller_id is not None:
        cible = db.ligne(c.execute(select(db.utilisateur).where(db.utilisateur.c.id == conseiller_id)))
        if cible is None or not cible["actif"]:
            raise Refus("Conseiller introuvable ou désactivé.")
        nom = cible["nom"]
    c.execute(db.dossier.update().where(db.dossier.c.id == dossier_id).values(conseiller_id=conseiller_id, maj_le=db.maintenant()))
    _journal(c, dossier_id, utilisateur, "attribution", f"Dossier attribué à {nom}.")
    return lire(c, dossier_id)


def definir_echeance(c, dossier_id: int, echeance: str, utilisateur: dict) -> dict:
    d = lire(c, dossier_id)
    _verifier(utilisateur, d)
    try:
        jour = date.fromisoformat(echeance)
    except (TypeError, ValueError):
        raise Refus("Date d'échéance invalide.")
    c.execute(db.dossier.update().where(db.dossier.c.id == dossier_id).values(echeance=jour, maj_le=db.maintenant()))
    _journal(c, dossier_id, utilisateur, "echeance", f"Prochaine échéance : {jour.strftime('%d/%m/%Y')}.")
    return lire(c, dossier_id)


def ajouter_action(c, dossier_id: int, type_: str, texte: str, utilisateur: dict) -> dict:
    d = lire(c, dossier_id)
    _verifier(utilisateur, d)
    if type_ not in TYPES_ACTION:
        raise Refus("Type d'action inconnu.")
    texte = (texte or "").strip()
    if not texte:
        raise Refus("Décrivez l'action en quelques mots.")
    if len(texte) > 4000:
        raise Refus("Texte trop long (4 000 caractères au plus).")
    valeurs = {"maj_le": db.maintenant(), "relance": False}
    if d["premier_contact_le"] is None and type_ in ("appel", "entretien"):
        valeurs["premier_contact_le"] = db.maintenant()
    if d["conseiller_id"] is None and utilisateur["role"] == "conseiller":
        valeurs["conseiller_id"] = utilisateur["id"]
    c.execute(db.dossier.update().where(db.dossier.c.id == dossier_id).values(**valeurs))
    _journal(c, dossier_id, utilisateur, type_, texte)
    return lire(c, dossier_id)


def cloturer(c, dossier_id: int, motif: str, texte: str | None, utilisateur: dict) -> dict:
    d = lire(c, dossier_id)
    _verifier(utilisateur, d)
    if motif not in MOTIFS_CLOTURE:
        raise Refus("Indiquez le motif de clôture.")
    p = db.ligne(c.execute(select(db.etudiant.c.probabilite).where(db.etudiant.c.id == d["etudiant_id"])))["probabilite"]
    maintenant = db.maintenant()
    c.execute(db.dossier.update().where(db.dossier.c.id == dossier_id).values(
        statut="clos", clos_le=maintenant, motif_cloture=motif, probabilite_cloture=p, echeance=None,
        relance=False, maj_le=maintenant))
    _journal(c, dossier_id, utilisateur, "cloture", (MOTIFS_CLOTURE[motif] + (f". {texte.strip()}" if texte and texte.strip() else "")),
             d["statut"], "clos")
    return lire(c, dossier_id)


def ouvrir_manuellement(c, etudiant_id: int, texte: str | None, utilisateur: dict) -> dict:
    """Un conseiller peut ouvrir un dossier sans alerte : signalement d'un enseignant, demande de l'etudiant..."""
    if db.ligne(c.execute(select(db.dossier.c.id).where(and_(db.dossier.c.etudiant_id == etudiant_id, db.dossier.c.statut != "clos")))):
        raise Refus("Un dossier est déjà ouvert pour cet étudiant.")
    e = db.ligne(c.execute(select(db.etudiant).where(db.etudiant.c.id == etudiant_id)))
    from .evaluations import _ouvrir_dossier
    motif = (texte or "").strip() or "sans précision"
    dossier_id = _ouvrir_dossier(c, etudiant_id, e["evaluation_id"], e["probabilite"],
                                 utilisateur["id"] if utilisateur["role"] == "conseiller" else e["referent_id"],
                                 utilisateur["id"], f"Ouverture manuelle par {utilisateur['nom']} : {motif}.")
    return lire(c, dossier_id)


def chronologie(c, dossier_id: int) -> list[dict]:
    lignes = db.lignes(c.execute(
        select(db.action, db.utilisateur.c.nom.label("auteur"))
        .select_from(db.action.outerjoin(db.utilisateur, db.utilisateur.c.id == db.action.c.utilisateur_id))
        .where(db.action.c.dossier_id == dossier_id).order_by(db.action.c.cree_le.desc(), db.action.c.id.desc())))
    return lignes
