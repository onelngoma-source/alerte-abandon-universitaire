"""Rendu reel dans un navigateur (Chromium) : le parcours d'un conseiller, de la file d'accompagnement a la fiche."""
import threading
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from werkzeug.serving import make_server  # noqa: E402

from conftest import RACINE  # noqa: E402

CHROMIUM = Path("/opt/pw-browsers/chromium")


@pytest.fixture
def serveur(app):
    s = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


@pytest.fixture
def page(serveur):
    with playwright.sync_playwright() as p:
        options = {"args": ["--no-sandbox"]}
        if CHROMIUM.exists():
            options["executable_path"] = str(CHROMIUM)
        try:
            navigateur = p.chromium.launch(**options)
        except Exception as e:  # navigateur absent : test ignore
            pytest.skip(f"Chromium indisponible : {e}")
        pg = navigateur.new_page(viewport={"width": 1440, "height": 900})
        erreurs = []
        pg.on("pageerror", lambda e: erreurs.append(str(e)))
        pg.goto(serveur + "/connexion")
        pg.fill("#identifiant", "admin"); pg.fill("#mot_de_passe", "changez-moi")
        pg.click("button[type=submit]"); pg.wait_for_load_state("networkidle")
        yield pg, serveur, erreurs
        navigateur.close()
        assert erreurs == []


def charger(pg, serveur):
    pg.goto(serveur + "/tableau")
    pg.click("#btn-charger-test-vide")
    pg.wait_for_selector("#lignes tr")


def test_demarrage_vide_puis_chargement_du_jeu_de_test(page):
    pg, serveur, _ = page
    pg.goto(serveur + "/tableau")
    assert pg.is_visible("#etat-vide")
    charger(pg, serveur)
    assert pg.inner_text("#kpi-effectif").replace("\u202f", " ") == "1 227"
    assert pg.locator("#lignes tr").count() == 25


def test_la_file_est_classee_par_risque_et_suit_la_capacite(page):
    pg, serveur, _ = page
    charger(pg, serveur)
    risques = [int(x.split()[0]) for x in pg.locator("#lignes .pct").all_inner_texts()]
    assert risques == sorted(risques, reverse=True)
    pg.check("#prioritaires")
    assert "245 étudiants" in pg.inner_text("#compte").replace("\u202f", " ")
    pg.fill("#capacite", "10")
    pg.dispatch_event("#capacite", "input")
    assert "123 étudiants" in pg.inner_text("#compte").replace("\u202f", " ")
    assert "123 étudiants" in pg.inner_text("#capacite-phrase").replace("\u202f", " ")


def test_filtres_par_niveau_et_par_filiere(page):
    pg, serveur, _ = page
    charger(pg, serveur)
    pg.click("#niveaux [data-niveau=faible]")
    assert all("Faible" in b for b in pg.locator("#lignes .risque-cellule .badge").all_inner_texts())
    pg.click("#niveaux [data-niveau=tous]")
    pg.click("#par-filiere [data-filiere='Agronomie']")
    assert set(pg.locator("#lignes .etudiant span").all_inner_texts()) == {"Agronomie"}


def test_un_clic_ouvre_la_fiche_et_permet_de_passer_au_suivant(page):
    pg, serveur, _ = page
    charger(pg, serveur)
    premier = pg.inner_text("#lignes tr:first-child .etudiant b")
    pg.click("#lignes tr:first-child")
    pg.wait_for_selector(".risque-grand")
    assert pg.inner_text("h1") == premier
    assert pg.locator(".facteurs.hausse li").count() >= 1
    assert pg.is_visible(".pistes") and pg.is_visible(".pastilles-voisins")
    assert pg.locator(".trajectoire .etape-traj").count() == 3
    pg.click("#suivant")
    pg.wait_for_selector(".risque-grand")
    assert pg.inner_text("h1") != premier


def test_la_saisie_estime_en_direct(page):
    pg, serveur, _ = page
    pg.goto(serveur + "/saisie")
    pg.click("[data-exemple=difficulte]")
    pg.wait_for_selector("#resultat .risque-grand")
    assert "fin du 2e semestre" in pg.inner_text("#resultat .meta-risque")
    pg.uncheck("[data-bascule='1st']")
    pg.wait_for_function("document.querySelector('#resultat .meta-risque').innerText.includes(\"l'inscription\")")
    assert pg.locator("#resultat .etape-traj.future").count() == 2


def test_la_page_fiabilite_retrouve_l_evaluation(page):
    pg, serveur, _ = page
    pg.goto(serveur + "/fiabilite")
    pg.wait_for_selector("#table-comparaison tr")
    assert "0,902" in pg.inner_text("#kpis")
    assert "Boursiers" in pg.inner_text("#table-equite")
    assert pg.locator("#table-moments tbody tr").count() == 3


def test_les_pages_restent_sobres_sans_jargon(page):
    """Le conseiller ne voit ni logit, ni nom de variable anglais, ni code technique de modele."""
    pg, serveur, _ = page
    charger(pg, serveur)
    pg.click("#lignes tr:first-child")
    pg.wait_for_selector(".risque-grand")
    texte = pg.inner_text("main")
    for mot in ("logit", "Curricular", "Tuition", "T0", "T1", "T2", "p_ml", "undefined", "NaN"):
        assert mot not in texte, mot
