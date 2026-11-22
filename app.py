"""Application Flask : outil d'alerte precoce et de suivi du risque d'abandon universitaire.

Organisee autour du travail de l'equipe d'accompagnement (dossier volets/) :
  1. dossiers : les alertes a traiter, attribuees, avec echeances et journal de suivi ;
  2. suivi de cohorte : les etudiants d'une promotion classes par risque, selon la capacite d'accompagnement ;
  3. fiche etudiant : risque, evolution, facteurs, pistes, et le dossier de suivi ;
  4. evaluer un etudiant (simulation) et importer une promotion ;
  5. pilotage : le suivi est-il fait, a temps, et par qui ;
  6. fiabilite du modele : evaluation de reference et surveillance sur l'etablissement ;
  7. administration : comptes, journal d'activite, conservation des donnees.
Le calcul est unique (dossier moteur/), les regles de suivi sont dans metier/, les donnees dans db.py.
"""
import os
import secrets
from datetime import timedelta

from flask import Flask, g, jsonify, redirect, request, url_for
from sqlalchemy import and_, func, select
from werkzeug.middleware.proxy_fix import ProxyFix

import auth
import db
from moteur import cohortes
from moteur.scoring import Moteur
from volets import administration, api_cohortes, dossiers, fiabilite, fiche, import_csv, pilotage, raccordement, saisie, tableau

NOM_JEU_DE_TEST = "Cohortes 2015 à 2017 (démonstration)"


def charger_jeu_de_test(app) -> int:
    """Charge une seule fois les 1 227 etudiants de test (cohortes 2015 a 2017, jamais vus a l'entrainement)
    par la chaine d'import commune. En mode demonstration, le suivi est en plus deja engage."""
    with db.connexion() as c:
        existante = db.ligne(c.execute(select(db.promotion.c.id).where(db.promotion.c.origine == "demonstration")))
    if existante:
        return existante["id"]
    chemin = db.RACINE / "data" / db.FICHIER_JEU_DE_TEST
    df, erreur = cohortes.lire_csv(chemin.read_bytes())
    if erreur:
        raise RuntimeError(erreur)
    compte = cohortes.importer(app.moteur, df, NOM_JEU_DE_TEST, "demonstration", chemin.name)
    if auth.mode_demo():
        from metier import demo
        with db.connexion() as c:
            demo.engager_le_suivi(c, compte["cohorte_id"], demo.creer_comptes(c))
    return compte["cohorte_id"]


def creer_application(moteur: Moteur | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=int(os.environ.get("DUREE_SESSION_HEURES", "8")))
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURISE", "0") == "1"
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.moteur = moteur or Moteur()
    app.charger_jeu_de_test = lambda: charger_jeu_de_test(app)
    db.initialiser()
    # Cle de signature des sessions : FLASK_SECRET_KEY, sinon une cle tiree une fois et gardee en base, la meme
    # pour tous les processus et apres chaque redemarrage (sans quoi chaque redemarrage deconnecte tout le monde).
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or db.parametre_cree_une_fois("cle_session", lambda: secrets.token_hex(32))
    if auth.proxys_de_confiance():
        nb = auth.proxys_de_confiance()
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=nb, x_proto=nb)
    if auth.mode_demo():
        from metier import demo
        with db.connexion() as c:
            demo.creer_comptes(c)
    auth.creer_administrateur_initial()

    app.before_request(auth.charger_utilisateur)
    app.before_request(auth.verifier_csrf)

    @app.before_request
    def nonce_csp():
        g.csp_nonce = secrets.token_urlsafe(18)

    @app.after_request
    def entetes(reponse):
        """En-tetes de securite. La politique de contenu (CSP) n'autorise que les scripts du site et les scripts
        en ligne porteurs du nonce de la requete : un script injecte dans une page ne s'executerait pas."""
        h = reponse.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        h.setdefault("Content-Security-Policy", (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{g.get('csp_nonce', '')}'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"))
        if app.config["SESSION_COOKIE_SECURE"]:
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        if request.endpoint != "static":
            h.setdefault("Cache-Control", "no-store")  # donnees personnelles : jamais dans un cache partage
        return reponse

    @app.context_processor
    def contexte():
        u = auth.utilisateur_courant()
        compteurs = {}
        if u:
            aujourd_hui = db.maintenant().date()
            with db.connexion() as c:
                ouverts = and_(db.dossier.c.statut != "clos", db.dossier.c.conseiller_id == u["id"])
                compteurs["mes_dossiers"] = c.execute(select(func.count()).select_from(db.dossier).where(ouverts)).scalar()
                compteurs["mes_retards"] = c.execute(select(func.count()).select_from(db.dossier).where(
                    and_(ouverts, db.dossier.c.echeance < aujourd_hui))).scalar()
                compteurs["non_attribues"] = c.execute(select(func.count()).select_from(db.dossier).where(
                    and_(db.dossier.c.statut != "clos", db.dossier.c.conseiller_id.is_(None)))).scalar()
        from metier.regles import ROLES
        return {"utilisateur": u, "csrf": auth.jeton_csrf(), "roles": ROLES, "compteurs": compteurs,
                "mode_demo": auth.mode_demo(), "csp_nonce": g.get("csp_nonce", "")}

    for module in (auth, tableau, saisie, import_csv, fiche, fiabilite, dossiers, pilotage, administration, raccordement):
        app.register_blueprint(module.bp)
    app.register_blueprint(api_cohortes.bp)
    app.register_blueprint(api_cohortes.bp_etudiants)

    @app.route("/sante")
    def sante():
        """Pour la supervision (sonde toutes les minutes) : la base repond-elle, le schema est-il a jour, la derniere
        sauvegarde verifiee a-t-elle moins de 26 heures ? Aucune donnee personnelle, aucune version de logiciel."""
        import json as _json
        from datetime import datetime
        from alembic.script import ScriptDirectory
        try:
            revision = db.revision_schema()
            brute = db.lire_parametre("derniere_sauvegarde")
        except Exception:  # noqa: BLE001 - la sonde doit repondre, meme base arretee
            return jsonify({"etat": "panne", "base": False}), 503
        attendue = ScriptDirectory.from_config(db.config_migrations()).get_current_head()
        sauvegarde = None
        if brute:
            s = _json.loads(brute)
            age = (db.maintenant() - datetime.fromisoformat(s["cree_le"])).total_seconds() / 3600
            sauvegarde = {"age_heures": round(age, 1), "verifiee": bool(s.get("verifiee")), "recente": age < 26 and bool(s.get("verifiee"))}
        a_jour = revision == attendue
        return jsonify({"etat": "ok" if a_jour else "degrade", "base": True, "schema_a_jour": a_jour,
                        "sauvegarde": sauvegarde}), 200

    @app.route("/")
    def racine():
        u = g.get("utilisateur")
        return redirect(auth.page_d_accueil(u) if u else url_for("auth.connexion"))

    if os.environ.get("DEMO_PRELOAD", "1") == "1":  # par defaut, les 1 227 etudiants de test sont deja charges
        charger_jeu_de_test(app)
    return app


app = creer_application()

if __name__ == "__main__":
    # serveur de developpement, local par defaut ; en production : gunicorn (voir Dockerfile)
    app.run(debug=False, host=os.environ.get("HOTE", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)), use_reloader=False)
