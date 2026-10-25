"""
Chapitre II.3 - Demarche methodologique, etape 5 :
Modeles dedies au mode precoce, bornes et valeurs par defaut des variables.

Le formulaire de l'application accepte un profil dont les quatre champs du
second semestre sont vides. Imputer ces variables degraderait la mesure : on
entraine donc un second couple de modeles sur les 30 variables qui restent
quand tout le second semestre est retire, dans exactement les memes conditions
que les modeles complets (meme decoupage 70/30 stratifie a graine 42, SMOTE sur
le seul echantillon d'entrainement, normalisation ajustee sur l'entrainement).

Ce script produit aussi les deux tables que l'application charge au demarrage :
les bornes de chaque variable et sa valeur par defaut, toutes deux calculees
sur les 4 424 etudiants du jeu complet et non sur le seul entrainement, parce
qu'elles servent a valider et a completer des profils saisis a la main, pas a
apprendre quoi que ce soit.

A lancer apres 02_pretraitement.py (qui fournit le decoupage) :
    python3 notebooks/04_modeles_precoces.py
"""
import pathlib
import sys

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler

RACINE = pathlib.Path(__file__).resolve().parents[1]
DONNEES, MODELES = RACINE / "data", RACINE / "models"
MODELES.mkdir(exist_ok=True)
sys.path.insert(0, str(RACINE))
from kernel_utils import noyau_gaussien  # noqa: E402

GRAINE = 42
PART_TEST = 0.30
NB_VOISINS = 75
# Tout le second semestre sort du jeu de variables : les quatre champs du
# formulaire, mais aussi les deux variables que le formulaire ne demande pas et
# qui porteraient la meme information.
PREFIXE_2E_SEMESTRE = "Curricular units 2nd sem"

df = pd.read_csv(DONNEES / "data_avec_cible_binaire.csv")
y = df["Abandon"]
X = df.drop(columns=["Target", "Abandon"])
variables = list(X.columns)

# ---------------------------------------------------------------
# 1. Bornes et valeurs par defaut, sur les 4 424 etudiants
# ---------------------------------------------------------------
# Les bornes servent a ramener une saisie aberrante dans le domaine observe,
# avant toute estimation des valeurs absentes. La valeur par defaut remplace un
# champ du formulaire laisse vide le temps de chercher les voisins : c'est la
# mediane, insensible aux valeurs extremes.
bornes = {c: (float(X[c].min()), float(X[c].max())) for c in variables}
defauts = {c: float(X[c].median()) for c in variables}
joblib.dump(bornes, MODELES / "bornes_variables.joblib")
joblib.dump(defauts, MODELES / "valeurs_par_defaut.joblib")
print(f"Bornes et valeurs par defaut ecrites pour {len(variables)} variables "
      f"(calculees sur les {len(df)} etudiants).")

# ---------------------------------------------------------------
# 2. Jeu de variables du mode precoce
# ---------------------------------------------------------------
variables_precoce = [c for c in variables if not c.startswith(PREFIXE_2E_SEMESTRE)]
retirees = [c for c in variables if c.startswith(PREFIXE_2E_SEMESTRE)]
print(f"\nMode precoce : {len(variables_precoce)} variables conservees, "
      f"{len(retirees)} retirees.")
for c in retirees:
    print(f"  - {c}")

# ---------------------------------------------------------------
# 3. Meme decoupage que les modeles complets, puis SMOTE sur le train seul
# ---------------------------------------------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X[variables_precoce], y, test_size=PART_TEST, stratify=y, random_state=GRAINE
)
print(f"\nTrain : {len(X_train)} ({y_train.mean() * 100:.1f}% abandon)")
print(f"Test  : {len(X_test)} ({y_test.mean() * 100:.1f}% abandon)")

scaler_precoce = StandardScaler()
X_train_scaled = scaler_precoce.fit_transform(X_train)
X_test_scaled = scaler_precoce.transform(X_test)

X_train_bal, y_train_bal = SMOTE(random_state=GRAINE).fit_resample(X_train_scaled, y_train)
print(f"Apres SMOTE : {len(X_train_bal)} observations d'entrainement")

# ---------------------------------------------------------------
# 4. Les deux modeles, aux memes reglages que leurs equivalents complets
# ---------------------------------------------------------------
resultats = {}


def evaluer(nom, y_pred, y_proba):
    resultats[nom] = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred),
        "recall": recall_score(y_test, y_pred),
        "f1": f1_score(y_test, y_pred),
        "auc": roc_auc_score(y_test, y_proba),
        "matrice_confusion": confusion_matrix(y_test, y_pred).tolist(),
    }
    r = resultats[nom]
    print(f"\n{nom}")
    print(f"  Accuracy  : {r['accuracy']:.3f}")
    print(f"  Precision : {r['precision']:.3f}")
    print(f"  Recall    : {r['recall']:.3f}")
    print(f"  F1-score  : {r['f1']:.3f}")
    print(f"  AUC-ROC   : {r['auc']:.3f}")


modele_noyau_precoce = KNeighborsClassifier(
    n_neighbors=NB_VOISINS, weights=noyau_gaussien, metric="euclidean"
).fit(X_train_bal, y_train_bal)
evaluer("Approche a noyau, mode precoce",
        modele_noyau_precoce.predict(X_test_scaled),
        modele_noyau_precoce.predict_proba(X_test_scaled)[:, 1])

modele_rf_precoce = RandomForestClassifier(
    n_estimators=300, max_depth=12, random_state=GRAINE, n_jobs=-1
).fit(X_train_bal, y_train_bal)
evaluer("Random Forest, mode precoce",
        modele_rf_precoce.predict(X_test_scaled),
        modele_rf_precoce.predict_proba(X_test_scaled)[:, 1])

# ---------------------------------------------------------------
# 5. Serialisation
# ---------------------------------------------------------------
joblib.dump(modele_noyau_precoce, MODELES / "modele_noyau_precoce.joblib")
joblib.dump(modele_rf_precoce, MODELES / "modele_rf_precoce.joblib")
joblib.dump(scaler_precoce, MODELES / "scaler_precoce.joblib")
joblib.dump(variables_precoce, MODELES / "feature_names_precoce.joblib")
joblib.dump(resultats, MODELES / "resultats_precoces.joblib")

print("\n" + "=" * 70)
print(f"{'Modele':<40}{'Accuracy':<11}{'AUC':<9}{'F1':<9}")
for nom, r in resultats.items():
    print(f"{nom:<40}{r['accuracy']:<11.3f}{r['auc']:<9.3f}{r['f1']:<9.3f}")
print("\nModeles du mode precoce ecrits dans", MODELES)
