"""Correspondance entre l'application et le projet de recherche (protocole rigoureux).

Projet de recherche : github.com/onelngoma-source/abandon-universitaire. L'application doit :
  - utiliser le meme decoupage par cohorte (developpement 2008 a 2014, test 2015 a 2017) ;
  - retrouver exactement l'evaluation finale pre-enregistree sur le jeu de test ;
  - ne rien apprendre du jeu de test (bornes et valeurs par defaut comprises) ;
  - expliquer ses estimations de facon exacte.
"""
import numpy as np
import pandas as pd
import pytest

from conftest import RACINE
from moteur.variables import BINAIRES, NOMINALES, preparer

COHORTE_PAR_CHOMAGE = {7.6: 2008, 9.4: 2009, 10.8: 2010, 12.7: 2011, 15.5: 2012,
                       16.2: 2013, 13.9: 2014, 12.4: 2015, 11.1: 2016, 8.9: 2017}


@pytest.fixture(scope="module")
def donnees():
    df = pd.read_csv(RACINE / "data" / "data_avec_cible_binaire.csv")
    df.columns = [c.strip() for c in df.columns]
    df["cohorte"] = df["Unemployment rate"].map(COHORTE_PAR_CHOMAGE)
    return df


def test_decoupage_par_cohorte(donnees):
    dev, test = donnees[donnees["cohorte"] <= 2014], donnees[donnees["cohorte"] > 2014]
    assert donnees["cohorte"].notna().all() and donnees["cohorte"].nunique() == 10
    assert (len(donnees), len(dev), len(test)) == (4424, 3197, 1227)
    assert (int((test["Target"] == "Dropout").sum()), int((dev["Target"] == "Dropout").sum())) == (326, 1095)


def test_le_fichier_du_jeu_de_test_contient_exactement_les_cohortes_2015_a_2017(donnees):
    fichier = pd.read_csv(RACINE / "data" / "jeu_de_test_2015_2017.csv")
    attendu = donnees[donnees["cohorte"] > 2014]
    assert sorted(fichier["Reference"]) == sorted(f"E-{i + 1:04d}" for i in attendu.index)
    assert set(fichier["Unemployment rate"]) == {12.4, 11.1, 8.9}
    colonnes = [c for c in fichier.columns if c not in ("Reference", "Target")]
    assert len(colonnes) == 36
    assert np.allclose(fichier[colonnes].to_numpy(float), attendu[colonnes].to_numpy(float))


def test_les_scores_du_jeu_de_test_retrouvent_l_evaluation_finale(client, moteur):
    """Le tableau de bord recalcule ROC-AUC, Brier, rappel et precision : ce sont exactement ceux du rapport
    final du projet de recherche (reports/evaluation_finale.json, moment T2)."""
    cohorte = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    d = client.get(f"/api/cohortes/{cohorte}").json
    assert len(d["lignes"]) == 1227 and sum(l["abandon_reel"] for l in d["lignes"]) == 326
    assert {l["mode"] for l in d["lignes"]} == {"T2"}
    for cle, ref in d["reference"].items():
        for indicateur, attendu in ref.items():
            assert abs(d["metriques"][cle][indicateur] - attendu) <= 6e-4, (cle, indicateur)


@pytest.mark.parametrize("moment", ["T0", "T1", "T2"])
def test_les_trois_modeles_retrouvent_l_evaluation_finale(moteur, donnees, moment):
    from sklearn.metrics import roc_auc_score
    test = donnees[donnees["cohorte"] > 2014]
    X, y, *_ = preparer(test, moment)
    for nom, cle in (("logistique", "logistique"), ("noyau", "noyau")):
        p = moteur.modeles[moment][nom].predict_proba(X)[:, 1]
        assert abs(roc_auc_score(y, p) - moteur.reference[cle][moment]["auc"]) <= 1e-4


def test_aucune_borne_ni_valeur_par_defaut_ne_vient_du_jeu_de_test(moteur, donnees):
    dev = donnees[donnees["cohorte"] <= 2014]
    for c in moteur.variables:
        assert moteur.bornes[c] == (float(dev[c].min()), float(dev[c].max())), c
        if c in NOMINALES or c in BINAIRES:
            assert moteur.defauts[c] == float(dev[c].mode().iloc[0]), c
    # contre-epreuve : le test contient des valeurs hors des bornes du developpement, qui sont donc ramenees
    test = donnees[donnees["cohorte"] > 2014]
    assert any(test[c].max() > moteur.bornes[c][1] or test[c].min() < moteur.bornes[c][0] for c in moteur.variables)


def test_reglages_identiques_au_projet_de_recherche(moteur):
    assert {m: r["C"] for m, r in moteur.reglages.items()} == {"T0": 0.1, "T1": 0.1, "T2": 0.1}
    assert {m: round(r["bande"], 4) for m, r in moteur.reglages.items()} == {"T0": 0.8177, "T1": 1.0456, "T2": 1.3372}


def test_les_contributions_expliquent_exactement_la_regression_logistique(moteur):
    """Somme des contributions = logit(p) - logit de l'etudiant moyen : l'explication est exacte."""
    profils = [{}, {"Curricular units 1st sem (enrolled)": 6, "Curricular units 1st sem (approved)": 1},
               {"Curricular units 2nd sem (approved)": 6, "Debtor": 1, "Course": 9853}]
    for profil in profils:
        valeurs, _ = moteur.nettoyer(pd.DataFrame([profil]))
        moment = moteur.moments(valeurs).iloc[0]
        completees, _ = moteur._completer(valeurs, moment)
        X, *_ = preparer(completees, moment)
        p = moteur.modeles[moment]["logistique"].predict_proba(X)[0, 1]
        total = sum(moteur.contributions(X, moment).values())
        assert abs(total - (np.log(p / (1 - p)) - moteur.logit_reference(moment))) < 1e-9


def test_seuil_d_alerte_et_niveaux():
    from moteur.scoring import categorie
    assert [categorie(p) for p in (0.10, 0.166, 0.167, 0.49, 0.5, 0.95)] == \
        ["faible", "faible", "moyen", "moyen", "eleve", "eleve"]
