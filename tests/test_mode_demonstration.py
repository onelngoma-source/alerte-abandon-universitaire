"""Mode demonstration (mise en ligne pour le jury et le portfolio).

Il garantit : des comptes fictifs prets a l'emploi pour chaque role, un suivi deja engage sur les cohortes
2015 a 2017, et aucune operation destructrice ou d'administration des comptes.
"""
import pytest

from conftest import base_de_test, connecter


@pytest.fixture
def application(moteur, tmp_path, monkeypatch):
    monkeypatch.setenv("MODE_DEMO", "1")
    base_de_test(tmp_path, monkeypatch, "demo.db")
    monkeypatch.delenv("DEMO_PRELOAD", raising=False)
    from app import creer_application
    return creer_application(moteur=moteur)


def test_comptes_de_demonstration_et_page_de_connexion(application):
    page = application.test_client().get("/connexion").get_data(as_text=True)
    assert "Démonstration" in page and "conseiller1" in page
    for identifiant in ("admin", "responsable", "conseiller1", "conseiller2"):
        assert connecter(application, identifiant, "demo").get("/api/session").json["identifiant"] == identifiant


def test_le_suivi_est_deja_engage(application):
    responsable = connecter(application, "responsable", "demo")
    p = responsable.get("/api/pilotage").json
    statuts = {s["statut"]: s["nombre"] for s in p["par_statut"]}
    assert p["ouverts"] + p["clos"] == 455
    assert all(statuts[s] > 0 for s in ("a_contacter", "contacte", "entretien", "accompagnement", "clos"))
    assert p["delai_median_jours"] is not None and len(p["charge"]) == 2
    conseiller = connecter(application, "conseiller1", "demo")
    assert len(conseiller.get("/api/dossiers?vue=mes").json["dossiers"]) > 50


def test_rien_de_destructeur_en_demonstration(application):
    admin = connecter(application, "admin", "demo")
    promo = admin.get("/api/cohortes").json[0]["id"]
    assert admin.delete(f"/api/cohortes/{promo}").status_code == 403
    assert admin.post("/api/cohortes/vider").status_code == 403
    assert admin.post("/api/admin/utilisateurs", json={"identifiant": "x", "nom": "X", "role": "admin"}).status_code == 403
    assert admin.post("/api/admin/purge", json={"promotions": [promo]}).status_code == 403
    assert len(admin.get("/api/cohortes").json) == 1


def test_l_estimation_individuelle_reste_accessible(application):
    c = connecter(application, "conseiller2", "demo")
    r = c.post("/api/predict", json={"Age at enrollment": 20, "Course": 9500})
    assert r.status_code == 200 and r.json["moment"] == "T0"


def test_le_compte_du_jury_s_ajoute_aux_comptes_fictifs(moteur, tmp_path, monkeypatch):
    """La version en ligne garde le compte du jury, declare par variables d'environnement (carton QR)."""
    from werkzeug.security import generate_password_hash
    monkeypatch.setenv("MODE_DEMO", "1")
    monkeypatch.setenv("DEMO_PRELOAD", "0")
    monkeypatch.setenv("ADMIN_IDENTIFIANT", "jury")
    monkeypatch.setenv("ADMIN_MDP_HACHE", generate_password_hash("soutenance2026"))
    base_de_test(tmp_path, monkeypatch, "jury.db")
    from app import creer_application
    application = creer_application(moteur=moteur)
    assert connecter(application, "jury", "soutenance2026").get("/api/session").json["role"] == "admin"
    assert connecter(application, "conseiller1", "demo").get("/api/session").status_code == 200
