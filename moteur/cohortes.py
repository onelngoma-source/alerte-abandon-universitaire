"""Lecture d'un fichier d'etudiants et enregistrement dans une promotion (fichier CSV ou jeu de test).

Une SEULE fonction, `importer`, sert au chargement du jeu de test et a l'import d'un fichier :
c'est la garantie que les deux volets produisent exactement le meme tableau.
"""
from __future__ import annotations

import io

import pandas as pd

import db
from .referentiels import CHAMPS_FORMULAIRE
from .scoring import Moteur

NOMS_REFERENCE = {"reference", "référence", "ref", "id", "identifiant", "matricule", "student id", "id etudiant"}
NOMS_DEVENIR = {"target", "devenir", "devenir reel", "devenir réel"}
NOMS_ABANDON = {"abandon", "dropout"}
NOMS_NOM = {"nom", "nom complet", "nom et prenom", "nom et prénom", "prenom et nom", "prénom et nom", "name", "full name"}
NOMS_EMAIL = {"email", "e-mail", "courriel", "mail", "adresse email"}
NOMS_TELEPHONE = {"telephone", "téléphone", "tel", "tél", "phone", "portable"}
EN_TETES_GABARIT = ["Reference", "Nom", "Email", "Telephone"] + CHAMPS_FORMULAIRE + ["Target"]
TAILLE_MAX_LIGNES_IGNOREES = 20


def lire_csv(contenu: bytes) -> tuple[pd.DataFrame | None, str | None]:
    """Lit un CSV en essayant ';' puis ',' (et UTF-8 puis Latin-1). Toutes les cellules sont lues en texte :
    la conversion numerique (virgule decimale comprise) est faite ensuite, une seule fois, par le moteur."""
    for encodage in ("utf-8-sig", "latin-1"):
        try:
            texte = contenu.decode(encodage)
        except UnicodeDecodeError:
            continue
        for separateur in (";", ","):
            try:
                df = pd.read_csv(io.StringIO(texte), sep=separateur, dtype=str, keep_default_na=False)
            except Exception:
                continue
            if df.shape[1] > 1:
                df.columns = [str(c).strip() for c in df.columns]
                return df, None
        break
    return None, "Fichier illisible (séparateur non reconnu, essayez « ; » ou « , »)."


def appliquer_correspondance(df: pd.DataFrame, correspondance: dict | None, moteur: Moteur) -> pd.DataFrame:
    """Renomme les colonnes du fichier selon la correspondance choisie par l'utilisateur
    ({champ attendu: colonne du fichier}). Les cles speciales 'reference' et 'devenir' designent
    l'identifiant et le devenir reel."""
    if not correspondance:
        return df
    renommage = {}
    for champ, colonne in correspondance.items():
        if not colonne or colonne == "__aucune__" or colonne not in df.columns:
            continue
        cible = {"reference": "Reference", "devenir": "Target", "nom": "Nom", "email": "Email",
                 "telephone": "Telephone"}.get(champ)
        renommage[colonne] = cible or moteur.noms_canoniques.get(moteur.normaliser(champ), champ)
    cibles = set(renommage.values())
    a_supprimer = [c for c in df.columns if c not in renommage and
                   (moteur.noms_canoniques.get(moteur.normaliser(c)) in cibles
                    or (("Reference" in cibles) and moteur.normaliser(c) in NOMS_REFERENCE)
                    or (("Target" in cibles) and moteur.normaliser(c) in NOMS_DEVENIR | NOMS_ABANDON)
                    or (("Nom" in cibles) and moteur.normaliser(c) in NOMS_NOM)
                    or (("Email" in cibles) and moteur.normaliser(c) in NOMS_EMAIL)
                    or (("Telephone" in cibles) and moteur.normaliser(c) in NOMS_TELEPHONE))]
    return df.drop(columns=a_supprimer).rename(columns=renommage)


def _colonne(df: pd.DataFrame, noms: set[str], moteur: Moteur) -> str | None:
    for c in df.columns:
        if moteur.normaliser(c) in noms:
            return c
    return None


def promotion_par_nom(c, nom: str, origine: str = "etablissement") -> int:
    from sqlalchemy import select
    r = db.ligne(c.execute(select(db.promotion.c.id).where(db.promotion.c.nom == nom)))
    if r:
        return r["id"]
    return c.execute(db.promotion.insert().values(nom=nom, origine=origine, cree_le=db.maintenant())).inserted_primary_key[0]


def importer(moteur: Moteur, df: pd.DataFrame, nom: str | None, origine: str, fichier: str | None,
             promotion_id: int | None = None, utilisateur: dict | None = None) -> dict:
    """Score `df` et l'enregistre dans une promotion (existante : mise a jour des etudiants deja connus,
    par matricule ; sinon creee sous le nom donne). Rend le compte rendu de l'import."""
    from metier.evaluations import enregistrer_lot
    from metier.journal import tracer
    colonnes = {
        "reference": _colonne(df, NOMS_REFERENCE, moteur), "devenir": _colonne(df, NOMS_DEVENIR, moteur),
        "abandon": _colonne(df, NOMS_ABANDON, moteur), "filiere": _colonne(df, {moteur.normaliser("Course")}, moteur),
        "nom": _colonne(df, NOMS_NOM, moteur), "email": _colonne(df, NOMS_EMAIL, moteur),
        "telephone": _colonne(df, NOMS_TELEPHONE, moteur),
    }
    with db.connexion() as c:
        if promotion_id is None:
            promotion_id = promotion_par_nom(c, nom, origine)
        compte = enregistrer_lot(c, moteur, promotion_id, df, colonnes, fichier, utilisateur["id"] if utilisateur else None)
        if utilisateur:
            tracer(c, utilisateur, "import", "promotion", promotion_id,
                   {"fichier": fichier, "effectif": compte["effectif"], "nouveaux": compte["nouveaux"],
                    "dossiers_ouverts": compte["dossiers_ouverts"]})
    erreurs, scores = compte.pop("erreurs"), compte.pop("scores")
    reconnues = [v for v in moteur.variables if moteur.normaliser(v) in {moteur.normaliser(x) for x in df.columns}]
    return {
        **compte,
        "lignes_ignorees": [{"ligne": int(i) + 2, "motif": m} for i, m in list(erreurs.items())[:TAILLE_MAX_LIGNES_IGNOREES]],
        "nb_ignorees": len(erreurs),
        "variables_reconnues": len(reconnues),
        "variables_modele": len(moteur.variables),
        "nb_precoces": int((scores["mode_calcul"] != "T2").sum()),
        "par_moment": {m: int((scores["mode_calcul"] == m).sum()) for m in ("T0", "T1", "T2")},
        "moyenne_estimees": round(float(scores["nb_estimees"].mean()), 1),
    }
