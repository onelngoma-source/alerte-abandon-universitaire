"""Page « Fiabilité du modèle » : tout ce qui justifie la confiance (ou la prudence) dans les estimations.

Les indicateurs sont recalcules au demarrage sur le jeu de test (cohortes 2015 a 2017, 1 227 etudiants
jamais vus pendant le developpement), avec les modeles de l'application. Ils retrouvent l'evaluation
finale pre-enregistree du projet de recherche (github.com/onelngoma-source/abandon-universitaire).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

import db
from .referentiels import LIBELLES_MOMENTS, RAPPORT_COUTS, SEUIL_ALERTE
from .variables import semestre

# Evaluation finale du projet de recherche (reports/evaluation_finale.json) : les modeles a arbres
# ne sont pas embarques dans l'application, leurs resultats sont repris tels quels.
COMPARAISON_RECHERCHE = [
    {"modele": "Régression logistique", "role": "Modèle retenu", "auc": {"T0": 0.775, "T1": 0.876, "T2": 0.902},
     "brier_t2": 0.0915, "auc_validation_t2": 0.923},
    {"modele": "Forêt aléatoire", "role": "", "auc": {"T0": 0.755, "T1": 0.869, "T2": 0.897},
     "brier_t2": 0.0966, "auc_validation_t2": 0.919},
    {"modele": "XGBoost", "role": "", "auc": {"T0": 0.769, "T1": 0.866, "T2": 0.893},
     "brier_t2": 0.0965, "auc_validation_t2": 0.922},
    {"modele": "Nadaraya-Watson (noyau)", "role": "Approche du mémoire, corrigée", "auc": {"T0": 0.700, "T1": 0.839, "T2": 0.865},
     "brier_t2": 0.1078, "auc_validation_t2": 0.894},
    {"modele": "Pipeline du mémoire d'origine", "role": "Référence historique", "auc": {"T0": None, "T1": 0.807, "T2": 0.844},
     "brier_t2": 0.1396, "auc_validation_t2": 0.846},
]
CAPACITE_REPERE = 0.20  # part des etudiants que l'on peut accompagner, repere du projet de recherche


def _au_moment(valeurs: pd.DataFrame, moment: str) -> pd.DataFrame:
    v = valeurs.copy()
    if moment != "T2":
        v[semestre("2nd")] = np.nan
    if moment == "T0":
        v[semestre("1st")] = np.nan
    return v


def _seuil(y, p):
    alerte = p >= SEUIL_ALERTE
    vrais = int((alerte & (y == 1)).sum())
    return {"alertes": int(alerte.sum()), "part_alertes": float(alerte.mean()),
            "rappel": vrais / max(int(y.sum()), 1), "precision": vrais / max(int(alerte.sum()), 1)}


def _capacite(y, p, part):
    n = max(1, int(round(part * len(p))))
    ordre = np.argsort(-p, kind="stable")[:n]
    return {"accompagnes": n, "detectes": int(y[ordre].sum()), "rappel": float(y[ordre].sum() / y.sum()),
            "precision": float(y[ordre].mean())}


def _calibration(y, p, nb=10):
    rangs = pd.qcut(pd.Series(p).rank(method="first"), nb, labels=False)
    sortie = []
    for k in range(nb):
        m = (rangs == k).to_numpy()
        sortie.append({"predit": float(p[m].mean()), "observe": float(y[m].mean()), "effectif": int(m.sum())})
    return sortie


@lru_cache(maxsize=1)
def calculer(moteur) -> dict:
    df = pd.read_csv(db.RACINE / "data" / db.FICHIER_JEU_DE_TEST, dtype=str, keep_default_na=False)
    y = (df["Target"] == "Dropout").astype(int).to_numpy()
    valeurs, _ = moteur.nettoyer(df)

    moments, probas = [], {}
    for m in ("T0", "T1", "T2"):
        s = moteur.scorer_valeurs(_au_moment(valeurs, m))
        p_ml, p_nw = s["probabilite_ml"].to_numpy(float), s["probabilite_noyau"].to_numpy(float)
        probas[m] = p_ml
        moments.append({
            "moment": m, "libelle": LIBELLES_MOMENTS[m],
            "logistique": {"auc": roc_auc_score(y, p_ml), "brier": brier_score_loss(y, p_ml), **_seuil(y, p_ml),
                           "capacite": _capacite(y, p_ml, CAPACITE_REPERE)},
            "noyau": {"auc": roc_auc_score(y, p_nw), "brier": brier_score_loss(y, p_nw), **_seuil(y, p_nw)},
        })
        if m == "T2":
            p_t2_nw = p_nw

    # courbe de capacite : si nous accompagnons x % des etudiants (les plus a risque), quelle part des abandons ?
    parts = [k / 100 for k in range(0, 101, 5)]
    courbes = {m: [0.0] + [_capacite(y, probas[m], q)["rappel"] for q in parts[1:]] for m in probas}

    # equite : le meme seuil donne-t-il la meme detection dans chaque groupe ? (modele de fin de 2e semestre)
    p = probas["T2"]
    groupes = [
        ("Bourse", "Scholarship holder", {1: "Boursiers", 0: "Non boursiers"}),
        ("Genre", "Gender", {0: "Femmes", 1: "Hommes"}),
        ("Dette", "Debtor", {1: "Débiteurs", 0: "Sans dette"}),
        ("Horaires", "Daytime/evening attendance", {1: "Cours du jour", 0: "Cours du soir"}),
    ]
    equite = []
    for titre, variable, libelles in groupes:
        lignes = []
        for code, libelle in libelles.items():
            m = (valeurs[variable] == code).to_numpy()
            if m.sum() < 20 or y[m].sum() < 5:
                continue
            lignes.append({"groupe": libelle, "effectif": int(m.sum()), "abandons": int(y[m].sum()),
                           "taux_abandon": float(y[m].mean()), **_seuil(y[m], p[m])})
        equite.append({"critere": titre, "lignes": lignes})
    age = valeurs["Age at enrollment"].to_numpy()
    lignes = []
    for libelle, m in (("Moins de 23 ans", age < 23), ("23 ans et plus", age >= 23)):
        lignes.append({"groupe": libelle, "effectif": int(m.sum()), "abandons": int(y[m].sum()),
                       "taux_abandon": float(y[m].mean()), **_seuil(y[m], p[m])})
    equite.append({"critere": "Âge à l'inscription", "lignes": lignes})

    return {
        "effectif": int(len(y)), "abandons": int(y.sum()), "seuil": SEUIL_ALERTE, "rapport_couts": RAPPORT_COUTS,
        "capacite_repere": CAPACITE_REPERE,
        "moments": moments,
        "calibration": {"logistique": _calibration(y, probas["T2"]), "noyau": _calibration(y, p_t2_nw)},
        "courbe_capacite": {"parts": parts, **courbes},
        "equite": equite,
        "comparaison": COMPARAISON_RECHERCHE,
    }


def avertissements(moteur, valeurs: dict) -> list[str]:
    """Mises en garde propres au profil, tirees de l'analyse d'equite sur les cohortes de test."""
    from .scoring import vers_nombre
    try:
        boursier = vers_nombre(valeurs.get("Scholarship holder")) == 1
    except ValueError:
        boursier = False
    sortie = []
    if boursier:
        groupes = {l["groupe"]: l for g in calculer(moteur)["equite"] if g["critere"] == "Bourse" for l in g["lignes"]}
        if "Boursiers" in groupes and "Non boursiers" in groupes:
            sortie.append(
                f"Étudiant boursier : sur les cohortes de test, le modèle n'a repéré que "
                f"{round(100 * groupes['Boursiers']['rappel'])} % des abandons de boursiers, contre "
                f"{round(100 * groupes['Non boursiers']['rappel'])} % chez les non-boursiers. "
                "Un risque faible est donc à interpréter avec prudence.")
    return sortie
