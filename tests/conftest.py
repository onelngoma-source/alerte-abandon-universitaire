import io
import os
import sys
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.chdir(RACINE)

from moteur.scoring import Moteur  # noqa: E402


@pytest.fixture(scope="session")
def moteur():
    return Moteur()


def base_de_test(tmp_path, monkeypatch, nom="test.db"):
    """SQLite par defaut. Avec TEST_DATABASE_URL (PostgreSQL), la meme base est videe avant chaque test."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        monkeypatch.setenv("DATABASE_URL", url)
        import db
        from sqlalchemy import create_engine
        moteur_bd = create_engine(db.url_base())
        db.meta.drop_all(moteur_bd)
        moteur_bd.dispose()
    else:
        monkeypatch.setenv("DB_PATH", str(tmp_path / nom))
        monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture
def app(moteur, tmp_path, monkeypatch):
    base_de_test(tmp_path, monkeypatch)
    monkeypatch.setenv("DEMO_PRELOAD", "0")  # les tests partent d'une base vide
    monkeypatch.setenv("ADMIN_MDP_HACHE", generate_password_hash("changez-moi"))
    from app import creer_application
    return creer_application(moteur=moteur)


def connecter(application, identifiant="admin", mot_de_passe="changez-moi"):
    """Un client connecte, qui envoie le jeton anti-CSRF avec chaque requete."""
    c = application.test_client()
    assert c.post("/connexion", data={"identifiant": identifiant, "mot_de_passe": mot_de_passe}).status_code == 302
    c.environ_base["HTTP_X_CSRF_TOKEN"] = c.get("/api/session").json["csrf"]
    return c


@pytest.fixture
def client(app):
    return connecter(app)


@pytest.fixture(scope="session")
def contenu_jeu_de_test():
    return (RACINE / "data" / "jeu_de_test_2015_2017.csv").read_bytes()


def televerser(client, contenu: bytes, fichier="fichier.csv", **champs):
    donnees = {"fichier": (io.BytesIO(contenu), fichier), **champs}
    return client.post("/api/import", data=donnees, content_type="multipart/form-data")


def lignes_sans_id(client, cohorte_id):
    """Les identifiants (etudiant, dossier) sont des cles de base propres a chaque promotion : on les retire."""
    d = client.get(f"/api/cohortes/{cohorte_id}").json
    return [{k: v for k, v in ligne.items() if k not in ("id", "dossier_id")} for ligne in d["lignes"]], d


@pytest.fixture
def app_prechargee(moteur, tmp_path, monkeypatch):
    base_de_test(tmp_path, monkeypatch, "precharge.db")
    monkeypatch.delenv("DEMO_PRELOAD", raising=False)
    monkeypatch.setenv("ADMIN_MDP_HACHE", generate_password_hash("changez-moi"))
    from app import creer_application
    return creer_application(moteur=moteur)
