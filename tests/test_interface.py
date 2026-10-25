"""Rendu reel dans un navigateur (Chromium) : le tableau de bord et l'import affichent le meme bloc, a l'identique."""
import threading
import re
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from werkzeug.serving import make_server  # noqa: E402

from conftest import RACINE  # noqa: E402

CHROMIUM = Path("/opt/pw-browsers/chromium")


def sans_identifiants(html: str) -> str:
    """Les identifiants de lignes sont des cles de base de donnees, propres a chaque cohorte : on les retire."""
    return re.sub(r' data-id="\d+"', "", html)


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


def test_demarrage_vide_puis_chargement_du_jeu_de_test(page):
    pg, base, _ = page
    pg.goto(base + "/tableau")
    assert pg.is_visible("#etat-vide") and pg.is_hidden("#cohorte-vue")
    pg.click("#btn-charger-test-vide")
    pg.wait_for_selector("#cohorte-vue:not([hidden])")
    assert pg.inner_text("[data-kpi=effectif]").replace(" ", "").replace(" ", "").replace(" ", "") == "1328"
    assert pg.inner_text("[data-kpi=abandons]").replace(" ", "").replace(" ", "").replace(" ", "") == "427"


def test_tableau_de_bord_et_import_ont_le_meme_rendu(page):
    pg, base, _ = page
    pg.goto(base + "/tableau")
    pg.click("#btn-charger-test-vide"); pg.wait_for_selector("#cohorte-vue:not([hidden])")
    pg.wait_for_timeout(500)
    rendu_tableau = sans_identifiants(pg.inner_html("#cohorte-vue"))
    taille_tableau = {k: v for k, v in pg.locator("#cohorte-vue").bounding_box().items() if k in ("width", "height")}

    pg.goto(base + "/import")
    pg.set_input_files("#fichier", str(RACINE / "data" / "jeu_de_test_1328.csv"))
    pg.click("#btn-analyser")
    pg.wait_for_selector("#cohorte-vue:not([hidden])")
    pg.wait_for_timeout(500)
    assert sans_identifiants(pg.inner_html("#cohorte-vue")) == rendu_tableau  # meme HTML, apres rendu
    # memes dimensions a l'ecran (une comparaison au pixel serait faussee par le decalage vertical du bloc,
    # place plus bas sur la page d'import : l'anticrenelage du texte differe d'un demi-pixel)
    taille_import = {k: v for k, v in pg.locator("#cohorte-vue").bounding_box().items() if k in ("width", "height")}
    assert taille_import == taille_tableau


def test_un_filtre_change_le_tableau_et_les_indicateurs(page):
    pg, base, _ = page
    pg.goto(base + "/tableau")
    pg.click("#btn-charger-test-vide"); pg.wait_for_selector("#cohorte-vue:not([hidden])")
    pg.select_option("[data-filtre=c_ml]", "eleve")
    pg.select_option("[data-filtre=debiteur]", "1")
    pg.wait_for_timeout(300)
    effectif = int(pg.inner_text("[data-kpi=effectif]").replace(" ", "").replace(" ", "").replace(" ", ""))
    assert 0 < effectif < 345
    assert "Élevé" in pg.inner_text("[data-role=corps] tr:first-child")
    assert pg.inner_text("[data-kpi=eleve-ml]").strip() == str(effectif)


def test_clic_sur_une_ligne_ouvre_la_fiche_d_explication(page):
    pg, base, _ = page
    pg.goto(base + "/tableau")
    pg.click("#btn-charger-test-vide"); pg.wait_for_selector("#cohorte-vue:not([hidden])")
    reference = pg.inner_text("[data-role=corps] tr:nth-child(2) td:first-child").split("\n")[0].strip()
    pg.click("[data-role=corps] tr:nth-child(2)")
    pg.wait_for_selector("[data-role=fiche-contenu]:not([hidden])")
    assert pg.inner_text("[data-role=fiche-titre]") == reference
    assert pg.inner_text("[data-role=fiche-devenir]") in ("Abandon", "Diplômé", "Inscrit")
    assert len(pg.query_selector_all("[data-role=facteurs] .list-group-item")) == 5
    assert pg.inner_text("[data-role=p-ml]") != "-"
    assert len(pg.query_selector_all("[data-role=fiche-profil] .list-group-item")) == 13


def test_la_fiche_explique_le_noyau_par_ses_voisins(page):
    pg, base, _ = page
    pg.goto(base + "/tableau")
    pg.click("#btn-charger-test-vide"); pg.wait_for_selector("#cohorte-vue:not([hidden])")
    pg.click("[data-role=corps] tr:nth-child(2)")
    pg.wait_for_selector("[data-role=fiche-contenu]:not([hidden])")
    assert len(pg.query_selector_all("[data-role=voisins-lignes] tr")) == 5   # cinq profils, pas soixante-quinze
    assert "ont abandonné" in pg.inner_text("[data-role=voisins-bas]")
    # l'ecran reste sobre : aucun jargon technique dans la fiche
    texte = pg.inner_text("[data-role=fiche-contenu]").lower()
    for mot in ("shap", "smote", "nadaraya", "gaussien", "shapley", "largeur de bande", "75 profils"):
        assert mot not in texte


def test_graphique_par_filiere_suit_les_filtres_et_le_modele(page):
    pg, base, _ = page
    pg.goto(base + "/tableau")
    pg.click("#btn-charger-test-vide"); pg.wait_for_selector("#cohorte-vue:not([hidden])")
    etiquettes = lambda: pg.evaluate("Chart.getChart(document.querySelector('[data-role=graphique-filiere]')).data.labels")
    comptes = lambda: pg.evaluate("Chart.getChart(document.querySelector('[data-role=graphique-filiere]')).data.datasets.map(d => d.counts)")
    assert len(etiquettes()) == 17
    total = sum(sum(c) for c in comptes())
    assert total == 1328
    pg.select_option("[data-role=modele-filiere]", "noyau")
    assert sum(sum(c) for c in comptes()) == 1328
    pg.select_option("[data-filtre=filiere]", index=1)
    pg.wait_for_timeout(200)
    assert len(etiquettes()) == 1


def test_les_pages_restent_sobres_sans_jargon(page):
    """Les conseillers n'ont pas a lire de vocabulaire technique : il vit dans la documentation, pas dans l'application."""
    pg, base, _ = page
    interdits = ("smote", "nadaraya", "gaussien", "shapley", "imputation", "mode précoce", "seuil 0,5", "entraîné")
    for chemin in ("/tableau", "/saisie", "/import"):
        pg.goto(base + chemin)
        pg.wait_for_timeout(200)
        texte = pg.inner_text("body").lower()
        for mot in interdits:
            assert mot not in texte, (chemin, mot)
