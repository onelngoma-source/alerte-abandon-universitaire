"""Fiabilite du modele : evaluation de reference sur les cohortes 2015 a 2017, et surveillance sur l'etablissement."""
from flask import Blueprint, current_app, jsonify, render_template

import db
from auth import connexion_requise
from metier import surveillance
from moteur import fiabilite

bp = Blueprint("fiabilite", __name__)


@bp.route("/fiabilite")
@connexion_requise
def page():
    return render_template("fiabilite.html", actif="fiabilite", modele_version=current_app.moteur.version)


@bp.get("/api/fiabilite")
@connexion_requise
def donnees():
    return jsonify(fiabilite.calculer(current_app.moteur))


@bp.get("/api/surveillance")
@connexion_requise
def surveiller():
    """Performances recalculees sur les etudiants de l'etablissement dont le devenir reel est connu
    (les promotions de demonstration sont exclues)."""
    with db.connexion() as c:
        return jsonify({"etablissement": surveillance.etat(c, current_app.moteur, "etablissement"),
                        "demonstration": surveillance.etat(c, current_app.moteur, "demonstration")})
