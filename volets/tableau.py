"""Volet 1 : tableau de bord des etudiants du jeu de test."""
from flask import Blueprint, render_template, request

import db
from auth import MODE_DEMO, connexion_requise, proprietaire_courant

bp = Blueprint("tableau", __name__)


@bp.route("/tableau")
@connexion_requise
def page():
    cohortes = db.lister_cohortes(proprietaire_courant())
    demandee = request.args.get("cohorte", type=int)
    ids = [c["id"] for c in cohortes]
    if demandee in ids:
        courante = demandee
    else:  # par defaut : le jeu de test s'il est charge, sinon la derniere cohorte
        test = [c["id"] for c in cohortes if c["origine"] == "test_uci"]
        courante = test[0] if test else (ids[-1] if ids else None)
    return render_template("tableau.html", cohortes=cohortes, courante=courante,
                           actif="tableau", mode_demo=MODE_DEMO)
