"""API des cohortes, partagee par le tableau de bord et l'import (meme tableau, memes donnees)."""
import csv
import json
from functools import lru_cache

import numpy as np
from flask import Blueprint, current_app, jsonify

import db
from auth import MODE_DEMO, connexion_requise, proprietaire_courant
from moteur.conseils import generer_conseils
from moteur.referentiels import CHAMPS_FORMULAIRE, CHAMPS_OUI_NON, DEVENIRS, FILIERES, LIBELLES_CHAMPS

bp = Blueprint("api_cohortes", __name__, url_prefix="/api/cohortes")


@lru_cache(maxsize=1)
def references_jeu_de_test() -> frozenset:
    """Les 1 328 references du jeu de test : un fichier importe qui les contient toutes est le jeu de test."""
    with open(db.RACINE / "data" / "jeu_de_test_1328.csv", encoding="utf-8", newline="") as f:
        return frozenset(ligne["Reference"] for ligne in csv.DictReader(f))


def est_le_jeu_de_test(cohorte, lignes) -> bool:
    if cohorte["origine"] == "test_uci":
        return True
    return cohorte["effectif"] == len(references_jeu_de_test()) and {l["reference"] for l in lignes} == references_jeu_de_test()


@bp.get("")
@connexion_requise
def lister():
    return jsonify(db.lister_cohortes(proprietaire_courant()))


@bp.get("/<int:cohorte_id>")
@connexion_requise
def lire(cohorte_id):
    cohorte = db.lire_cohorte(cohorte_id, proprietaire_courant())
    if cohorte is None:
        return jsonify({"erreur": "Cohorte introuvable."}), 404
    lignes = db.lire_lignes(cohorte_id)
    etiquetees = [l for l in lignes if l["abandon_reel"] is not None]
    metriques = {}
    if len(etiquetees) >= 30:
        metriques = current_app.moteur.metriques(
            np.array([l["abandon_reel"] for l in etiquetees]),
            np.array([l["p_noyau"] for l in etiquetees]),
            np.array([l["p_ml"] for l in etiquetees]))
        if metriques:
            metriques["effectif"] = len(etiquetees)
    return jsonify({
        "cohorte": cohorte,
        "lignes": lignes,
        "metriques": metriques,
        "memoire": current_app.moteur.valeurs_memoire() if est_le_jeu_de_test(cohorte, lignes) else None,
    })


@bp.post("/jeu-de-test")
@connexion_requise
def charger_jeu_de_test():
    return jsonify({"cohorte_id": current_app.charger_jeu_de_test()})


@bp.delete("/<int:cohorte_id>")
@connexion_requise
def supprimer(cohorte_id):
    """En mode demonstration, chacun ne peut effacer que ses propres imports :
    la cohorte de reference, partagee, n'est jamais supprimable."""
    efface = db.supprimer_cohorte(cohorte_id, proprietaire_courant())
    if MODE_DEMO and not efface:
        return jsonify({"erreur": "Cette cohorte est partagée et ne peut pas être supprimée."}), 403
    return jsonify({"ok": True})


@bp.post("/vider")
@connexion_requise
def vider():
    if MODE_DEMO:
        return jsonify({"erreur": "Indisponible en mode démonstration."}), 403
    db.vider()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- fiche d'explication d'un etudiant
bp_etudiants = Blueprint("api_etudiants", __name__, url_prefix="/api/etudiants")


@bp_etudiants.get("/<int:etudiant_id>")
@connexion_requise
def fiche(etudiant_id):
    """Fiche d'un etudiant de la base : scores, facteurs (SHAP), conseils, comparaison avec le devenir reel."""
    e = db.lire_etudiant(etudiant_id)
    if e is None:
        return jsonify({"erreur": "Étudiant introuvable."}), 404
    if not e["caracteristiques"]:
        return jsonify({"erreur": "Les valeurs de cet étudiant n'ont pas été conservées (base ancienne). Réimportez la cohorte."}), 409
    valeurs = json.loads(e["caracteristiques"])
    resultat = current_app.moteur.expliquer(valeurs)
    profil = []
    for champ in CHAMPS_FORMULAIRE:
        v = valeurs.get(champ)
        if v is None:
            affichee = None
        elif champ in CHAMPS_OUI_NON:
            affichee = "Oui" if v == 1 else "Non"
        elif champ == "Course":
            affichee = FILIERES.get(int(v), f"Code {int(v)}")
        else:
            affichee = int(v) if float(v).is_integer() else round(v, 2)
        profil.append({"variable": LIBELLES_CHAMPS[champ], "valeur": affichee, "fournie": v is not None})
    reel = e["abandon_reel"]
    verification = None
    if reel is not None:
        verification = {cle: ((p >= 0.5) == (reel == 1)) for cle, p in (("noyau", resultat["probabilite_noyau"]),
                                                                       ("ml", resultat["probabilite_ml"]))}
    cohorte = db.lire_cohorte(e["cohorte_id"], proprietaire_courant())
    if cohorte is None:
        return jsonify({"erreur": "Étudiant introuvable."}), 404
    return jsonify({
        "reference": e["reference"], "cohorte": cohorte["nom"],
        "devenir": DEVENIRS.get(e["devenir_reel"]) or ("Abandon" if reel == 1 else "Pas d'abandon" if reel == 0 else None),
        "abandon_reel": reel, "verification": verification,
        "resultat": resultat, "conseils": generer_conseils(valeurs), "profil": profil,
    })
