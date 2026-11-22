"""Raccordement au systeme de scolarite : imports automatiques par jeton de service ou par dossier de depot."""
import io

import pandas as pd
from sqlalchemy import func, select

import db
from outils import synchroniser


def _extrait(contenu_jeu_de_test, n=40) -> bytes:
    """Les n premiers etudiants du jeu de test, au format du gabarit d'import."""
    df = pd.read_csv(io.BytesIO(contenu_jeu_de_test), sep=None, engine="python", dtype=str)
    return df.head(n).to_csv(index=False).encode()


def _creer_jeton(client, nom="Logiciel de scolarité"):
    r = client.post("/api/admin/jetons", json={"nom": nom})
    assert r.status_code == 200
    return r.json["id"], r.json["jeton"]


def _envoyer(app, jeton, contenu, promotion="Licence 1 Informatique 2026-2027"):
    service = app.test_client()  # aucune session : seul le jeton authentifie
    return service.post("/api/v1/synchronisation", headers={"Authorization": f"Bearer {jeton}"},
                        data={"promotion": promotion, "fichier": (io.BytesIO(contenu), "l1.csv")},
                        content_type="multipart/form-data")


def test_un_jeton_permet_l_import_automatique_et_n_est_jamais_stocke(app, client, contenu_jeu_de_test):
    _, jeton = _creer_jeton(client)
    assert jeton.startswith("aap_") and len(jeton) > 40
    with db.connexion() as c:
        ligne = db.ligne(c.execute(select(db.jeton_service)))
    assert jeton not in str(ligne.values()) and ligne["prefixe"] == jeton[:12]

    r = _envoyer(app, jeton, _extrait(contenu_jeu_de_test))
    assert r.status_code == 200, r.json
    assert r.json["effectif"] == 40 and r.json["nouveaux"] == 40
    # renvoyer le meme fichier (le systeme de scolarite relance son export) ne cree aucun doublon
    r = _envoyer(app, jeton, _extrait(contenu_jeu_de_test))
    assert r.json["nouveaux"] == 0 and r.json["mis_a_jour"] == 40
    with db.connexion() as c:
        assert c.execute(select(func.count()).select_from(db.etudiant)).scalar() == 40
        journal = db.lignes(c.execute(select(db.journal.c.identifiant).where(db.journal.c.action == "synchronisation")))
    assert [j["identifiant"] for j in journal] == ["jeton:Logiciel de scolarité"] * 2
    assert client.get("/api/admin/jetons").json["jetons"][0]["derniere_utilisation"]


def test_corps_brut_avec_la_promotion_dans_l_adresse(app, client, contenu_jeu_de_test):
    _, jeton = _creer_jeton(client)
    r = app.test_client().post("/api/v1/synchronisation?promotion=Master%201%20Big%20Data",
                               headers={"Authorization": f"Bearer {jeton}", "Content-Type": "text/csv"},
                               data=_extrait(contenu_jeu_de_test, 10))
    assert r.status_code == 200 and r.json["effectif"] == 10


def test_jeton_absent_faux_ou_revoque_refuse(app, client, contenu_jeu_de_test):
    identifiant, jeton = _creer_jeton(client)
    contenu = _extrait(contenu_jeu_de_test, 5)
    assert _envoyer(app, None, contenu).status_code == 401
    assert _envoyer(app, "aap_" + "x" * 43, contenu).status_code == 401
    assert client.post(f"/api/admin/jetons/{identifiant}/revocation", json={}).status_code == 200
    r = _envoyer(app, jeton, contenu)
    assert r.status_code == 401 and r.headers["WWW-Authenticate"] == "Bearer"
    with db.connexion() as c:
        assert c.execute(select(func.count()).select_from(db.etudiant)).scalar() == 0


def test_essais_de_jetons_en_serie_bloques(app, contenu_jeu_de_test):
    contenu = _extrait(contenu_jeu_de_test, 5)
    for _ in range(5):
        _envoyer(app, "aap_devine", contenu)
    assert _envoyer(app, "aap_devine", contenu).status_code == 429


def test_fichier_mal_forme_refuse_avec_explication(app, client):
    _, jeton = _creer_jeton(client)
    r = _envoyer(app, jeton, b"nom;prenom\nNdong;Paul\n")
    assert r.status_code == 400 and "gabarit" in r.json["erreur"]


def test_seul_l_administrateur_gere_les_jetons(app, client):
    client.post("/api/admin/utilisateurs", json={"identifiant": "resp", "nom": "Resp", "role": "responsable"})
    from werkzeug.security import generate_password_hash
    with db.connexion() as c:
        c.execute(db.utilisateur.update().where(db.utilisateur.c.identifiant == "resp")
                  .values(mdp_hache=generate_password_hash("motdepasse-42"), doit_changer_mdp=False))
    from conftest import connecter
    responsable = connecter(app, "resp", "motdepasse-42")
    assert responsable.post("/api/admin/jetons", json={"nom": "x"}).status_code == 403
    assert responsable.get("/api/admin/jetons").status_code == 403


def test_depot_de_fichiers_traite_puis_range(app, tmp_path, moteur, contenu_jeu_de_test):
    depot = tmp_path / "depot"
    depot.mkdir()
    (depot / "Licence 2 Gestion 2026-2027.csv").write_bytes(_extrait(contenu_jeu_de_test, 25))
    (depot / "Fichier illisible.csv").write_bytes(b"a;b\n1;2\n")
    bilan = synchroniser.traiter(depot, moteur)
    assert [i["fichier"] for i in bilan["importes"]] == ["Licence 2 Gestion 2026-2027.csv"]
    assert bilan["importes"][0]["effectif"] == 25
    assert len(bilan["refuses"]) == 1
    assert not list(depot.glob("*.csv"))  # le depot est vide : rien ne sera importe deux fois
    assert len(list((depot / "traites").glob("*.csv"))) == 1
    assert len(list((depot / "erreurs").glob("*.txt"))) == 1
    with db.connexion() as c:
        assert c.execute(select(db.promotion.c.nom)).scalars().all() == ["Licence 2 Gestion 2026-2027"]
