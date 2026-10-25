"""Volet 2 : saisie individuelle d'un etudiant."""
from flask import Blueprint, current_app, jsonify, render_template, request

from auth import connexion_requise
from moteur.conseils import generer_conseils
from moteur.referentiels import CHAMPS_FORMULAIRE, CHAMPS_OUI_NON, FILIERES, LIBELLES_CHAMPS

bp = Blueprint("saisie", __name__)


@bp.route("/saisie")
@connexion_requise
def page():
    moteur = current_app.moteur
    bornes = {c: [float(moteur.bornes[c][0]), float(moteur.bornes[c][1])] for c in CHAMPS_FORMULAIRE}
    return render_template("saisie.html", actif="saisie", champs=CHAMPS_FORMULAIRE, libelles=LIBELLES_CHAMPS,
                           bornes=bornes, filieres=FILIERES, oui_non=CHAMPS_OUI_NON)


@bp.post("/api/predict")
@connexion_requise
def predire():
    donnees = request.get_json(force=True, silent=True) or {}
    try:
        resultat = current_app.moteur.scorer_un(donnees)
    except (ValueError, TypeError) as e:
        return jsonify({"erreur": str(e)}), 400
    resultat["conseils"] = generer_conseils(donnees)
    return jsonify(resultat)
