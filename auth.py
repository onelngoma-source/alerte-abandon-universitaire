"""Comptes, roles et securite.

  - un compte par personne, trois roles : conseiller, responsable, administrateur ;
  - mots de passe haches (werkzeug), 10 caracteres au moins, changement impose a la premiere connexion ;
  - verrouillage temporaire apres 5 echecs de connexion depuis une meme adresse ;
  - jeton anti-CSRF sur toutes les requetes qui modifient quelque chose ;
  - journal des connexions, reussies ou non.
Au premier demarrage sur une base vide, un administrateur est cree a partir des variables ADMIN_IDENTIFIANT
et ADMIN_MDP_HACHE (sinon « admin » / « changez-moi », a changer des la premiere connexion).
"""
import os
import secrets
import time
from functools import wraps
from pathlib import Path

from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import func, select
from werkzeug.security import check_password_hash, generate_password_hash

import db
from metier.journal import tracer
from metier.regles import ROLES

bp = Blueprint("auth", __name__)

DOSSIER_FONDS = Path(__file__).resolve().parent / "static" / "fonds"
EXTENSIONS_IMAGE = (".jpg", ".jpeg", ".png", ".webp", ".avif")
LONGUEUR_MIN_MDP = 10
ECHECS_MAX, VERROU_SECONDES = 5, 300
_echecs: dict[str, list[float]] = {}


def mode_demo() -> bool:
    return os.environ.get("MODE_DEMO", "0") == "1"


# ------------------------------------------------------------------ image de fond de la page de connexion
def image_de_fond() -> str | None:
    """Image de fond de la connexion : static/fonds/connexion.(jpg|png|webp|avif), ou FOND_CONNEXION."""
    choix = os.environ.get("FOND_CONNEXION", "").strip()
    if choix.startswith(("http://", "https://")):
        return choix
    if choix:
        fichier = DOSSIER_FONDS / Path(choix).name
        return f"fonds/{fichier.name}" if fichier.is_file() else None
    for extension in EXTENSIONS_IMAGE:
        fichier = DOSSIER_FONDS / f"connexion{extension}"
        if fichier.is_file():
            return f"fonds/{fichier.name}"
    return None


def voile_du_fond() -> int:
    try:
        return max(0, min(90, int(os.environ.get("FOND_VOILE", "0"))))
    except ValueError:
        return 0


# ------------------------------------------------------------------ comptes
def creer_administrateur_initial() -> None:
    with db.connexion() as c:
        hache = os.environ.get("ADMIN_MDP_HACHE")
        identifiant = os.environ.get("ADMIN_IDENTIFIANT", "admin")
        existe = db.ligne(c.execute(select(db.utilisateur.c.id).where(db.utilisateur.c.identifiant == identifiant)))
        # en demonstration, le compte du jury (variables d'environnement) s'ajoute aux comptes fictifs
        if existe or (c.execute(select(func.count()).select_from(db.utilisateur)).scalar() and not (mode_demo() and hache)):
            return
        c.execute(db.utilisateur.insert().values(
            identifiant=identifiant, nom="Administrateur", role="admin",
            mdp_hache=hache or generate_password_hash("changez-moi"), actif=True,
            doit_changer_mdp=not hache and not mode_demo(), cree_le=db.maintenant()))


def verifier_mot_de_passe(mdp: str) -> str | None:
    if len(mdp or "") < LONGUEUR_MIN_MDP:
        return f"Le mot de passe doit compter au moins {LONGUEUR_MIN_MDP} caractères."
    if mdp.isdigit() or mdp.isalpha():
        return "Mélangez lettres et chiffres (ou symboles)."
    return None


def utilisateur_courant() -> dict | None:
    return g.get("utilisateur")


def _adresse() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


def charger_utilisateur():
    """Avant chaque requete : l'utilisateur de la session, s'il existe toujours et reste actif."""
    g.utilisateur = None
    uid = session.get("uid")
    if uid is None:
        return
    with db.connexion() as c:
        u = db.ligne(c.execute(select(db.utilisateur).where(db.utilisateur.c.id == uid)))
    if u is None or not u["actif"] or session.get("version") != u["mdp_hache"][-12:]:
        session.clear()  # compte desactive ou mot de passe change ailleurs : la session tombe
        return
    g.utilisateur = u


# ------------------------------------------------------------------ CSRF
def jeton_csrf() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def verifier_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS") or request.endpoint in ("auth.connexion", "static"):
        return
    if utilisateur_courant() is None:
        return  # sans session, rien a proteger : la vue repondra « reconnectez-vous »
    envoye = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    if not envoye or not secrets.compare_digest(envoye, session.get("csrf", "")):
        if request.path.startswith("/api/"):
            return jsonify({"erreur": "Session expirée ou requête non autorisée : rechargez la page."}), 400
        abort(400)


# ------------------------------------------------------------------ decorateurs
def connexion_requise(vue):
    @wraps(vue)
    def protegee(*args, **kwargs):
        u = utilisateur_courant()
        if u is None:
            if request.path.startswith("/api/"):
                return jsonify({"erreur": "Session expirée, reconnectez-vous."}), 401
            return redirect(url_for("auth.connexion", suivant=request.path))
        if u["doit_changer_mdp"] and request.endpoint not in ("auth.compte", "auth.changer_mdp", "auth.deconnexion", "auth.session_courante"):
            if request.path.startswith("/api/"):
                return jsonify({"erreur": "Changez d'abord votre mot de passe."}), 403
            return redirect(url_for("auth.compte"))
        return vue(*args, **kwargs)
    return protegee


def role_requis(*roles):
    def decorateur(vue):
        @wraps(vue)
        @connexion_requise
        def protegee(*args, **kwargs):
            if utilisateur_courant()["role"] not in roles:
                if request.path.startswith("/api/"):
                    return jsonify({"erreur": "Accès réservé : " + ", ".join(ROLES[r].lower() for r in roles) + "."}), 403
                abort(403)
            return vue(*args, **kwargs)
        return protegee
    return decorateur


def interdit_en_demo(vue):
    @wraps(vue)
    def protegee(*args, **kwargs):
        if mode_demo():
            return jsonify({"erreur": "Indisponible en mode démonstration."}), 403
        return vue(*args, **kwargs)
    return protegee


def page_d_accueil(u) -> str:
    return url_for("dossiers.page") if u["role"] == "conseiller" else url_for("tableau.page")


# ------------------------------------------------------------------ pages
@bp.route("/connexion", methods=["GET", "POST"])
def connexion():
    erreur = None
    if request.method == "POST":
        adresse = _adresse()
        recents = [t for t in _echecs.get(adresse, []) if time.time() - t < VERROU_SECONDES]
        _echecs[adresse] = recents
        identifiant = request.form.get("identifiant", "").strip()
        if len(recents) >= ECHECS_MAX:
            erreur = "Trop de tentatives. Réessayez dans quelques minutes."
        else:
            with db.connexion() as c:
                u = db.ligne(c.execute(select(db.utilisateur).where(db.utilisateur.c.identifiant == identifiant)))
                if u and u["actif"] and check_password_hash(u["mdp_hache"], request.form.get("mot_de_passe", "")):
                    session.clear()
                    session.update(uid=u["id"], version=u["mdp_hache"][-12:], csrf=secrets.token_urlsafe(32))
                    session.permanent = True
                    c.execute(db.utilisateur.update().where(db.utilisateur.c.id == u["id"]).values(derniere_connexion=db.maintenant()))
                    tracer(c, u, "connexion")
                    _echecs.pop(adresse, None)
                    suivant = request.args.get("suivant", "")
                    if u["doit_changer_mdp"]:
                        return redirect(url_for("auth.compte"))
                    return redirect(suivant if suivant.startswith("/") and not suivant.startswith("//") else page_d_accueil(u))
                tracer(c, None, "echec_connexion", detail={"identifiant": identifiant[:80]})
            _echecs.setdefault(adresse, []).append(time.time())
            erreur = "Identifiant ou mot de passe incorrect."
    fond = image_de_fond()
    from metier.demo import COMPTES_DEMO, MOT_DE_PASSE_DEMO
    return render_template("connexion.html", erreur=erreur,
                           fond=(fond if (fond or "").startswith("http") else (url_for("static", filename=fond) if fond else None)),
                           voile=voile_du_fond(), demo=mode_demo(),
                           comptes_demo=COMPTES_DEMO, mdp_demo=MOT_DE_PASSE_DEMO, roles=ROLES)


@bp.route("/deconnexion")
def deconnexion():
    u = utilisateur_courant()
    if u:
        with db.connexion() as c:
            tracer(c, u, "deconnexion")
    session.clear()
    return redirect(url_for("auth.connexion"))


@bp.route("/compte")
@connexion_requise
def compte():
    return render_template("compte.html", actif="compte", longueur_min=LONGUEUR_MIN_MDP)


@bp.post("/api/compte/mot-de-passe")
@connexion_requise
def changer_mdp():
    u = utilisateur_courant()
    donnees = request.get_json(silent=True) or {}
    if not check_password_hash(u["mdp_hache"], donnees.get("actuel", "")):
        return jsonify({"erreur": "Mot de passe actuel incorrect."}), 400
    nouveau = donnees.get("nouveau", "")
    message = verifier_mot_de_passe(nouveau)
    if message:
        return jsonify({"erreur": message}), 400
    if nouveau == donnees.get("actuel"):
        return jsonify({"erreur": "Choisissez un mot de passe différent de l'actuel."}), 400
    hache = generate_password_hash(nouveau)
    with db.connexion() as c:
        c.execute(db.utilisateur.update().where(db.utilisateur.c.id == u["id"]).values(mdp_hache=hache, doit_changer_mdp=False))
        tracer(c, u, "changement_mot_de_passe", "utilisateur", u["id"])
    session["version"] = hache[-12:]
    return jsonify({"ok": True, "suivant": page_d_accueil(u)})


@bp.get("/api/session")
@connexion_requise
def session_courante():
    u = utilisateur_courant()
    return jsonify({"identifiant": u["identifiant"], "nom": u["nom"], "role": u["role"], "csrf": jeton_csrf()})
