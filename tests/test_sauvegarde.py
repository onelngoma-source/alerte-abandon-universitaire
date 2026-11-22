"""Sauvegarde et restauration : une sauvegarde ne compte que si elle se restaure a l'identique, et toute
alteration du fichier est detectee."""
import gzip
import json
import os

import pytest
from sqlalchemy import create_engine, func, select

import db
from outils import sauvegarde


@pytest.fixture
def base_remplie(app_prechargee, client_precharge):
    """1 227 etudiants (jeu de test), avec un dossier suivi et une action, pour couvrir toutes les tables."""
    lignes = client_precharge.get("/api/cohortes/1").json["lignes"]
    etudiant = lignes[0]["id"]
    client_precharge.post(f"/api/etudiants/{etudiant}/dossier", json={})
    with db.connexion() as c:
        dossier_id = c.execute(select(db.dossier.c.id).where(db.dossier.c.etudiant_id == etudiant)).scalar()
    client_precharge.post(f"/api/dossiers/{dossier_id}/actions", json={"type": "appel", "texte": "Appel : rendez-vous fixé lundi, « é » ✓"})
    return db.moteur_bd()


@pytest.fixture
def client_precharge(app_prechargee):
    from conftest import connecter
    return connecter(app_prechargee)


def _moteur_vide(tmp_path, nom="cible.db"):
    return create_engine(f"sqlite:///{tmp_path / nom}")


def test_la_sauvegarde_se_restaure_a_l_identique(base_remplie, tmp_path):
    fichier = tmp_path / "s.sauvegarde"
    entete = sauvegarde.creer(base_remplie, fichier)
    assert entete["tables"]["etudiant"]["lignes"] == 1227 and entete["tables"]["action"]["lignes"] >= 1
    assert oct(fichier.stat().st_mode)[-3:] == "600"  # lisible par le seul compte du service

    bilan = sauvegarde.verifier(fichier)
    assert bilan["lignes"] == sum(t["lignes"] for t in entete["tables"].values())

    cible = _moteur_vide(tmp_path)
    sauvegarde.restaurer(fichier, cible)
    assert sauvegarde.empreintes(cible) == sauvegarde.empreintes(base_remplie)


def test_une_valeur_modifiee_dans_le_fichier_est_detectee(base_remplie, tmp_path):
    fichier = tmp_path / "s.sauvegarde"
    sauvegarde.creer(base_remplie, fichier)
    lignes = gzip.decompress(fichier.read_bytes()).decode().splitlines()
    for i, brute in enumerate(lignes[1:], start=1):
        r = json.loads(brute)
        if r["t"] == "etudiant":
            r["l"]["probabilite"] = 0.01  # quelqu'un « baisse » un risque dans la sauvegarde
            lignes[i] = json.dumps(r)
            break
    fichier.write_bytes(gzip.compress(("\n".join(lignes) + "\n").encode()))
    with pytest.raises(sauvegarde.SauvegardeInvalide, match="non conforme pour : etudiant"):
        sauvegarde.verifier(fichier)


def test_un_fichier_tronque_est_detecte(base_remplie, tmp_path):
    fichier = tmp_path / "s.sauvegarde"
    sauvegarde.creer(base_remplie, fichier)
    fichier.write_bytes(fichier.read_bytes()[:-200])
    with pytest.raises(sauvegarde.SauvegardeInvalide):
        sauvegarde.verifier(fichier)


def test_sauvegarde_chiffree_et_scellee(base_remplie, tmp_path):
    cle = sauvegarde.nouvelle_cle()
    fichier = tmp_path / "s.sauvegarde"
    sauvegarde.creer(base_remplie, fichier, cle=cle)
    contenu = fichier.read_bytes()
    assert contenu.startswith(b"gAAAAA")  # jeton Fernet : rien de lisible sans la cle
    with pytest.raises(OSError):
        gzip.decompress(contenu)
    assert sauvegarde.verifier(fichier, cle=cle)["lignes"] > 1227
    with pytest.raises(sauvegarde.SauvegardeInvalide, match="SAUVEGARDE_CLE"):
        sauvegarde.verifier(fichier, cle="")
    with pytest.raises(sauvegarde.SauvegardeInvalide, match="clé incorrecte"):
        sauvegarde.verifier(fichier, cle=sauvegarde.nouvelle_cle())
    altere = bytearray(contenu)
    altere[len(altere) // 2] ^= 1  # un seul bit change
    fichier.write_bytes(bytes(altere))
    with pytest.raises(sauvegarde.SauvegardeInvalide, match="modifié"):
        sauvegarde.verifier(fichier, cle=cle)


def test_restaurer_n_ecrase_pas_une_base_en_service_sans_le_demander(base_remplie, tmp_path):
    fichier = tmp_path / "s.sauvegarde"
    sauvegarde.creer(base_remplie, fichier)
    cible = _moteur_vide(tmp_path)
    sauvegarde.restaurer(fichier, cible)
    with pytest.raises(sauvegarde.SauvegardeInvalide, match="--forcer"):
        sauvegarde.restaurer(fichier, cible)
    sauvegarde.restaurer(fichier, cible, forcer=True)
    assert sauvegarde.empreintes(cible) == sauvegarde.empreintes(base_remplie)


def test_la_commande_planifiee_sauvegarde_verifie_note_et_fait_tourner(app_prechargee, tmp_path):
    dossier = tmp_path / "sauvegardes"
    dossier.mkdir()
    for i in range(3):  # anciennes sauvegardes
        (dossier / f"alerte-2020010{i}-000000.sauvegarde").write_bytes(b"ancienne")
    assert sauvegarde.main(["creer", "--dossier", str(dossier), "--garder", "2", "--verifier"]) == 0
    restantes = sauvegarde.lister(dossier)
    assert len(restantes) == 2 and restantes[-1].name.startswith("alerte-20")
    etat = sauvegarde.derniere()
    assert etat["verifiee"] and etat["lignes"] > 1227 and etat["fichier"] == restantes[-1].name
    with db.connexion() as c:
        assert c.execute(select(func.count()).select_from(db.journal).where(db.journal.c.action == "sauvegarde")).scalar() == 1
    assert sauvegarde.main(["verifier", str(restantes[0])]) == 2  # une « ancienne » illisible : echec signale


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="PostgreSQL non configure (TEST_DATABASE_URL)")
def test_restauration_dans_postgresql_reprend_les_compteurs(base_remplie, tmp_path):
    """Sauvegarde restauree dans une seconde base PostgreSQL : les nouveaux enregistrements prennent la suite
    des identifiants restaures au lieu d'entrer en collision."""
    fichier = tmp_path / "s.sauvegarde"
    sauvegarde.creer(base_remplie, fichier)
    url = os.environ["TEST_DATABASE_URL"].rsplit("/", 1)[0] + "/alerte_essai"
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    cible = create_engine(url)
    sauvegarde.restaurer(fichier, cible, forcer=True)
    assert sauvegarde.empreintes(cible)["etudiant"] == sauvegarde.empreintes(base_remplie)["etudiant"]
    with cible.begin() as c:
        maxi = c.execute(select(func.max(db.promotion.c.id))).scalar()
        nouvel = c.execute(db.promotion.insert().values(nom="Après restauration", origine="etablissement",
                                                        cree_le=db.maintenant())).inserted_primary_key[0]
    assert nouvel == maxi + 1
    cible.dispose()
