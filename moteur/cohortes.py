"""Construction d'une cohorte a partir d'un tableau d'etudiants (fichier CSV ou jeu de test).

Une SEULE fonction, `importer`, sert au chargement du jeu de test et a l'import d'un fichier :
c'est la garantie que les deux volets produisent exactement le meme tableau.
"""
from __future__ import annotations

import io
import json

import pandas as pd

import db
from .referentiels import CHAMPS_FORMULAIRE, FILIERES
from .scoring import Moteur

NOMS_REFERENCE = {"reference", "référence", "ref", "id", "identifiant", "matricule", "student id", "id etudiant"}
NOMS_DEVENIR = {"target", "devenir", "devenir reel", "devenir réel"}
NOMS_ABANDON = {"abandon", "dropout"}
_DEVENIRS_TEXTE = {"dropout": "Dropout", "abandon": "Dropout", "graduate": "Graduate", "diplome": "Graduate",
                   "diplômé": "Graduate", "enrolled": "Enrolled", "inscrit": "Enrolled"}
EN_TETES_GABARIT = ["Reference"] + CHAMPS_FORMULAIRE + ["Target"]
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
        cible = {"reference": "Reference", "devenir": "Target"}.get(champ)
        renommage[colonne] = cible or moteur.noms_canoniques.get(moteur.normaliser(champ), champ)
    cibles = set(renommage.values())
    a_supprimer = [c for c in df.columns if c not in renommage and
                   (moteur.noms_canoniques.get(moteur.normaliser(c)) in cibles
                    or (("Reference" in cibles) and moteur.normaliser(c) in NOMS_REFERENCE)
                    or (("Target" in cibles) and moteur.normaliser(c) in NOMS_DEVENIR | NOMS_ABANDON))]
    return df.drop(columns=a_supprimer).rename(columns=renommage)


def _colonne(df: pd.DataFrame, noms: set[str], moteur: Moteur) -> str | None:
    for c in df.columns:
        if moteur.normaliser(c) in noms:
            return c
    return None


def _entier_ou_none(valeur):
    return None if pd.isna(valeur) else int(round(float(valeur)))


def _reel_ou_none(valeur):
    return None if pd.isna(valeur) else round(float(valeur), 2)


def importer(moteur: Moteur, df: pd.DataFrame, nom: str, origine: str, fichier: str | None,
             proprietaire: str | None = None) -> dict:
    """Score `df`, l'enregistre en base comme nouvelle cohorte et renvoie un compte rendu."""
    df = df.reset_index(drop=True)
    valeurs, erreurs = moteur.nettoyer(df)
    valides = valeurs.drop(index=list(erreurs))
    if valides.empty:
        raise ValueError("Aucune ligne exploitable dans le fichier.")
    scores = moteur.scorer_valeurs(valides)

    col_ref = _colonne(df, NOMS_REFERENCE, moteur)
    col_devenir = _colonne(df, NOMS_DEVENIR, moteur)
    col_abandon = _colonne(df, NOMS_ABANDON, moteur)
    col_filiere = _colonne(df, {moteur.normaliser("Course")}, moteur)

    etudiants = []
    for i in valides.index:
        v, s = valides.loc[i], scores.loc[i]
        reference = str(df.at[i, col_ref]).strip() if col_ref else ""
        devenir, abandon = None, None
        if col_devenir:
            devenir = _DEVENIRS_TEXTE.get(moteur.normaliser(df.at[i, col_devenir]))
        if devenir:
            abandon = 1 if devenir == "Dropout" else 0
        elif col_abandon:
            texte = str(df.at[i, col_abandon]).strip().lower()
            abandon = {"1": 1, "1.0": 1, "0": 0, "0.0": 0, "oui": 1, "non": 0}.get(texte)
        course = _entier_ou_none(v["Course"])
        texte_filiere = ""
        if course is None and col_filiere:
            texte_filiere = str(df.at[i, col_filiere]).strip()
        genre = None if pd.isna(v["Gender"]) else ("Homme" if v["Gender"] == 1 else "Femme")
        etudiants.append({
            "reference": reference or f"L-{i + 1:04d}",
            "filiere": (FILIERES.get(course, f"Code {course}") if course is not None else (texte_filiere or None)),
            "genre": genre,
            "age": _reel_ou_none(v["Age at enrollment"]),
            "boursier": _entier_ou_none(v["Scholarship holder"]),
            "debiteur": _entier_ou_none(v["Debtor"]),
            "frais_a_jour": _entier_ou_none(v["Tuition fees up to date"]),
            "note_s1": _reel_ou_none(v["Curricular units 1st sem (grade)"]),
            "note_s2": _reel_ou_none(v["Curricular units 2nd sem (grade)"]),
            "devenir_reel": devenir, "abandon_reel": abandon,
            "p_noyau": float(s["probabilite_noyau"]), "c_noyau": s["categorie_noyau"],
            "p_ml": float(s["probabilite_ml"]), "c_ml": s["categorie_ml"],
            "mode": s["mode_calcul"],
            "caracteristiques": json.dumps({k: float(x) for k, x in v.items() if not pd.isna(x)}),
        })
    cohorte_id = db.creer_cohorte(nom, origine, fichier, etudiants, ignorees=len(erreurs),
                                 proprietaire=proprietaire)
    reconnues = [c for c in moteur.variables if moteur.normaliser(c) in {moteur.normaliser(x) for x in df.columns}]
    return {
        "cohorte_id": cohorte_id,
        "effectif": len(etudiants),
        "lignes_ignorees": [{"ligne": int(i) + 2, "motif": m} for i, m in list(erreurs.items())[:TAILLE_MAX_LIGNES_IGNOREES]],
        "nb_ignorees": len(erreurs),
        "variables_reconnues": len(reconnues),
        "variables_modele": len(moteur.variables),
        "nb_precoces": int((scores["mode_calcul"] == "precoce").sum()),
        "moyenne_estimees": round(float(scores["nb_estimees"].mean()), 1),
    }
