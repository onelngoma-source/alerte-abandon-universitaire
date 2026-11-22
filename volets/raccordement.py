"""Raccordement au systeme de scolarite : API d'import par jeton de service, et gestion des jetons (administrateur).

    curl -H "Authorization: Bearer aap_..." -F promotion="Licence 1 Informatique 2026-2027" -F fichier=@l1.csv \\
         https://alerte.exemple.ga/api/v1/synchronisation
"""
from flask import Blueprint, current_app, jsonify, request

import auth
import db
from auth import interdit_en_demo, role_requis, utilisateur_courant
from metier import synchronisation as sync

bp = Blueprint("raccordement", __name__)


def _jeton_presente() -> str | None:
    entete = request.headers.get("Authorization", "")
    return entete[7:].strip() if entete.lower().startswith("bearer ") else None


@bp.post("/api/v1/synchronisation")
def synchroniser():
    adresse = auth._adresse()
    with db.connexion() as c:
        if auth.connexion_bloquee(c, adresse, ""):
            return jsonify({"erreur": "Trop de tentatives refusées depuis cette adresse. Réessayez plus tard."}), 429
        jeton = sync.jeton_valide(c, _jeton_presente())
        if jeton is None:
            auth.noter_echec(c, adresse, "")
    if jeton is None:
        return jsonify({"erreur": "Jeton de service absent, invalide ou révoqué."}), 401, {"WWW-Authenticate": "Bearer"}

    if "fichier" in request.files:
        f = request.files["fichier"]
        contenu, nom_fichier = f.read(), f.filename
        promotion = request.form.get("promotion") or ""
    else:  # corps brut (text/csv), promotion dans l'adresse
        contenu, nom_fichier = request.get_data(), None
        promotion = request.args.get("promotion") or ""
    if not contenu:
        return jsonify({"erreur": "Fichier vide ou absent."}), 400
    try:
        compte = sync.synchroniser(current_app.moteur, contenu, promotion, nom_fichier, f"jeton:{jeton['nom']}")
    except sync.ImportRefuse as e:
        return jsonify({"erreur": str(e)}), 400
    return jsonify(compte)


@bp.get("/api/admin/jetons")
@role_requis("admin")
def lister():
    with db.connexion() as c:
        return jsonify({"jetons": sync.lister_jetons(c)})


@bp.post("/api/admin/jetons")
@role_requis("admin")
@interdit_en_demo
def creer():
    nom = ((request.get_json(silent=True) or {}).get("nom") or "").strip()
    if not nom:
        return jsonify({"erreur": "Donnez un nom au jeton (par exemple : « Logiciel de scolarité »)."}), 400
    with db.connexion() as c:
        identifiant, jeton = sync.creer_jeton(c, nom, utilisateur_courant())
    return jsonify({"id": identifiant, "jeton": jeton})


@bp.post("/api/admin/jetons/<int:identifiant>/revocation")
@role_requis("admin")
def revoquer(identifiant):
    with db.connexion() as c:
        if not sync.revoquer_jeton(c, identifiant, utilisateur_courant()):
            return jsonify({"erreur": "Jeton introuvable ou déjà révoqué."}), 404
    return jsonify({"ok": True})
