"""Application Flask : dispositif d'alerte precoce du risque d'abandon universitaire.

Trois volets, chacun dans son module (dossier volets/) :
  1. tableau de bord : les etudiants du jeu de TEST, avec filtres et indicateurs ;
  2. saisie individuelle : un etudiant, un formulaire, une explication ;
  3. import CSV : un fichier produit le meme tableau que le tableau de bord.
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
from volets import api_cohortes, import_csv, saisie, tableau

NOM_JEU_DE_TEST = "Jeu de test UCI (1 328 étudiants)"


def charger_jeu_de_test(app) -> int:
    """Charge les 1 328 etudiants de test dans la base (une seule fois) par la chaine d'import commune."""
    for c in db.lister_cohortes():
        if c["origine"] == "test_uci":
            return c["id"]
    chemin = db.RACINE / "data" / "jeu_de_test_1328.csv"
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
    app.register_blueprint(api_cohortes.bp)
    app.register_blueprint(api_cohortes.bp_etudiants)

    @app.route("/")
    def racine():
        return redirect(url_for("tableau.page"))

    if os.environ.get("DEMO_PRELOAD", "1") == "1":  # par defaut, les 1 328 etudiants de test sont deja affiches
        charger_jeu_de_test(app)
    return app


app = creer_application()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), use_reloader=False)
