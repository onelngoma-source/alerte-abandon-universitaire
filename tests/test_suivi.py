"""Outil operationnel : regles d'alerte, suivi des dossiers, roles, securite, pilotage, surveillance."""
import io

import pandas as pd
from sqlalchemy import func, select

import db
from conftest import RACINE, connecter, televerser


def creer_compte(admin, identifiant, role, nom=None):
    r = admin.post("/api/admin/utilisateurs", json={"identifiant": identifiant, "nom": nom or identifiant.title(), "role": role})
    assert r.status_code == 200, r.json
    mdp = r.json["mot_de_passe_provisoire"]
    return r.json["id"], mdp


def activer(app, identifiant, mdp):
    """Premiere connexion : le changement de mot de passe est impose avant tout le reste."""
    c = connecter(app, identifiant, mdp)
    assert c.get("/api/cohortes").status_code == 403
    assert c.post("/api/compte/mot-de-passe", json={"actuel": mdp, "nouveau": "nouveau-mdp-2026"}).status_code == 200
    return connecter(app, identifiant, "nouveau-mdp-2026")


def promotion_test(client, contenu, nom="Licence 1"):
    df = pd.read_csv(io.BytesIO(contenu), dtype=str).head(120)
    return televerser(client, df.to_csv(index=False).encode(), "promo.csv", nom=nom).json


def test_un_dossier_s_ouvre_pour_chaque_alerte_et_un_seul(client, contenu_jeu_de_test):
    r = promotion_test(client, contenu_jeu_de_test)
    lignes = client.get(f"/api/cohortes/{r['cohorte_id']}").json["lignes"]
    alertes = [l for l in lignes if round(l["p_ml"], 3) >= round(1 / 6, 3)]
    assert r["dossiers_ouverts"] == len(alertes) > 0
    assert all(l["dossier_statut"] == "a_contacter" for l in alertes)
    assert all(l["dossier_statut"] is None for l in lignes if l not in alertes)
    # re-importer le meme fichier dans la meme promotion : memes etudiants, pas de nouveau dossier
    df = pd.read_csv(io.BytesIO(contenu_jeu_de_test), dtype=str).head(120)
    r2 = client.post("/api/import", data={"fichier": (io.BytesIO(df.to_csv(index=False).encode()), "promo.csv"),
                                          "promotion": r["cohorte_id"]}, content_type="multipart/form-data").json
    assert r2["nouveaux"] == 0 and r2["mis_a_jour"] == 120 and r2["dossiers_ouverts"] == 0
    with db.connexion() as c:
        assert c.execute(select(func.count()).select_from(db.evaluation)).scalar() == 240


def test_le_premier_semestre_met_a_jour_les_memes_etudiants(client, contenu_jeu_de_test):
    """Inscription puis 1er semestre : un seul etudiant, deux estimations, un historique."""
    from moteur.referentiels import CHAMPS_FORMULAIRE
    df = pd.read_csv(io.BytesIO(contenu_jeu_de_test), dtype=str).head(60)
    inscription = df[["Reference"] + [c for c in CHAMPS_FORMULAIRE if "sem" not in c]]
    r = televerser(client, inscription.to_csv(index=False).encode(), "t0.csv", nom="Promo 2026").json
    assert r["par_moment"]["T0"] == 60
    s1 = df[["Reference"] + [c for c in CHAMPS_FORMULAIRE if "2nd sem" not in c]]
    r2 = client.post("/api/import", data={"fichier": (io.BytesIO(s1.to_csv(index=False).encode()), "t1.csv"),
                                          "promotion": r["cohorte_id"]}, content_type="multipart/form-data").json
    assert r2["nouveaux"] == 0 and r2["mis_a_jour"] == 60 and r2["par_moment"]["T1"] == 60
    lignes = client.get(f"/api/cohortes/{r['cohorte_id']}").json["lignes"]
    assert len(lignes) == 60 and {l["mode"] for l in lignes} == {"T1"}
    fiche = client.get(f"/api/etudiants/{lignes[0]['id']}").json
    assert [h["moment"] for h in fiche["historique"]] == ["T0", "T1"]


def test_parcours_complet_d_un_dossier(app, client, contenu_jeu_de_test):
    r = promotion_test(client, contenu_jeu_de_test)
    cid, mdp = creer_compte(client, "c.essono", "conseiller")
    conseiller = activer(app, "c.essono", mdp)
    dossiers = conseiller.get("/api/dossiers?vue=non_attribues").json["dossiers"]
    assert len(dossiers) == r["dossiers_ouverts"]
    d = dossiers[0]
    # le conseiller le prend en charge en agissant dessus
    assert conseiller.post(f"/api/dossiers/{d['id']}/actions", json={"type": "appel", "texte": "Appel passé, RDV mardi."}).status_code == 200
    mes = conseiller.get("/api/dossiers?vue=mes").json["dossiers"]
    assert [x["id"] for x in mes] == [d["id"]]
    for statut in ("contacte", "entretien", "accompagnement"):
        assert conseiller.post(f"/api/dossiers/{d['id']}/statut", json={"statut": statut}).json["statut"] == statut
    assert conseiller.post(f"/api/dossiers/{d['id']}/cloture", json={"motif": "inconnu"}).status_code == 400
    assert conseiller.post(f"/api/dossiers/{d['id']}/cloture", json={"motif": "accompagnement_termine"}).json["statut"] == "clos"
    fiche = conseiller.get(f"/api/etudiants/{d['etudiant_id']}").json
    assert fiche["dossier"] is None and len(fiche["dossiers_clos"]) == 1
    with db.connexion() as c:
        types = [a["type"] for a in db.lignes(c.execute(select(db.action.c.type).where(db.action.c.dossier_id == d["id"])
                                                        .order_by(db.action.c.id)))]
        dossier = db.ligne(c.execute(select(db.dossier).where(db.dossier.c.id == d["id"])))
    assert types == ["ouverture", "appel", "statut", "statut", "statut", "cloture"]
    assert dossier["premier_contact_le"] is not None and dossier["conseiller_id"] == cid


def test_un_conseiller_ne_touche_pas_au_dossier_d_un_autre(app, client, contenu_jeu_de_test):
    promotion_test(client, contenu_jeu_de_test)
    id_a, mdp_a = creer_compte(client, "conseiller.a", "conseiller")
    _, mdp_b = creer_compte(client, "conseiller.b", "conseiller")
    a, b = activer(app, "conseiller.a", mdp_a), activer(app, "conseiller.b", mdp_b)
    d = a.get("/api/dossiers?vue=non_attribues").json["dossiers"][0]
    assert client.post(f"/api/dossiers/{d['id']}/attribution", json={"conseiller_id": id_a}).status_code == 200
    assert b.post(f"/api/dossiers/{d['id']}/statut", json={"statut": "contacte"}).status_code == 403
    assert b.post(f"/api/dossiers/{d['id']}/attribution", json={"conseiller_id": id_a}).status_code == 403
    assert a.post(f"/api/dossiers/{d['id']}/statut", json={"statut": "contacte"}).status_code == 200
    # roles : un conseiller n'importe pas, ne pilote pas, n'administre pas
    assert a.get("/api/pilotage").status_code == 403
    assert a.get("/api/admin/utilisateurs").status_code == 403
    assert a.post("/api/import", data={}, content_type="multipart/form-data").status_code == 403


def test_une_hausse_du_risque_signale_le_dossier_et_une_cloture_n_est_pas_rouverte_pour_rien(client):
    profil = {"Reference": "M-1", "Curricular units 1st sem (enrolled)": 6, "Curricular units 1st sem (approved)": 5,
              "Curricular units 1st sem (grade)": 12, "Tuition fees up to date": 1, "Debtor": 0, "Age at enrollment": 19,
              "Course": 9147}
    r = televerser(client, pd.DataFrame([profil]).to_csv(index=False).encode(), "un.csv", nom="P").json
    etudiant = client.get(f"/api/cohortes/{r['cohorte_id']}").json["lignes"][0]
    assert etudiant["dossier_statut"] is None or etudiant["p_ml"] >= 1 / 6
    # resultats du 1er semestre qui se degradent, saisis sur la fiche
    f = client.post(f"/api/etudiants/{etudiant['id']}/evaluations",
                    json={"Curricular units 1st sem (approved)": 1, "Tuition fees up to date": 0, "Debtor": 1}).json
    assert f["dossier"] is not None and f["dossier"]["statut"] == "a_contacter"
    p_ouverture = f["resultat"]["probabilite_ml"]
    d = f["dossier"]["id"]
    client.post(f"/api/dossiers/{d}/cloture", json={"motif": "risque_ecarte"})
    # meme niveau de risque a l'estimation suivante : pas de nouveau dossier
    f = client.post(f"/api/etudiants/{etudiant['id']}/evaluations", json={"Curricular units 1st sem (grade)": 11}).json
    assert f["dossier"] is None and abs(f["resultat"]["probabilite_ml"] - p_ouverture) < 0.10
    assert len(f["historique"]) == 3


def test_securite_csrf_verrouillage_et_journal(app, client):
    sans_jeton = app.test_client()
    sans_jeton.post("/connexion", data={"identifiant": "admin", "mot_de_passe": "changez-moi"})
    assert sans_jeton.post("/api/admin/utilisateurs", json={"identifiant": "x", "nom": "X", "role": "conseiller"}).status_code == 400
    intrus = app.test_client()
    for _ in range(5):
        intrus.post("/connexion", data={"identifiant": "admin", "mot_de_passe": "faux"})
    r = intrus.post("/connexion", data={"identifiant": "admin", "mot_de_passe": "changez-moi"})
    assert r.status_code == 200 and "Trop de tentatives" in r.get_data(as_text=True)
    with db.connexion() as c:
        actions = {l["action"] for l in db.lignes(c.execute(select(db.journal.c.action)))}
    assert {"connexion", "echec_connexion"} <= actions
    journal = client.get("/api/admin/journal").json
    assert journal["lignes"] and journal["lignes"][0]["libelle"]


def test_mot_de_passe_trop_faible_refuse_et_dernier_admin_protege(app, client):
    uid, mdp = creer_compte(client, "r.nguema", "responsable")
    c = connecter(app, "r.nguema", mdp)
    assert c.post("/api/compte/mot-de-passe", json={"actuel": mdp, "nouveau": "court1"}).status_code == 400
    assert c.post("/api/compte/mot-de-passe", json={"actuel": mdp, "nouveau": "seulementdeslettres"}).status_code == 400
    admin_id = client.get("/api/session").json and [u for u in client.get("/api/admin/utilisateurs").json if u["role"] == "admin"][0]["id"]
    assert client.post(f"/api/admin/utilisateurs/{admin_id}", json={"role": "conseiller"}).status_code == 400
    # un compte desactive perd sa session et ses dossiers redeviennent non attribues
    assert client.post(f"/api/admin/utilisateurs/{uid}", json={"actif": False}).status_code == 200
    assert c.get("/api/cohortes").status_code == 401


def test_pilotage_et_surveillance(client):
    client.post("/api/cohortes/jeu-de-test")
    p = client.get("/api/pilotage").json
    assert p["ouverts"] == 455 and p["non_attribues"] == 455 and p["en_retard"] == 0
    s = client.get("/api/surveillance").json
    t2 = next(m for m in s["demonstration"]["moments"] if m["moment"] == "T2")
    assert t2["suffisant"] and abs(t2["auc"] - 0.9019) < 1e-3 and t2["signaux"] == []
    assert s["etablissement"]["devenirs_connus"] == 0


def test_export_csv_de_la_file(client, contenu_jeu_de_test):
    r = promotion_test(client, contenu_jeu_de_test)
    texte = client.get(f"/api/cohortes/{r['cohorte_id']}/export.csv").get_data(as_text=True)
    lignes = texte.strip().splitlines()
    assert lignes[0].lstrip("﻿").startswith("Rang;Matricule") and len(lignes) == 121
    assert client.get("/api/dossiers/export.csv?vue=ouverts").status_code == 200


def test_rappels_par_courriel(app, client, contenu_jeu_de_test):
    from outils.rappels import preparer
    promotion_test(client, contenu_jeu_de_test)
    uid, _ = creer_compte(client, "c.mintsa", "conseiller")
    client.post(f"/api/admin/utilisateurs/{uid}", json={"email": "c.mintsa@exemple.ga"})
    d = client.get("/api/dossiers?vue=non_attribues").json["dossiers"][0]
    client.post(f"/api/dossiers/{d['id']}/attribution", json={"conseiller_id": uid})
    client.post(f"/api/dossiers/{d['id']}/echeance", json={"echeance": "2020-01-01"})
    messages = preparer()
    assert len(messages) == 1 and messages[0]["To"] == "c.mintsa@exemple.ga"
    corps = messages[0].get_content()
    assert d["matricule"] in corps and "en retard" in corps and "Frais" not in corps


def test_recalibration_sur_l_etablissement(tmp_path, monkeypatch, moteur):
    """Une correction de Platt change le niveau des probabilites, jamais l'ordre des etudiants."""
    import joblib
    import numpy as np
    from moteur.scoring import Moteur
    chemin = tmp_path / "recal.joblib"
    joblib.dump({"parametres": {"T2": (-0.5, 0.9)}, "date": "01/07/2027", "effectif": 800, "fichier": "x.csv"}, chemin)
    monkeypatch.setenv("RECALIBRATION", str(chemin))
    recal = Moteur()
    df = pd.read_csv(RACINE / "data" / "jeu_de_test_2015_2017.csv", dtype=str, keep_default_na=False).head(200)
    p0 = moteur.scorer(df)["probabilite_ml"].to_numpy()
    p1 = recal.scorer(df)["probabilite_ml"].to_numpy()
    assert not np.allclose(p0, p1) and (np.argsort(p0, kind="stable") == np.argsort(p1, kind="stable")).mean() > 0.99
    assert "recalibré le 01/07/2027" in recal.version and "recalibré" not in moteur.version
