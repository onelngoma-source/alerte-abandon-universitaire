"""Fiche d'un etudiant : une page a part entiere, ouverte depuis le suivi de cohorte."""
from flask import Blueprint, abort, render_template

import db
from auth import connexion_requise, proprietaire_courant

bp = Blueprint("fiche", __name__)


@bp.route("/etudiants/<int:etudiant_id>")
@connexion_requise
def page(etudiant_id):
    e = db.lire_etudiant(etudiant_id)
    cohorte = db.lire_cohorte(e["cohorte_id"], proprietaire_courant()) if e else None
    if cohorte is None:
        abort(404)
    return render_template("fiche.html", actif="tableau", etudiant_id=etudiant_id, reference=e["reference"],
                           cohorte=cohorte)
