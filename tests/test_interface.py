"""Rendu reel dans un navigateur (Chromium) : le parcours d'un conseiller, de la file d'accompagnement a la fiche.

Les listes s'affichent par lots dans leur propre zone de defilement ; un clic ouvre l'apercu (tiroir de droite),
d'ou l'on traite le dossier ou ouvre la fiche complete, organisee en onglets."""
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
    pg.wait_for_function("document.querySelector('#kpi-effectif').innerText.replace(/\\s/g, '') === '1227'")
    assert pg.locator("#lignes tr[data-id]").count() == 60
    # les lignes suivantes arrivent quand on approche du bas de la liste
    pg.locator("#lignes .sentinelle").scroll_into_view_if_needed()
    pg.wait_for_function("document.querySelectorAll('#lignes tr[data-id]').length > 60")


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
    assert {t.split(' · ')[0] for t in pg.locator("#lignes .etudiant span").all_inner_texts()} == {"Agronomie"}


def test_un_clic_ouvre_l_apercu_puis_la_fiche_en_onglets(page):
    pg, serveur, _ = page
    charger(pg, serveur)
    premier = pg.inner_text("#lignes tr:first-child .etudiant b")
    deuxieme = pg.inner_text("#lignes tr:nth-child(2) .etudiant b")
    pg.click("#lignes tr:first-child")
    pg.wait_for_selector("#tiroir.ouvert #carte-dossier")
    assert pg.inner_text("#tiroir-titre") == premier
    assert pg.locator("#tiroir .facteurs.hausse li").count() >= 1
    # fleche bas : etudiant suivant de la liste, sans quitter la page
    pg.keyboard.press("ArrowDown")
    pg.wait_for_function(f"document.querySelector('#tiroir-titre').innerText === {deuxieme!r}")
    pg.keyboard.press("ArrowUp")
    pg.wait_for_function(f"document.querySelector('#tiroir-titre').innerText === {premier!r}")
    pg.click("#tiroir-fiche")
    pg.wait_for_selector("#ruban-fiche")
    assert pg.inner_text("h1") == premier
    assert pg.is_visible("#p-suivi #carte-dossier")
    pg.click("[data-onglet=pourquoi]")
    assert pg.locator("#p-pourquoi .facteurs.hausse li").count() >= 1
    assert pg.is_visible("#p-pourquoi .pistes")
    pg.click("[data-onglet=proches]")
    assert pg.is_visible(".pastilles-voisins")
    pg.click("[data-onglet=evolution]")
    assert pg.locator(".trajectoire .etape-traj").count() == 3
    pg.click("#suivant")
    pg.wait_for_function(f"document.querySelector('h1').innerText !== {premier!r}")
    pg.wait_for_selector("#ruban-fiche")
    assert pg.inner_text("h1") == deuxieme


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
    pg.wait_for_selector("#table-moments tbody tr")
    assert "0,902" in pg.inner_text("#kpis")
    assert pg.locator("#table-moments tbody tr").count() == 3
    pg.click("[data-onglet=calibration]")
    pg.wait_for_selector("#table-equite tr")
    assert "Boursiers" in pg.inner_text("#table-equite")
    pg.click("[data-onglet=comparaison]")
    pg.wait_for_selector("#table-comparaison tr")


def test_les_pages_restent_sobres_sans_jargon(page):
    """Le conseiller ne voit ni logit, ni nom de variable anglais, ni code technique de modele."""
    pg, serveur, _ = page
    charger(pg, serveur)
    pg.click("#lignes tr:first-child")
    pg.wait_for_selector("#tiroir.ouvert #carte-dossier")
    textes = [pg.inner_text("main"), pg.inner_text("#tiroir")]
    pg.click("#tiroir-fiche")
    pg.wait_for_selector("#ruban-fiche")
    for onglet in ("suivi", "pourquoi", "evolution", "proches", "scolaire"):
        pg.click(f"[data-onglet={onglet}]")
        textes.append(pg.inner_text("main"))
    texte = " ".join(textes)
    for mot in ("logit", "Curricular", "Tuition", "T0", "T1", "T2", "p_ml", "undefined", "NaN"):
        assert mot not in texte, mot


def test_traiter_une_alerte_depuis_les_dossiers(page):
    pg, serveur, _ = page
    charger(pg, serveur)
    pg.goto(serveur + "/dossiers?vue=non_attribues")
    pg.wait_for_selector("#lignes tr")
    pg.click("#lignes tr:first-child td:nth-child(2)")
    # le dossier se traite dans l'apercu, sans quitter la liste
    pg.wait_for_selector("#tiroir.ouvert #carte-dossier .statut.s-a_contacter")
    pg.click("[data-op=statut][data-statut=contacte]")
    pg.wait_for_selector("#carte-dossier .statut.s-contacte")
    pg.select_option("form[data-op=action] select[name=type]", "entretien")
    pg.fill("form[data-op=action] textarea", "Entretien fixé jeudi avec l'étudiant.")
    pg.click("form[data-op=action] button[type=submit]")
    pg.wait_for_selector("text=Entretien fixé jeudi")
    pg.click("[data-op=ouvrir-cloture]")
    pg.select_option("form[data-op=cloture] select[name=motif]", "risque_ecarte")
    pg.click("form[data-op=cloture] button[type=submit]")
    pg.wait_for_selector("#tiroir >> text=Aucun dossier ouvert")
    assert "Risque écarté" in pg.inner_text("#tiroir #carte-dossier")
    # la liste des dossiers non attribues s'est mise a jour derriere le tiroir
    pg.keyboard.press("Escape")
    assert not pg.is_visible("#tiroir.ouvert")


def test_pages_de_pilotage_et_d_administration(page):
    pg, serveur, _ = page
    charger(pg, serveur)
    pg.goto(serveur + "/pilotage")
    pg.wait_for_selector("#charge tbody tr")
    assert "455" in pg.inner_text("#kpis")
    pg.goto(serveur + "/admin/utilisateurs")
    pg.click("#nouveau")
    pg.fill("#form-compte [name=nom]", "Conseiller Test")
    pg.fill("#form-compte [name=identifiant]", "c.test")
    pg.click("#form-compte button[type=submit]")
    pg.wait_for_selector("#modale-mdp[open]")
    assert len(pg.inner_text("#mdp")) == 12
    pg.goto(serveur + "/admin/journal")
    pg.wait_for_selector("#lignes tr")
    assert "Création de compte" in pg.inner_text("#lignes")
