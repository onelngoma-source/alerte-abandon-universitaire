"""
Chapitre III.2 - Analyse descriptive du jeu de données
Etude : L'abandon universitaire - approche predictive noyau vs Machine Learning
"""
import pathlib

import pandas as pd
import numpy as np

# Racine du depot, deduite de l'emplacement de ce fichier : le script reste
# executable quel que soit le dossier d'ou on le lance.
RACINE = pathlib.Path(__file__).resolve().parents[1]
DONNEES = RACINE / "data"

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 140)

df = pd.read_csv(DONNEES / "data_officiel.csv", sep=";", encoding="utf-8-sig")

print("=" * 70)
print("1. STRUCTURE GENERALE")
print("=" * 70)
print(f"Nombre d'observations : {df.shape[0]}")
print(f"Nombre de variables   : {df.shape[1]}")
print(f"Valeurs manquantes    : {df.isna().sum().sum()}")

print()
print("=" * 70)
print("2. DISTRIBUTION DE LA VARIABLE CIBLE (Target)")
print("=" * 70)
print(df["Target"].value_counts())
print(df["Target"].value_counts(normalize=True).round(3) * 100)

# Reformulation binaire : Abandon (Dropout) vs Non-abandon (Enrolled + Graduate)
df["Abandon"] = (df["Target"] == "Dropout").astype(int)
print()
print("Reformulation binaire (Abandon = 1 si Dropout) :")
print(df["Abandon"].value_counts())
print(f"Taux d'abandon global : {df['Abandon'].mean()*100:.1f} %")

print()
print("=" * 70)
print("3. VARIABLES ACADEMIQUES CLES (moyennes par groupe)")
print("=" * 70)
cols_academiques = [
    "Curricular units 1st sem (grade)",
    "Curricular units 2nd sem (grade)",
    "Curricular units 1st sem (approved)",
    "Curricular units 2nd sem (approved)",
]
print(df.groupby("Abandon")[cols_academiques].mean().round(2))

print()
print("=" * 70)
print("4. VARIABLES SOCIO-ECONOMIQUES (taux d'abandon par sous-groupe)")
print("=" * 70)
print("Selon la bourse (Scholarship holder) :")
print(df.groupby("Scholarship holder")["Abandon"].mean().round(3) * 100)
print()
print("Selon le statut de debiteur (Debtor) :")
print(df.groupby("Debtor")["Abandon"].mean().round(3) * 100)
print()
print("Selon la mise a jour des frais de scolarite (Tuition fees up to date) :")
print(df.groupby("Tuition fees up to date")["Abandon"].mean().round(3) * 100)

print()
print("=" * 70)
print("5. VARIABLE DEMOGRAPHIQUE (genre)")
print("=" * 70)
print(df.groupby("Gender")["Abandon"].mean().round(3) * 100)

df.to_csv(DONNEES / "data_avec_cible_binaire.csv", index=False)
print()
print("Fichier enrichi sauvegarde : data_avec_cible_binaire.csv")
