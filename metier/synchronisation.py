"""Raccordement au systeme de scolarite : imports automatiques, sans intervention humaine.

Deux voies, au choix de la direction informatique :
  1. API : le systeme de scolarite envoie le fichier d'une promotion a POST /api/v1/synchronisation, avec un
     jeton de service (en-tete « Authorization: Bearer ... ») cree par l'administrateur (page Donnees) ;
  2. dossier de depot : le systeme de scolarite depose « <Nom de la promotion>.csv » dans un dossier partage,
     et `python -m outils.synchroniser --depot DOSSIER` (tache planifiee) les importe.
Dans les deux cas, l'import est idempotent : un etudiant deja connu (meme matricule, meme promotion) recoit une
nouvelle estimation au lieu d'etre cree une seconde fois ; renvoyer le meme fichier ne cree aucun doublon.

Un jeton de service n'est jamais stocke : seule son empreinte SHA-256 l'est. Il est affiche une fois, a sa creation,
et peut etre revoque a tout moment. Chaque usage est trace dans le journal.
"""
from __future__ import annotations

import hashlib
import secrets

from sqlalchemy import select

import db
from metier.journal import tracer
from moteur import cohortes
from moteur.referentiels import CHAMPS_FORMULAIRE

PREFIXE_JETON = "aap_"
MIN_CHAMPS_RECONNUS = 5


class ImportRefuse(ValueError):
    pass


# ------------------------------------------------------------------ jetons de service
def _empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def creer_jeton(c, nom: str, utilisateur: dict) -> tuple[int, str]:
    jeton = PREFIXE_JETON + secrets.token_urlsafe(32)
    identifiant = c.execute(db.jeton_service.insert().values(
        nom=nom[:120], prefixe=jeton[:12], empreinte=_empreinte(jeton), cree_par=utilisateur["id"],
        cree_le=db.maintenant())).inserted_primary_key[0]
    tracer(c, utilisateur, "creation_jeton", "jeton", identifiant, {"nom": nom[:120]})
    return identifiant, jeton


def jeton_valide(c, jeton: str | None) -> dict | None:
    """Le jeton presente, s'il existe et n'est pas revoque. La comparaison porte sur des empreintes de
    longueur fixe : elle ne renseigne pas un attaquant sur le debut d'un jeton valide."""
    if not jeton or not jeton.startswith(PREFIXE_JETON) or len(jeton) > 200:
        return None
    r = db.ligne(c.execute(select(db.jeton_service).where(db.jeton_service.c.empreinte == _empreinte(jeton))))
    if r is None or r["revoque_le"] is not None:
        return None
    c.execute(db.jeton_service.update().where(db.jeton_service.c.id == r["id"]).values(derniere_utilisation=db.maintenant()))
    return r


def revoquer_jeton(c, identifiant: int, utilisateur: dict) -> bool:
    r = c.execute(db.jeton_service.update().where(
        db.jeton_service.c.id == identifiant, db.jeton_service.c.revoque_le.is_(None)).values(revoque_le=db.maintenant()))
    if r.rowcount:
        tracer(c, utilisateur, "revocation_jeton", "jeton", identifiant)
    return bool(r.rowcount)


def lister_jetons(c) -> list[dict]:
    t = db.jeton_service
    lignes = db.lignes(c.execute(select(t.c.id, t.c.nom, t.c.prefixe, t.c.cree_le, t.c.derniere_utilisation, t.c.revoque_le,
                                        db.utilisateur.c.nom.label("cree_par"))
                                 .select_from(t.outerjoin(db.utilisateur, db.utilisateur.c.id == t.c.cree_par))
                                 .order_by(t.c.id.desc())))
    for l in lignes:
        for k in ("cree_le", "derniere_utilisation", "revoque_le"):
            l[k] = l[k].isoformat() if l[k] else None
    return lignes


# ------------------------------------------------------------------ import automatique
def synchroniser(moteur, contenu: bytes, promotion: str, fichier: str | None, source: str) -> dict:
    """Importe le fichier d'une promotion (creee au besoin). `source` : « jeton:<nom> » ou « depot »."""
    promotion = (promotion or "").strip()[:200]
    if not promotion:
        raise ImportRefuse("Nom de promotion manquant.")
    df, erreur = cohortes.lire_csv(contenu)
    if erreur:
        raise ImportRefuse(erreur)
    presentes = {moteur.normaliser(c) for c in df.columns}
    reconnus = [c for c in CHAMPS_FORMULAIRE if moteur.normaliser(c) in presentes]
    if len(reconnus) < MIN_CHAMPS_RECONNUS:
        raise ImportRefuse(f"Structure non reconnue : {len(reconnus)} des {len(CHAMPS_FORMULAIRE)} colonnes attendues. "
                           "Le système de scolarité doit exporter les colonnes du gabarit d'import (page Importer).")
    if not any(moteur.normaliser(c) in cohortes.NOMS_REFERENCE for c in df.columns):
        raise ImportRefuse("Colonne du matricule absente : elle est indispensable pour mettre à jour sans créer de doublons.")
    try:
        compte = cohortes.importer(moteur, df, promotion, "etablissement", fichier)
    except ValueError as e:
        raise ImportRefuse(str(e)) from e
    with db.connexion() as c:
        tracer(c, {"id": None, "identifiant": source[:80]}, "synchronisation", "promotion", compte["cohorte_id"],
               {"promotion": promotion, "fichier": fichier, "effectif": compte["effectif"], "nouveaux": compte["nouveaux"],
                "dossiers_ouverts": compte["dossiers_ouverts"]})
    return compte
