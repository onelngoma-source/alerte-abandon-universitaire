"""Fiche d'un etudiant : une page a part entiere, ouverte depuis le suivi de cohorte ou un dossier."""
from flask import Blueprint, abort, render_template
from sqlalchemy import select

import db
from auth import connexion_requise

bp = Blueprint("fiche", __name__)


@bp.route("/etudiants/<int:etudiant_id>")
@connexion_requise
def page(etudiant_id):
    with db.connexion() as c:
        e = db.ligne(c.execute(select(db.etudiant.c.matricule, db.etudiant.c.nom, db.etudiant.c.promotion_id,
                                      db.promotion.c.nom.label("promotion"))
                               .join(db.promotion, db.promotion.c.id == db.etudiant.c.promotion_id)
                               .where(db.etudiant.c.id == etudiant_id)))
    if e is None:
        abort(404)
    return render_template("fiche.html", actif="tableau", etudiant_id=etudiant_id, reference=e["matricule"],
                           nom=e["nom"], cohorte={"id": e["promotion_id"], "nom": e["promotion"]})
