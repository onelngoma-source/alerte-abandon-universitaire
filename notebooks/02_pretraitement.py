"""
Chapitre II.3 - Demarche methodologique, etape 2 : Pretraitement des donnees
"""
import pathlib

# Racine du depot, deduite de l'emplacement de ce fichier : le script reste
# executable quel que soit le dossier d'ou on le lance.
RACINE = pathlib.Path(__file__).resolve().parents[1]
DONNEES, MODELES = RACINE / "data", RACINE / "models"
MODELES.mkdir(exist_ok=True)

import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from imblearn.over_sampling import SMOTE

df = pd.read_csv(DONNEES / "data_avec_cible_binaire.csv")

# On retire Target (remplace par Abandon) et Enrolled n'est pas dans le perimetre
# On garde toutes les variables explicatives (deja numeriques/codees dans le dataset officiel)
y = df["Abandon"]
X = df.drop(columns=["Target", "Abandon"])

print(f"Variables explicatives retenues : {X.shape[1]}")
print(f"Observations : {X.shape[0]}")

# Split stratifie 70/30, coherent avec la taille de l'echantillon (guide : justifier le choix)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.30, stratify=y, random_state=42
)
print(f"\nTrain : {X_train.shape[0]} ({y_train.mean()*100:.1f}% abandon)")
print(f"Test  : {X_test.shape[0]} ({y_test.mean()*100:.1f}% abandon)")

# Normalisation - indispensable pour l'approche a noyau (sensible a l'echelle des variables)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Rééquilibrage SMOTE - uniquement sur le train, jamais sur le test (fuite de donnees sinon)
smote = SMOTE(random_state=42)
X_train_bal, y_train_bal = smote.fit_resample(X_train_scaled, y_train)
print(f"\nApres SMOTE : {X_train_bal.shape[0]} observations d'entrainement")
print(f"Repartition : {pd.Series(y_train_bal).value_counts().to_dict()}")

# Sauvegarde pour les etapes suivantes
joblib.dump({
    "X_train_scaled": X_train_scaled, "X_test_scaled": X_test_scaled,
    "X_train_bal": X_train_bal, "y_train_bal": y_train_bal,
    "y_train": y_train.values, "y_test": y_test.values,
    "feature_names": list(X.columns), "scaler": scaler,
}, DONNEES / "donnees_pretraitees.joblib")
print("\nDonnees pretraitees sauvegardees.")
