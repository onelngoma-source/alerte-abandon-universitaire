"""Import d'un fichier CSV dans une promotion (responsable, administrateur).

Nouvelle promotion : les etudiants sont crees. Promotion existante : les etudiants deja connus (meme matricule)
recoivent une nouvelle estimation (par exemple a la fin du 1er semestre), les autres sont ajoutes.
Dans les deux cas, la regle d'alerte ouvre les dossiers de suivi."""
import json

from flask import Blueprint, Response, current_app, jsonify, render_template, request

import db
from sqlalchemy import select

from auth import role_requis, utilisateur_courant
from moteur import cohortes
from moteur.referentiels import CHAMPS_FORMULAIRE, LIBELLES_CHAMPS, sans_accents
from moteur.scoring import libelle_variable

bp = Blueprint("import_csv", __name__)

# Champs proposes a l'etape de correspondance : les 13 variables principales (celles du formulaire),
# puis les 23 autres variables du jeu de donnees, dans une section repliee.
CHAMPS_PRINCIPAUX = {
    "reference": "Matricule de l'étudiant (indispensable pour les mises à jour)",
    "nom": "Nom de l'étudiant (facultatif)",
    "email": "Courriel (facultatif)",
    "telephone": "Téléphone (facultatif)",
    **{c: LIBELLES_CHAMPS[c] for c in CHAMPS_FORMULAIRE},
    "devenir": "Devenir réel : Dropout, Graduate ou Enrolled (facultatif)",
}


def champs_supplementaires(moteur):
    return {v: libelle_variable(v) for v in moteur.variables if v not in CHAMPS_FORMULAIRE}


@bp.route("/import")
@role_requis("responsable", "admin")
def page():
    with db.connexion() as c:
        promotions = db.lignes(c.execute(select(db.promotion.c.id, db.promotion.c.nom).order_by(db.promotion.c.id.desc())))
    return render_template("import.html", actif="import", promotions=promotions,
                           cible=request.args.get("promotion", type=int))


def _lire_fichier():
    if "fichier" not in request.files:
        return None, None, (jsonify({"erreur": "Aucun fichier fourni."}), 400)
    fichier = request.files["fichier"]
    df, erreur = cohortes.lire_csv(fichier.read())
    if erreur:
        return None, None, (jsonify({"erreur": erreur}), 400)
    return df, fichier.filename, None


@bp.post("/api/analyser-fichier")
@role_requis("responsable", "admin")
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
            elif champ == "nom" and nom in cohortes.NOMS_NOM:
                suggestions[champ] = colonne
            elif champ == "email" and nom in cohortes.NOMS_EMAIL:
                suggestions[champ] = colonne
            elif champ == "telephone" and nom in cohortes.NOMS_TELEPHONE:
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
    connus = (set(moteur.noms_canoniques) | cohortes.NOMS_REFERENCE | cohortes.NOMS_DEVENIR | cohortes.NOMS_ABANDON
              | cohortes.NOMS_NOM | cohortes.NOMS_EMAIL | cohortes.NOMS_TELEPHONE)
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
@role_requis("responsable", "admin")
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

    promotion_id = request.form.get("promotion", type=int)
    nom = (request.form.get("nom") or "").strip() or (nom_fichier or "Import CSV")
    with db.connexion() as c:
        if promotion_id and db.ligne(c.execute(select(db.promotion.c.id).where(db.promotion.c.id == promotion_id))) is None:
            return jsonify({"erreur": "Promotion introuvable."}), 400
        if not promotion_id:
            # un nom deja pris designe une nouvelle promotion homonyme : on le complete plutot que de fusionner en silence
            base, k = nom[:180], 2
            while db.ligne(c.execute(select(db.promotion.c.id).where(db.promotion.c.nom == nom))):
                nom, k = f"{base} ({k})", k + 1
    try:
        compte_rendu = cohortes.importer(moteur, df, nom, "etablissement", nom_fichier, promotion_id=promotion_id,
                                         utilisateur=utilisateur_courant())
    except ValueError as e:
        return jsonify({"erreur": str(e)}), 400
    return jsonify(compte_rendu)


@bp.get("/api/gabarit")
@role_requis("responsable", "admin")
def gabarit():
    contenu = ",".join(cohortes.EN_TETES_GABARIT) + "\n"
    return Response(contenu, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=gabarit_import.csv"})


@bp.get("/api/exemple")
@role_requis("responsable", "admin")
def exemple():
    """Telecharge le fichier du jeu de test : l'importer doit redonner le tableau de bord."""
    chemin = db.RACINE / "data" / db.FICHIER_JEU_DE_TEST
    return Response(chemin.read_bytes(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={db.FICHIER_JEU_DE_TEST}"})
