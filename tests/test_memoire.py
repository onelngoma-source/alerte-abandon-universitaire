"""Correspondance entre l'application et le memoire (Chapitres II et III)."""
import json

import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import train_test_split

from conftest import RACINE

# Valeurs publiees dans le memoire (test, 1 328 etudiants)
MEMOIRE = {"noyau": {"auc": 0.875, "exactitude": 0.836, "f1": 0.747},
           "ml": {"auc": 0.934, "exactitude": 0.886, "f1": 0.816}}


def test_separation_70_30_graine_42():
    df = pd.read_csv(RACINE / "data" / "data_avec_cible_binaire.csv")
    X, y = df.drop(columns=["Target", "Abandon"]), df["Abandon"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.30, stratify=y, random_state=42)
    assert (len(df), len(X_tr), len(X_te), int(y_te.sum())) == (4424, 3096, 1328, 427)


def test_fichier_du_jeu_de_test_correspond_a_la_separation():
    df = pd.read_csv(RACINE / "data" / "data_avec_cible_binaire.csv")
    X, y = df.drop(columns=["Target", "Abandon"]), df["Abandon"]
    _, X_te, _, _ = train_test_split(X, y, test_size=0.30, stratify=y, random_state=42)
    fichier = pd.read_csv(RACINE / "data" / "jeu_de_test_1328.csv")
    assert len(fichier) == 1328 and (fichier["Target"] == "Dropout").sum() == 427
    assert sorted(fichier["Reference"]) == sorted(f"E-{i + 1:04d}" for i in X_te.index)
    attendu = df.loc[X_te.index.sort_values()].reset_index(drop=True)
    attendu.columns = [c.strip() for c in attendu.columns]
    for colonne in [c.strip() for c in X.columns]:
        assert np.allclose(fichier[colonne].to_numpy(float), attendu[colonne].to_numpy(float)), colonne


def test_le_jeu_de_test_ne_contient_aucun_etudiant_d_entrainement(moteur):
    """Les 1 328 etudiants du tableau de bord sont bien ceux que les modeles n'ont pas vus."""
    import joblib
    d = joblib.load(RACINE / "data" / "donnees_pretraitees.joblib")
    fichier = pd.read_csv(RACINE / "data" / "jeu_de_test_1328.csv")
    X_test = moteur.scaler.transform(fichier[[c.strip() for c in moteur.variables]].rename(columns=str.strip)
                                     .set_axis(moteur.variables, axis=1))
    assert np.allclose(np.sort(X_test, axis=0), np.sort(d["X_test_scaled"], axis=0))


def test_indicateurs_du_tableau_de_bord_egaux_a_ceux_du_memoire(client):
    cohorte_id = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    donnees = client.get(f"/api/cohortes/{cohorte_id}").json
    assert len(donnees["lignes"]) == 1328
    assert sum(1 for l in donnees["lignes"] if l["abandon_reel"] == 1) == 427
    for modele in ("noyau", "ml"):
        for indicateur, attendu in MEMOIRE[modele].items():
            assert round(donnees["metriques"][modele][indicateur], 3) == attendu, (modele, indicateur)


def test_non_regression_contre_l_application_d_origine(moteur):
    """56 profils calcules avec l'application d'origine : memes probabilites et memes contributions SHAP."""
    golden = json.loads((RACINE / "tests" / "golden_profils.json").read_text(encoding="utf-8"))
    verifies = 0
    for item in golden:
        if item["incoherence"]:
            continue
        res = moteur.scorer(pd.DataFrame([item["reponses"]])).iloc[0]
        assert res["mode_calcul"] == item["mode"]
        assert abs(round(res["probabilite_noyau"], 3) - item["probabilite_noyau"]) <= 1.1e-3
        assert abs(round(res["probabilite_ml"], 3) - item["probabilite_ml"]) <= 1.1e-3
        if "shap" in item:
            sortie = moteur.scorer_un(item["reponses"])
            assert [round(c, 4) for _, c in item["shap"]] == [f["contribution"] for f in sortie["facteurs_contributifs"]]
        verifies += 1
    assert verifies == 55
