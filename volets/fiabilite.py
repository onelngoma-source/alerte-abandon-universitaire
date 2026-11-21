"""Page « Fiabilité du modèle » : evaluation sur des cohortes jamais vues, calibration, equite,
comparaison des modeles (dont l'approche a noyau du memoire) et limites."""
from flask import Blueprint, current_app, jsonify, render_template

from auth import connexion_requise
from moteur import fiabilite

bp = Blueprint("fiabilite", __name__)


@bp.route("/fiabilite")
@connexion_requise
def page():
    return render_template("fiabilite.html", actif="fiabilite")


@bp.get("/api/fiabilite")
@connexion_requise
def donnees():
    return jsonify(fiabilite.calculer(current_app.moteur))
