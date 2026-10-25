"""Authentification : un compte administrateur unique (identifiants lus dans l'environnement)."""
import os
import secrets
from functools import wraps
from pathlib import Path

from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint("auth", __name__)

DOSSIER_FONDS = Path(__file__).resolve().parent / "static" / "fonds"
EXTENSIONS_IMAGE = (".jpg", ".jpeg", ".png", ".webp", ".avif")


def image_de_fond() -> str | None:
    """Image de fond de la page de connexion, choisie sans toucher au code.

    Il suffit de deposer une image nommee `connexion` dans static/fonds/
    (connexion.jpg, connexion.png, connexion.webp...). La variable
    d'environnement FOND_CONNEXION permet d'en designer une autre par son nom
    de fichier, ou de donner une adresse web (http...). Sans rien de tout cela,
    la page garde son degrade.
    """
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
    """Assombrissement applique sur l'image, de 0 a 90 % (variable FOND_VOILE).

    Aucun voile par defaut : l'image se voit telle quelle. Rien n'est ecrit
    directement dessus, le texte vivant dans la carte et dans le volet bleu.
    Monter cette valeur reste utile si une image claire noie la carte.
    """
    try:
        return max(0, min(90, int(os.environ.get("FOND_VOILE", "0"))))
    except ValueError:
        return 0

MODE_DEMO = os.environ.get("MODE_DEMO", "0") == "1"


def proprietaire_courant() -> str | None:
    """Identifiant du visiteur, propre a son navigateur. Sert a cloisonner les cohortes
    importees : hors mode demonstration, on rend None et tout le monde voit tout."""
    if not MODE_DEMO:
        return None
    if "visiteur" not in session:
        session["visiteur"] = secrets.token_urlsafe(12)
        session.permanent = True
    return session["visiteur"]


ADMIN_IDENTIFIANT = os.environ.get("ADMIN_IDENTIFIANT", "admin")
# A changer avant tout deploiement : variable ADMIN_MDP_HACHE (hash werkzeug). Defaut : "changez-moi".
ADMIN_MDP_HACHE = os.environ.get("ADMIN_MDP_HACHE", generate_password_hash("changez-moi"))


def connexion_requise(vue):
    @wraps(vue)
    def protegee(*args, **kwargs):
        if not session.get("connecte"):
            if request.path.startswith("/api/"):
                return {"erreur": "Session expirée, reconnectez-vous."}, 401
            return redirect(url_for("auth.connexion", suivant=request.path))
        return vue(*args, **kwargs)
    return protegee


@bp.route("/connexion", methods=["GET", "POST"])
def connexion():
    erreur = None
    if request.method == "POST":
        if (request.form.get("identifiant", "") == ADMIN_IDENTIFIANT
                and check_password_hash(ADMIN_MDP_HACHE, request.form.get("mot_de_passe", ""))):
            session["connecte"] = True
            session.permanent = True
            suivant = request.args.get("suivant", "")
            return redirect(suivant if suivant.startswith("/") and not suivant.startswith("//") else url_for("tableau.page"))
        erreur = "Identifiant ou mot de passe incorrect."
    fond = image_de_fond()
    return render_template("connexion.html", erreur=erreur,
                           fond=(fond if (fond or "").startswith("http") else
                                 (url_for("static", filename=fond) if fond else None)),
                           voile=voile_du_fond())


@bp.route("/deconnexion")
def deconnexion():
    session.pop("connecte", None)
    return redirect(url_for("auth.connexion"))
