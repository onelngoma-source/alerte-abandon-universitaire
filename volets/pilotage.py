"""Pilotage du dispositif (responsable, administrateur)."""
from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import select

import db
from auth import role_requis
from metier import pilotage

bp = Blueprint("pilotage", __name__)


@bp.route("/pilotage")
@role_requis("responsable", "admin")
def page():
    with db.connexion() as c:
        promotions = db.lignes(c.execute(select(db.promotion.c.id, db.promotion.c.nom).order_by(db.promotion.c.id)))
    return render_template("pilotage.html", actif="pilotage", promotions=promotions)


@bp.get("/api/pilotage")
@role_requis("responsable", "admin")
def donnees():
    with db.connexion() as c:
        return jsonify(pilotage.indicateurs(c, request.args.get("promotion", type=int)))
