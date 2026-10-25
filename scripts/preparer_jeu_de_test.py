"""Reconstruit data/jeu_de_test_1328.csv : les 1 328 etudiants du jeu de TEST du memoire.

Meme separation que le Chapitre II : 70 / 30, stratifiee sur l'abandon, graine 42.
Usage : python scripts/preparer_jeu_de_test.py
"""
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

RACINE = Path(__file__).resolve().parent.parent

df = pd.read_csv(RACINE / "data" / "data_avec_cible_binaire.csv")
y = df["Abandon"]
X = df.drop(columns=["Target", "Abandon"])
_, X_test, _, _ = train_test_split(X, y, test_size=0.30, stratify=y, random_state=42)

test = df.loc[X_test.index.sort_values()].drop(columns=["Abandon"]).copy()
test.columns = [c.strip() for c in test.columns]
test.insert(0, "Reference", [f"E-{i + 1:04d}" for i in test.index])
test.to_csv(RACINE / "data" / "jeu_de_test_1328.csv", index=False)
print(f"{len(test)} etudiants de test ecrits ; abandons : {(test['Target'] == 'Dropout').sum()}")
