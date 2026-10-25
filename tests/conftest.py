import io
import os
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.chdir(RACINE)

from moteur.scoring import Moteur  # noqa: E402


@pytest.fixture(scope="session")
def moteur():
    return Moteur()


@pytest.fixture
def app(moteur, tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DEMO_PRELOAD", "0")  # les tests partent d'une base vide
    from app import creer_application
    return creer_application(moteur=moteur)


@pytest.fixture
def client(app):
    c = app.test_client()
    assert c.post("/connexion", data={"identifiant": "admin", "mot_de_passe": "changez-moi"}).status_code == 302
    return c


@pytest.fixture(scope="session")
def contenu_jeu_de_test():
    return (RACINE / "data" / "jeu_de_test_1328.csv").read_bytes()


def televerser(client, contenu: bytes, nom="fichier.csv", **champs):
    donnees = {"fichier": (io.BytesIO(contenu), nom), **champs}
    return client.post("/api/import", data=donnees, content_type="multipart/form-data")


def lignes_sans_id(client, cohorte_id):
    d = client.get(f"/api/cohortes/{cohorte_id}").json
    return [{k: v for k, v in ligne.items() if k != "id"} for ligne in d["lignes"]], d


@pytest.fixture
def app_prechargee(moteur, tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "precharge.db"))
    monkeypatch.delenv("DEMO_PRELOAD", raising=False)
    from app import creer_application
    return creer_application(moteur=moteur)
