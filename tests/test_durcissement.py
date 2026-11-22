"""Durcissement pour la production : migrations du schema, verrouillage de connexion partage, cle de session stable.

Chaque test correspond a une exigence de la passation (voir docs/PASSATION.md, section « Ce que les tests prouvent »)."""
import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, func, inspect, select, text
from werkzeug.security import generate_password_hash

import db
from conftest import base_de_test, connecter


def _nouvelle_application(moteur, monkeypatch, **env):
    monkeypatch.setenv("DEMO_PRELOAD", "0")
    monkeypatch.setenv("ADMIN_MDP_HACHE", generate_password_hash("changez-moi"))
    for cle, valeur in env.items():
        monkeypatch.setenv(cle, valeur)
    from app import creer_application
    return creer_application(moteur=moteur)


# ------------------------------------------------------------------ migrations
def test_les_migrations_produisent_exactement_le_schema_du_code(app):
    """Le schema obtenu par les migrations est identique a celui decrit dans db.py : aucune difference oubliee."""
    with db.moteur_bd().connect() as c:
        differences = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), db.meta)
        revision = MigrationContext.configure(c).get_current_revision()
    assert differences == []
    assert revision == db.revision_schema() and revision is not None


def test_une_base_d_avant_les_migrations_est_reprise_sans_perte(moteur, tmp_path, monkeypatch):
    """Base creee par une version precedente (sans historique de migrations) : elle est reconnue, completee,
    et ses donnees restent intactes."""
    base_de_test(tmp_path, monkeypatch, "ancienne.db")
    from alembic import command
    ancien = create_engine(db.url_base())
    with ancien.begin() as c:
        command.upgrade(db.config_migrations(c), db.REVISION_DE_REFERENCE)
        c.execute(text("DROP TABLE alembic_version"))  # comme une base creee par create_all
        c.execute(db.promotion.insert().values(nom="Promotion 2025", origine="etablissement", cree_le=db.maintenant()))
    ancien.dispose()

    _nouvelle_application(moteur, monkeypatch)
    with db.connexion() as c:
        tables = set(inspect(c).get_table_names())
        noms = [r.nom for r in c.execute(select(db.promotion.c.nom))]
    assert {"echec_connexion", "parametre", "jeton_service", "alembic_version"} <= tables
    assert noms == ["Promotion 2025"]


def test_redemarrer_ne_rejoue_pas_les_migrations(app, moteur, monkeypatch):
    revision = db.revision_schema()
    with db.connexion() as c:
        c.execute(db.promotion.insert().values(nom="Gardee", origine="etablissement", cree_le=db.maintenant()))
    _nouvelle_application(moteur, monkeypatch)
    with db.connexion() as c:
        assert c.execute(select(func.count()).select_from(db.promotion)).scalar() == 1
    assert db.revision_schema() == revision


# ------------------------------------------------------------------ verrouillage de connexion
def _tenter(client, identifiant, mdp, **entetes):
    return client.post("/connexion", data={"identifiant": identifiant, "mot_de_passe": mdp}, headers=entetes)


def test_le_verrouillage_survit_a_un_redemarrage_et_vaut_pour_tous_les_processus(app, moteur, monkeypatch):
    intrus = app.test_client()
    for _ in range(5):
        _tenter(intrus, "admin", "faux")
    # un autre processus du serveur (ou le meme apres redemarrage) voit les memes echecs : ils sont en base
    autre = _nouvelle_application(moteur, monkeypatch).test_client()
    r = _tenter(autre, "admin", "changez-moi")
    assert "Trop de tentatives" in r.get_data(as_text=True)
    with db.connexion() as c:
        assert c.execute(select(func.count()).select_from(db.echec_connexion)).scalar() == 5
        actions = {r.action for r in c.execute(select(db.journal.c.action))}
    assert "connexion_bloquee" in actions


def test_un_en_tete_falsifie_ne_contourne_pas_le_verrouillage(app):
    """Sans proxy declare, X-Forwarded-For est ignore : changer d'adresse pretendue ne remet pas le compteur a zero."""
    intrus = app.test_client()
    for i in range(5):
        _tenter(intrus, "admin", "faux", **{"X-Forwarded-For": f"10.0.0.{i}"})
    r = _tenter(intrus, "admin", "changez-moi", **{"X-Forwarded-For": "10.9.9.9"})
    assert "Trop de tentatives" in r.get_data(as_text=True)


def test_un_compte_vise_depuis_plusieurs_adresses_est_protege(moteur, tmp_path, monkeypatch):
    """Derriere un proxy de confiance, chaque adresse reelle compte a part ; mais 10 echecs sur un meme
    identifiant, d'ou qu'ils viennent, bloquent ce compte pour un quart d'heure."""
    base_de_test(tmp_path, monkeypatch, "proxy.db")
    application = _nouvelle_application(moteur, monkeypatch, PROXYS_DE_CONFIANCE="1")
    intrus = application.test_client()
    for i in range(10):
        _tenter(intrus, "Admin ", "faux", **{"X-Forwarded-For": f"10.0.1.{i}"})  # casse et espaces : meme compte
    r = _tenter(intrus, "admin", "changez-moi", **{"X-Forwarded-For": "10.0.2.1"})
    assert "Trop de tentatives" in r.get_data(as_text=True)
    # un autre compte, depuis une adresse saine, reste accessible
    with db.connexion() as c:
        c.execute(db.utilisateur.insert().values(identifiant="c.ndong", nom="C. Ndong", role="conseiller",
                                                 mdp_hache=generate_password_hash("motdepasse-42"), actif=True,
                                                 doit_changer_mdp=False, cree_le=db.maintenant()))
    assert _tenter(intrus, "c.ndong", "motdepasse-42", **{"X-Forwarded-For": "10.0.3.1"}).status_code == 302
    with db.connexion() as c:
        adresses = {r.adresse for r in c.execute(select(db.echec_connexion.c.adresse))}
    assert "10.0.1.3" in adresses  # l'adresse reelle du visiteur, reprise par ProxyFix


def test_une_connexion_reussie_efface_les_echecs(app):
    utilisateur = app.test_client()
    for _ in range(3):
        _tenter(utilisateur, "admin", "faux")
    assert _tenter(utilisateur, "admin", "changez-moi").status_code == 302
    with db.connexion() as c:
        assert c.execute(select(func.count()).select_from(db.echec_connexion)).scalar() == 0


# ------------------------------------------------------------------ cle de session
def test_la_cle_de_session_est_stable_entre_processus(app, moteur, monkeypatch):
    """Sans FLASK_SECRET_KEY, la cle est tiree une fois et gardee en base : une session ouverte sur un processus
    reste valable sur un autre, et apres un redemarrage."""
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    client = connecter(app)
    autre = _nouvelle_application(moteur, monkeypatch)
    assert autre.secret_key == app.secret_key
    cookie = client.get_cookie("session")
    second = autre.test_client()
    second.set_cookie("session", cookie.value)
    assert second.get("/api/session").status_code == 200


@pytest.mark.parametrize("valeur", ["une-cle-fournie-par-l-hebergeur"])
def test_la_cle_fournie_par_l_environnement_prime(moteur, tmp_path, monkeypatch, valeur):
    base_de_test(tmp_path, monkeypatch, "cle.db")
    application = _nouvelle_application(moteur, monkeypatch, FLASK_SECRET_KEY=valeur)
    assert application.secret_key == valeur


# ------------------------------------------------------------------ en-tetes de securite et supervision
def test_en_tetes_de_securite_et_nonce_de_script(client):
    r = client.get("/tableau")
    csp = r.headers["Content-Security-Policy"]
    nonce = csp.split("'nonce-")[1].split("'")[0]
    page = r.get_data(as_text=True)
    assert f'<script nonce="{nonce}">' in page  # les scripts en ligne de la page portent le nonce de CETTE requete
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    autre = client.get("/tableau").headers["Content-Security-Policy"]
    assert autre != csp  # un nonce neuf a chaque requete
    assert client.get("/api/cohortes").headers["Cache-Control"] == "no-store"


def test_hsts_en_https(moteur, tmp_path, monkeypatch):
    base_de_test(tmp_path, monkeypatch, "hsts.db")
    application = _nouvelle_application(moteur, monkeypatch, COOKIE_SECURISE="1")
    assert "max-age=31536000" in application.test_client().get("/connexion").headers["Strict-Transport-Security"]


def test_sonde_de_sante_sans_donnee_personnelle(app, monkeypatch, tmp_path):
    r = app.test_client().get("/sante")
    assert r.status_code == 200
    assert r.json == {"etat": "ok", "base": True, "schema_a_jour": True, "sauvegarde": None}
    from outils import sauvegarde
    sauvegarde.main(["creer", "--dossier", str(tmp_path / "s"), "--verifier"])
    s = app.test_client().get("/sante").json["sauvegarde"]
    assert s["verifiee"] and s["recente"] and s["age_heures"] < 1


def test_console_de_secours_pour_la_direction_informatique(app, capsys):
    from outils import comptes
    intrus = app.test_client()
    for _ in range(10):
        _tenter(intrus, "admin", "faux")
    assert comptes.main(["reinitialiser", "admin"]) == 0
    provisoire = capsys.readouterr().out.split(" : ")[1].split()[0]
    with db.connexion() as c:
        c.execute(db.echec_connexion.delete())  # l'adresse du test reste sinon bloquee par ses propres essais
    r = _tenter(app.test_client(), "admin", provisoire)
    assert r.status_code == 302 and r.headers["Location"].endswith("/compte")  # changement impose
    assert comptes.main(["reinitialiser", "inconnu"]) == 2
    with db.connexion() as c:
        assert c.execute(select(db.journal.c.identifiant).where(db.journal.c.action == "reinitialisation_mdp")).scalar() == "console"
