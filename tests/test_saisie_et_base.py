"""Volet 2 (saisie individuelle), base de donnees et acces."""
import pytest
import pandas as pd

import db
from conftest import televerser

PROFIL = {"Curricular units 1st sem (enrolled)": "6", "Curricular units 1st sem (approved)": "4",
          "Curricular units 1st sem (evaluations)": "8", "Curricular units 1st sem (grade)": "11.5",
          "Curricular units 2nd sem (enrolled)": "6", "Curricular units 2nd sem (approved)": "4",
          "Curricular units 2nd sem (evaluations)": "8", "Curricular units 2nd sem (grade)": "11",
          "Tuition fees up to date": "1", "Scholarship holder": "0", "Debtor": "0",
          "Age at enrollment": "20", "Course": "9238"}


def test_la_saisie_donne_le_meme_score_que_l_import_du_meme_etudiant(client):
    """Un etudiant saisi au formulaire ou present dans un fichier recoit le meme score."""
    saisie = client.post("/api/predict", json=PROFIL).json
    fichier = pd.DataFrame([PROFIL]).to_csv(index=False).encode()
    r = televerser(client, fichier)
    ligne = client.get(f"/api/cohortes/{r.json['cohorte_id']}").json["lignes"][0]
    assert saisie["probabilite_noyau"] == round(ligne["p_noyau"], 3)
    assert saisie["probabilite_ml"] == round(ligne["p_ml"], 3)
    assert saisie["categorie_noyau"] == ligne["c_noyau"] and saisie["categorie_ml"] == ligne["c_ml"]


def test_nombres_json_ou_textes_donnent_le_meme_resultat(client):
    en_nombres = {k: float(v) for k, v in PROFIL.items()}
    assert client.post("/api/predict", json=PROFIL).json == client.post("/api/predict", json=en_nombres).json


def test_le_moment_depend_des_semestres_fournis(client):
    sans_s2 = {k: v for k, v in PROFIL.items() if "2nd sem" not in k}
    sans_semestre = {k: v for k, v in PROFIL.items() if "sem" not in k}
    moments = [client.post("/api/predict", json=p).json for p in (PROFIL, sans_s2, sans_semestre)]
    assert [s["moment"] for s in moments] == ["T2", "T1", "T0"]
    assert [s["nb_variables_modele"] for s in moments] == [32, 26, 20]
    assert all(len(s["facteurs_contributifs"]) == 5 for s in moments)


def test_incoherence_validees_superieures_aux_inscrites_refusee(client):
    r = client.post("/api/predict", json={**PROFIL, "Curricular units 1st sem (approved)": "9"})
    assert r.status_code == 400 and "Incohérence" in r.json["erreur"]


def test_valeur_non_numerique_refusee(client):
    r = client.post("/api/predict", json={**PROFIL, "Age at enrollment": "vingt"})
    assert r.status_code == 400


def test_conseils_financiers_avec_des_zeros_numeriques(client):
    """Correction d'un defaut de l'application d'origine : 0 (nombre) etait traite comme une valeur absente."""
    p = {k: float(v) for k, v in PROFIL.items()}
    p.update({"Tuition fees up to date": 0, "Scholarship holder": 0, "Debtor": 1})
    messages = " ".join(c["message"] for c in client.post("/api/predict", json=p).json["conseils"])
    assert "débiteur" in messages and "retard de paiement" in messages


def test_les_variables_estimees_sont_signalees(client):
    sortie = client.post("/api/predict", json=PROFIL).json
    assert sortie["nb_variables_estimees"] == 19 and sortie["nb_variables_modele"] == 32


def test_acces_protege(app):
    c = app.test_client()
    assert c.get("/tableau").status_code == 302
    assert c.get("/api/cohortes").status_code == 401
    assert c.post("/api/predict", json=PROFIL).status_code == 401


def test_la_base_demarre_vide_puis_le_jeu_de_test_se_charge_une_seule_fois(client):
    assert client.get("/api/cohortes").json == []
    premier = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    assert client.post("/api/cohortes/jeu-de-test").json["cohorte_id"] == premier
    assert len(client.get("/api/cohortes").json) == 1


def test_suppression_en_cascade_et_remise_a_zero(client, contenu_jeu_de_test):
    cohorte = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    with db.connecter() as c:
        assert c.execute("SELECT COUNT(*) FROM score").fetchone()[0] == 2 * 1227
    client.delete(f"/api/cohortes/{cohorte}")
    with db.connecter() as c:
        assert [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("cohorte", "etudiant", "score")] == [0, 0, 0]
    televerser(client, contenu_jeu_de_test)
    client.post("/api/cohortes/vider")
    assert client.get("/api/cohortes").json == []


def test_le_schema_impose_les_contraintes(client):
    import sqlite3
    import pytest
    client.post("/api/cohortes/jeu-de-test")
    with db.connecter() as c:
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("INSERT INTO score VALUES (1, 'noyau', 0.5, 'faible', 'complet')")  # cle primaire deja prise
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("INSERT INTO score VALUES (1, 'xgb', 0.5, 'faible', 'complet')")    # modele inconnu


def test_par_defaut_les_donnees_sont_deja_affichees_au_demarrage(app_prechargee):
    """Consigne de l'encadreur : au lancement, le tableau de bord contient deja les 1 227 etudiants de test (cohortes 2015 a 2017)."""
    c = app_prechargee.test_client()
    c.post("/connexion", data={"identifiant": "admin", "mot_de_passe": "changez-moi"})
    cohortes = c.get("/api/cohortes").json
    assert len(cohortes) == 1 and cohortes[0]["origine"] == "test_uci" and cohortes[0]["effectif"] == 1227
    assert len(c.get(f"/api/cohortes/{cohortes[0]['id']}").json["lignes"]) == 1227


def test_fiche_d_un_etudiant_reproduit_les_scores_du_tableau(client, contenu_jeu_de_test):
    cohorte = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    lignes = client.get(f"/api/cohortes/{cohorte}").json["lignes"]
    for l in lignes[::60]:  # un echantillon de 21 etudiants
        f = client.get(f"/api/etudiants/{l['id']}").json
        assert f["reference"] == l["reference"]
        assert f["resultat"]["probabilite_noyau"] == round(l["p_noyau"], 3)
        assert f["resultat"]["probabilite_ml"] == round(l["p_ml"], 3)
        assert len(f["resultat"]["facteurs_contributifs"]) == 5 and len(f["profil"]) == 13 and f["conseils"]
        assert f["verification"] is not None and set(f["verification"]) == {"noyau", "ml"}


def test_fiche_signale_les_variables_estimees_et_le_moment(client):
    fichier = pd.DataFrame([{k: v for k, v in PROFIL.items() if "2nd sem" not in k}]).to_csv(index=False).encode()
    r = televerser(client, fichier)
    ligne = client.get(f"/api/cohortes/{r.json['cohorte_id']}").json["lignes"][0]
    f = client.get(f"/api/etudiants/{ligne['id']}").json
    assert f["resultat"]["moment"] == "T1" and f["verification"] is None and f["devenir"] is None
    assert any(not p["fournie"] for p in f["profil"]) and f["resultat"]["nb_variables_estimees"] > 0
    assert f["resultat"]["probabilite_ml"] == round(ligne["p_ml"], 3)


def test_fiche_inconnue_et_acces_protege(client, app):
    assert client.get("/api/etudiants/999999").status_code == 404
    assert app.test_client().get("/api/etudiants/1").status_code == 401


# ---------------------------------------------------------------- explication du noyau par ses voisins
@pytest.mark.parametrize("moment", ["T0", "T1", "T2"])
def test_les_voisins_retrouvent_exactement_la_probabilite_du_noyau(moteur, contenu_jeu_de_test, moment):
    """Le calcul a la main (poids des etudiants ayant abandonne / poids total, sur les 3 197 etudiants
    du developpement) redonne la probabilite du modele, pour un echantillon d'etudiants de test."""
    import io
    from moteur.variables import semestre
    df = pd.read_csv(io.BytesIO(contenu_jeu_de_test), dtype=str, keep_default_na=False)
    valeurs, _ = moteur.nettoyer(df)
    if moment != "T2":
        valeurs[semestre("2nd")] = float("nan")
    if moment == "T0":
        valeurs[semestre("1st")] = float("nan")
    scores = moteur.scorer_valeurs(valeurs)
    assert set(scores["mode_calcul"]) == {moment}
    for i in valeurs.index[::25]:
        r = moteur.expliquer({c: valeurs.at[i, c] for c in valeurs.columns if not pd.isna(valeurs.at[i, c])})
        v = r["voisins_noyau"]
        assert r["moment"] == moment and v["nb_etudiants"] == 3197 and len(v["plus_proches"]) == 5
        assert abs(v["probabilite_recalculee"] - scores.at[i, "probabilite_noyau"]) < 1e-6
        assert 0 < v["poids_plus_proches"] <= 1 and 1 <= v["nombre_effectif"] <= 3197


def test_la_saisie_et_la_fiche_exposent_les_voisins(client):
    profil = {"Curricular units 1st sem (enrolled)": 6, "Curricular units 1st sem (approved)": 5,
              "Curricular units 1st sem (grade)": 13, "Tuition fees up to date": 1, "Age at enrollment": 19, "Course": 9119}
    r = client.post("/api/predict", json=profil).get_json()
    v = r["voisins_noyau"]
    assert r["moment"] == "T1" and v["nb_etudiants"] == 3197
    assert abs(v["probabilite_recalculee"] - r["probabilite_noyau"]) < 1e-3
    # seules les informations connues a la fin du 1er semestre sont montrees
    assert len(v["colonnes"]) == 4 and all(len(l["valeurs"]) == 4 for l in v["plus_proches"])
    client.post("/api/cohortes/jeu-de-test")
    fiche = client.get("/api/etudiants/1").get_json()
    assert fiche["resultat"]["voisins_noyau"]["nb_etudiants"] == 3197
