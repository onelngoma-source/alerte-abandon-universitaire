"""Volet 3 : import d'un fichier CSV. Le resultat est le MEME tableau que le tableau de bord."""
import json

from flask import Blueprint, Response, current_app, jsonify, render_template, request

import db
from auth import connexion_requise, proprietaire_courant
from moteur import cohortes
from moteur.referentiels import CHAMPS_FORMULAIRE, LIBELLES_CHAMPS, sans_accents
from moteur.scoring import libelle_variable

bp = Blueprint("import_csv", __name__)

# Champs proposes a l'etape de correspondance : les 13 variables principales (celles du formulaire),
# puis les 23 autres variables du jeu de donnees, dans une section repliee.
CHAMPS_PRINCIPAUX = {
    "reference": "Référence de l'étudiant (facultatif)",
    **{c: LIBELLES_CHAMPS[c] for c in CHAMPS_FORMULAIRE},
    "devenir": "Devenir réel : Dropout, Graduate ou Enrolled (facultatif)",
}


def champs_supplementaires(moteur):
    return {v: libelle_variable(v) for v in moteur.variables if v not in CHAMPS_FORMULAIRE}


@bp.route("/import")
@connexion_requise
def page():
    return render_template("import.html", actif="import")


def _lire_fichier():
    if "fichier" not in request.files:
        return None, None, (jsonify({"erreur": "Aucun fichier fourni."}), 400)
    fichier = request.files["fichier"]
    df, erreur = cohortes.lire_csv(fichier.read())
    if erreur:
        return None, None, (jsonify({"erreur": erreur}), 400)
    return df, fichier.filename, None


@bp.post("/api/analyser-fichier")
@connexion_requise
def analyser():
    """Etape 1 : lit les en-tetes sans calculer. Indique si une correspondance des colonnes est necessaire."""
    df, _, echec = _lire_fichier()
    if echec:
        return echec
    moteur = current_app.moteur
    presentes = {moteur.normaliser(c) for c in df.columns}
    reconnus = [c for c in CHAMPS_FORMULAIRE if moteur.normaliser(c) in presentes]
    supplementaires = champs_supplementaires(moteur)
    suggestions = {}
    for champ in [*CHAMPS_PRINCIPAUX, *supplementaires]:
        for colonne in df.columns:
            nom = moteur.normaliser(colonne)
            if champ in moteur.variables and nom == moteur.normaliser(champ):
                suggestions[champ] = colonne
            elif champ == "reference" and nom in cohortes.NOMS_REFERENCE:
                suggestions[champ] = colonne
            elif champ == "devenir" and nom in cohortes.NOMS_DEVENIR:
                suggestions[champ] = colonne
    # Deuxieme passe : colonne dont le nom CONTIENT le nom de la variable (anglais ou libelle francais),
    # proposee seulement si une seule colonne convient et qu'elle n'est pas deja prise.
    prises = set(suggestions.values())
    # les noms les plus longs d'abord : « Note de la qualification precedente » avant « Qualification precedente »
    for champ in sorted(moteur.variables, key=lambda c: -max(len(c), len(libelle_variable(c)))):
        if champ in suggestions:
            continue
        motifs = {sans_accents(moteur.normaliser(champ)), sans_accents(libelle_variable(champ))}
        candidates = [c for c in df.columns if c not in prises
                      and any(m and m in sans_accents(moteur.normaliser(c)) for m in motifs)]
        if len(candidates) == 1:
            suggestions[champ] = candidates[0]
            prises.add(candidates[0])
    connus = set(moteur.noms_canoniques) | cohortes.NOMS_REFERENCE | cohortes.NOMS_DEVENIR | cohortes.NOMS_ABANDON
    non_reconnues = [c for c in df.columns if moteur.normaliser(c) not in connus and c not in suggestions.values()]
    return jsonify({
        # l'etape de correspondance s'impose si une variable principale manque, ou si le fichier
        # contient des colonnes que l'on ne sait pas associer (elles pourraient etre des variables du modele)
        "mapping_necessaire": len(reconnus) < len(CHAMPS_FORMULAIRE) or bool(non_reconnues),
        "champs_attendus": CHAMPS_PRINCIPAUX,
        "champs_supplementaires": supplementaires,
        "colonnes_du_fichier": list(df.columns),
        "colonnes_non_reconnues": non_reconnues,
        "suggestions": suggestions,
        "nombre_lignes": len(df),
    })


@bp.post("/api/import")
@connexion_requise
def importer():
    """Etape 2 : calcule, enregistre la cohorte en base et renvoie son identifiant."""
    df, nom_fichier, echec = _lire_fichier()
    if echec:
        return echec
    moteur = current_app.moteur
    try:
        correspondance = json.loads(request.form.get("mapping") or "null")
    except json.JSONDecodeError:
        return jsonify({"erreur": "Correspondance de colonnes illisible."}), 400
    df = cohortes.appliquer_correspondance(df, correspondance, moteur)

    presentes = {moteur.normaliser(c) for c in df.columns}
    reconnus = [c for c in CHAMPS_FORMULAIRE if moteur.normaliser(c) in presentes]
    if not correspondance and len(reconnus) < 5:
        return jsonify({
            "erreur": (f"Structure de fichier non reconnue : seulement {len(reconnus)} des {len(CHAMPS_FORMULAIRE)} "
                       "colonnes attendues ont été retrouvées. Vérifiez les en-têtes ou utilisez la correspondance manuelle."),
            "colonnes_attendues": CHAMPS_FORMULAIRE, "colonnes_trouvees": list(df.columns)}), 400

    nom = (request.form.get("nom") or "").strip() or (nom_fichier or "Import CSV")
    try:
        compte_rendu = cohortes.importer(moteur, df, nom, "import", nom_fichier,
                                         proprietaire=proprietaire_courant())
    except ValueError as e:
        return jsonify({"erreur": str(e)}), 400
    return jsonify(compte_rendu)


@bp.get("/api/gabarit")
@connexion_requise
def gabarit():
    contenu = ",".join(cohortes.EN_TETES_GABARIT) + "\n"
    return Response(contenu, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=gabarit_import.csv"})


@bp.get("/api/exemple")
@connexion_requise
def exemple():
    """Telecharge le fichier du jeu de test : l'importer doit redonner le tableau de bord."""
    chemin = db.RACINE / "data" / "jeu_de_test_1328.csv"
    return Response(chemin.read_bytes(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=jeu_de_test_1328.csv"})
