"""Application Flask : dispositif d'alerte precoce du risque d'abandon universitaire.

Organisee autour du travail d'un conseiller (dossier volets/) :
  1. suivi de cohorte : la file des etudiants a accompagner en priorite, selon la capacite disponible ;
  2. fiche etudiant : le risque, son evolution, ce qui le fait monter ou baisser, des pistes d'action ;
  3. evaluer un etudiant : saisie guidee, estimation recalculee a chaque modification ;
  4. importer une cohorte : un fichier CSV, puis le meme suivi ;
  5. fiabilite du modele : evaluation sur des cohortes jamais vues, calibration, equite, approche a noyau.
Le calcul est unique (dossier moteur/) et les donnees sont dans une base SQLite (db.py).
"""
import os
import secrets
from datetime import timedelta

from flask import Flask, redirect, url_for

import auth
import db
from moteur import cohortes
from moteur.scoring import Moteur
from volets import api_cohortes, fiabilite, fiche, import_csv, saisie, tableau

NOM_JEU_DE_TEST = "Cohortes 2015 à 2017 (test)"


def charger_jeu_de_test(app) -> int:
    """Charge les 1 227 etudiants de test (cohortes 2015 a 2017, jamais vus a l'entrainement)
    dans la base, une seule fois, par la chaine d'import commune."""
    for c in db.lister_cohortes():
        if c["origine"] == "test_uci":
            return c["id"]
    chemin = db.RACINE / "data" / db.FICHIER_JEU_DE_TEST
    df, erreur = cohortes.lire_csv(chemin.read_bytes())
    if erreur:
        raise RuntimeError(erreur)
    return cohortes.importer(app.moteur, df, NOM_JEU_DE_TEST, "test_uci", chemin.name)["cohorte_id"]


def creer_application(moteur: Moteur | None = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    # La session etait permanente sans duree declaree : Flask retient alors
    # 31 jours, et l'application se rouvrait directement sur le tableau de bord
    # des semaines apres la derniere connexion. Une journee de travail suffit.
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        hours=int(os.environ.get("DUREE_SESSION_HEURES", "8")))
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.json.ensure_ascii = False
    app.json.sort_keys = False  # l'ordre des champs de correspondance est celui du formulaire
    app.moteur = moteur or Moteur()
    app.charger_jeu_de_test = lambda: charger_jeu_de_test(app)
    db.initialiser()

    app.register_blueprint(auth.bp)
    app.register_blueprint(tableau.bp)
    app.register_blueprint(saisie.bp)
    app.register_blueprint(import_csv.bp)
    app.register_blueprint(fiche.bp)
    app.register_blueprint(fiabilite.bp)
    app.register_blueprint(api_cohortes.bp)
    app.register_blueprint(api_cohortes.bp_etudiants)

    @app.route("/")
    def racine():
        return redirect(url_for("tableau.page"))

    if os.environ.get("DEMO_PRELOAD", "1") == "1":  # par defaut, les 1 227 etudiants de test sont deja affiches
        charger_jeu_de_test(app)
    return app


app = creer_application()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), use_reloader=False)
