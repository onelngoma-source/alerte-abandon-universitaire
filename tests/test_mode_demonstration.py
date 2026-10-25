"""Mode demonstration : plusieurs visiteurs simultanes, cloisonnes et sans pouvoir destructeur.

Ce mode sert a la mise en ligne publique de l'application. Il garantit trois choses :
chaque visiteur ne voit que la cohorte de reference et ses propres imports, personne ne
peut supprimer la cohorte de reference, et personne ne peut vider la base.
"""
import importlib
import io
import os
import sys
import tempfile
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

RACINE = Path(__file__).resolve().parent.parent
FICHIER = RACINE / "data" / "jeu_de_test_1328.csv"


@pytest.fixture(scope="module")
def application():
    """Une application en mode demonstration, sur une base temporaire."""
    anciennes = {c: os.environ.get(c) for c in
                 ("MODE_DEMO", "DB_PATH", "FLASK_SECRET_KEY", "ADMIN_IDENTIFIANT", "ADMIN_MDP_HACHE")}
    os.environ.update({
        "MODE_DEMO": "1",
        "DB_PATH": tempfile.mktemp(suffix=".db"),
        "FLASK_SECRET_KEY": "test-mode-demo",
        "ADMIN_IDENTIFIANT": "jury",
        "ADMIN_MDP_HACHE": generate_password_hash("secret"),
    })
    for module in ("auth", "db", "volets.tableau", "volets.api_cohortes", "volets.import_csv", "app"):
        if module in sys.modules:
            importlib.reload(sys.modules[module])
    import app as module_app
    app = module_app.creer_application()
    app.config["TESTING"] = True
    yield app

    for cle, valeur in anciennes.items():
        if valeur is None:
            os.environ.pop(cle, None)
        else:
            os.environ[cle] = valeur
    for module in ("auth", "db", "volets.tableau", "volets.api_cohortes", "volets.import_csv", "app"):
        if module in sys.modules:
            importlib.reload(sys.modules[module])


def visiteur(application):
    client = application.test_client()
    client.post("/connexion", data={"identifiant": "jury", "mot_de_passe": "secret"})
    return client


def noms(client):
    return {c["nom"] for c in client.get("/api/cohortes").get_json()}


def importer(client, nom, lignes=60):
    entetes, *corps = FICHIER.read_text(encoding="utf-8").splitlines()
    contenu = "\n".join([entetes, *corps[:lignes]]).encode()
    return client.post("/api/import",
                       data={"fichier": (io.BytesIO(contenu), "extrait.csv"), "nom": nom},
                       content_type="multipart/form-data")


def test_les_visiteurs_partent_de_la_meme_cohorte(application):
    a, b, c = visiteur(application), visiteur(application), visiteur(application)
    for client in (a, b, c):
        assert any(x["origine"] == "test_uci" for x in client.get("/api/cohortes").get_json())


def test_les_imports_sont_cloisonnes(application):
    a, b, c = visiteur(application), visiteur(application), visiteur(application)
    assert importer(a, "Cohorte de A").status_code == 200
    assert importer(b, "Cohorte de B").status_code == 200

    assert "Cohorte de A" in noms(a) and "Cohorte de A" not in noms(b) and "Cohorte de A" not in noms(c)
    assert "Cohorte de B" in noms(b) and "Cohorte de B" not in noms(a)


def test_la_cohorte_partagee_reste_visible_de_tous(application):
    a, b = visiteur(application), visiteur(application)
    importer(a, "Un import de plus")
    for client in (a, b):
        assert any(x["origine"] == "test_uci" for x in client.get("/api/cohortes").get_json())


def test_la_cohorte_de_reference_ne_peut_pas_etre_supprimee(application):
    a = visiteur(application)
    partagee = next(x["id"] for x in a.get("/api/cohortes").get_json() if x["origine"] == "test_uci")
    assert a.delete(f"/api/cohortes/{partagee}").status_code == 403
    assert any(x["origine"] == "test_uci" for x in a.get("/api/cohortes").get_json())


def test_la_base_ne_peut_pas_etre_videe(application):
    assert visiteur(application).post("/api/cohortes/vider").status_code == 403


def test_un_visiteur_ne_supprime_pas_la_cohorte_d_un_autre(application):
    a, b = visiteur(application), visiteur(application)
    importer(a, "Cohorte protegee")
    identifiant = next(x["id"] for x in a.get("/api/cohortes").get_json() if x["nom"] == "Cohorte protegee")

    assert b.delete(f"/api/cohortes/{identifiant}").status_code == 403
    assert "Cohorte protegee" in noms(a)

    assert a.delete(f"/api/cohortes/{identifiant}").status_code == 200
    assert "Cohorte protegee" not in noms(a)


def test_un_visiteur_ne_lit_pas_la_cohorte_d_un_autre(application):
    a, b = visiteur(application), visiteur(application)
    importer(a, "Cohorte privee")
    identifiant = next(x["id"] for x in a.get("/api/cohortes").get_json() if x["nom"] == "Cohorte privee")
    assert a.get(f"/api/cohortes/{identifiant}").status_code == 200
    assert b.get(f"/api/cohortes/{identifiant}").status_code == 404


def test_la_prediction_individuelle_reste_accessible(application):
    """Le formulaire n'ecrit rien en base : il doit fonctionner pour tous, simultanement."""
    a = visiteur(application)
    reponse = a.post("/api/predict", json={
        "Curricular units 1st sem (enrolled)": 6, "Curricular units 1st sem (approved)": 2,
        "Curricular units 1st sem (evaluations)": 8, "Curricular units 1st sem (grade)": 9.5,
        "Course": 9254, "Age at enrollment": 24, "Scholarship holder": 0,
        "Debtor": 0, "Tuition fees up to date": 1, "Gender": 1,
    })
    assert reponse.status_code == 200
    assert "probabilite_noyau" in reponse.get_json()
