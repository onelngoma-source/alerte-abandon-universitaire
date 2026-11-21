"""Entraîne les modèles de l'application : régression logistique (modèle retenu) et Nadaraya-Watson,
pour les trois moments de prédiction (T0 : inscription, T1 : fin du 1er semestre, T2 : fin du 2e).

Même protocole que le projet de recherche (github.com/onelngoma-source/abandon-universitaire) :
  - développement = cohortes 2008 à 2014 (3 197 étudiants), test = cohortes 2015 à 2017 (1 227) ;
  - réglage par validation croisée par cohorte (log loss), sur le développement seulement ;
  - bornes et valeurs par défaut calculées sur le développement seulement.
Le test ne sert qu'à vérifier que l'on retrouve exactement l'évaluation finale pré-enregistrée.

Usage : python scripts/entrainer_modeles.py
"""
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GridSearchCV, LeaveOneGroupOut
from sklearn.pipeline import Pipeline

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from moteur.noyau import NadarayaWatson  # noqa: E402
from moteur.variables import BINAIRES, MOMENTS, NOMINALES, preparer, pretraitement  # noqa: E402

# Cohorte d'entrée, reconnue à son taux de chômage (hypothèse H1 du journal de recherche)
COHORTE_PAR_CHOMAGE = {7.6: 2008, 9.4: 2009, 10.8: 2010, 12.7: 2011, 15.5: 2012,
                       16.2: 2013, 13.9: 2014, 12.4: 2015, 11.1: 2016, 8.9: 2017}
# Évaluation finale du projet de recherche (reports/evaluation_finale.json), seuil d'alerte 1/6
REFERENCE = {
    "logistique": {
        "T0": {"auc": 0.7751, "brier": 0.1566, "rappel": 0.893, "precision": 0.353},
        "T1": {"auc": 0.8761, "brier": 0.1034, "rappel": 0.844, "precision": 0.546},
        "T2": {"auc": 0.9019, "brier": 0.0915, "rappel": 0.856, "precision": 0.613},
    },
    "noyau": {
        "T0": {"auc": 0.7000, "brier": 0.1734},
        "T1": {"auc": 0.8387, "brier": 0.1218},
        "T2": {"auc": 0.8650, "brier": 0.1078},
    },
}
COLONNES_VOISINS = ["Curricular units 1st sem (approved)", "Curricular units 2nd sem (approved)",
                    "Curricular units 1st sem (grade)", "Curricular units 2nd sem (grade)",
                    "Tuition fees up to date", "Age at enrollment"]

df = pd.read_csv(RACINE / "data" / "data_avec_cible_binaire.csv").drop(columns=["Abandon"])
df.columns = [c.strip() for c in df.columns]
VARIABLES = [c for c in df.columns if c != "Target"]
df.insert(0, "id_etudiant", range(len(df)))
df["cohorte"] = df["Unemployment rate"].map(COHORTE_PAR_CHOMAGE)
assert df["cohorte"].notna().all() and len(VARIABLES) == 36
dev = df[df["cohorte"] <= 2014].reset_index(drop=True)
test = df[df["cohorte"] > 2014].reset_index(drop=True)
assert (len(dev), len(test)) == (3197, 1227)
groupes = dev["cohorte"].to_numpy()
print(f"Développement : {len(dev)} étudiants (2008 à 2014) ; test : {len(test)} (2015 à 2017)")


def regler(estimateur, param, valeurs, X, y):
    return GridSearchCV(estimateur, {param: valeurs}, scoring="neg_log_loss", cv=LeaveOneGroupOut(),
                        n_jobs=-1).fit(X, y, groups=groupes)


modeles, reglages, moyennes = {}, {}, {}
for moment in MOMENTS:
    X, y, *cols = preparer(dev, moment)
    lr = regler(Pipeline([("prep", pretraitement(*cols)), ("m", LogisticRegression(max_iter=5000))]),
                "m__C", list(np.logspace(-3, 2, 11)), X, y)
    nw = regler(Pipeline([("prep", pretraitement(*cols)), ("m", NadarayaWatson())]),
                "m__bande", list(np.geomspace(0.5, 20, 16)), X, y)
    modeles[moment] = {"logistique": lr.best_estimator_, "noyau": nw.best_estimator_}
    reglages[moment] = {"C": float(lr.best_params_["m__C"]), "bande": float(nw.best_params_["m__bande"])}
    # Profil moyen du développement, dans l'espace du modèle : référence des contributions (explication)
    moyennes[moment] = lr.best_estimator_.named_steps["prep"].transform(X).mean(axis=0)

    # Vérification : on doit retrouver l'évaluation finale du projet de recherche
    Xt, yt, *_ = preparer(test, moment)
    for nom, modele in modeles[moment].items():
        p = modele.predict_proba(Xt)[:, 1]
        auc, brier = roc_auc_score(yt, p), brier_score_loss(yt, p)
        ref = REFERENCE[nom][moment]
        ok = abs(auc - ref["auc"]) <= 1e-4 and abs(brier - ref["brier"]) <= 1e-4
        print(f"{moment} · {nom:<10} ROC-AUC {auc:.4f} (référence {ref['auc']:.4f}) · "
              f"Brier {brier:.4f} (référence {ref['brier']:.4f}) [{'OK' if ok else 'ÉCART'}]")
        if not ok:
            raise SystemExit("Les modèles ne reproduisent pas l'évaluation finale : arrêt.")
print("Réglages :", reglages)

# Bornes, valeurs par défaut et étudiants de référence : développement uniquement (correction M13)
bornes = {c: (float(dev[c].min()), float(dev[c].max())) for c in VARIABLES}
prepares, *_ = preparer(dev, "T2")
defauts = {}
for c in VARIABLES:
    if c in NOMINALES or c in BINAIRES or c == "Nacionality":
        defauts[c] = float(dev[c].mode().iloc[0])
    else:  # médiane, notes comprises sans les 0 « aucune unité validée » : la même que l'imputation des modèles
        defauts[c] = float(prepares[c].median()) if c in prepares else float(dev[c].median())

joblib.dump({
    "modeles": modeles, "reglages": reglages, "moyennes_transformees": moyennes, "variables": VARIABLES,
    "bornes": bornes, "defauts": defauts, "reference": REFERENCE,
    "voisins": {"colonnes": COLONNES_VOISINS, "valeurs": dev[COLONNES_VOISINS].to_numpy(dtype=float),
                "abandon": (dev["Target"] == "Dropout").to_numpy(dtype=int),
                "cohorte": dev["cohorte"].to_numpy(dtype=int)},
}, RACINE / "models" / "modeles.joblib", compress=3)

sortie = test[VARIABLES + ["Target"]].copy()
sortie.insert(0, "Reference", [f"E-{i + 1:04d}" for i in test["id_etudiant"]])
sortie.to_csv(RACINE / "data" / "jeu_de_test_2015_2017.csv", index=False)
print(f"Écrit : models/modeles.joblib et data/jeu_de_test_2015_2017.csv "
      f"({len(sortie)} étudiants, {int((sortie['Target'] == 'Dropout').sum())} abandons)")
