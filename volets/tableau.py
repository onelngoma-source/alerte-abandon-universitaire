"""Suivi de cohorte : les etudiants d'une promotion, classes par risque."""
from flask import Blueprint, render_template, request

import db
from auth import connexion_requise
from volets.api_cohortes import lister_promotions

bp = Blueprint("tableau", __name__)


@bp.route("/tableau")
@connexion_requise
def page():
    with db.connexion() as c:
        promotions = lister_promotions(c)
    demandee = request.args.get("cohorte", type=int)
    ids = [p["id"] for p in promotions]
    courante = demandee if demandee in ids else (ids[-1] if ids else None)
    return render_template("tableau.html", cohortes=promotions, courante=courante, actif="tableau")
