"""Administration : comptes et roles, journal d'activite, conservation des donnees (administrateur)."""
import secrets
import string
from datetime import timedelta

from flask import current_app, Blueprint, jsonify, render_template, request
from sqlalchemy import and_, delete, func, select
from werkzeug.security import generate_password_hash

import db
from auth import interdit_en_demo, role_requis, utilisateur_courant
from metier.journal import tracer
from metier.pilotage import aware
from metier.regles import DUREE_CONSERVATION_ANNEES, ROLES

bp = Blueprint("administration", __name__)

LIBELLES_JOURNAL = {
    "connexion": "Connexion", "echec_connexion": "Échec de connexion", "deconnexion": "Déconnexion",
    "changement_mot_de_passe": "Changement de mot de passe", "consultation_fiche": "Consultation d'une fiche",
    "import": "Import d'un fichier", "export": "Export", "changement_statut": "Changement de statut",
    "attribution": "Attribution", "attribution_groupee": "Attribution groupée", "echeance": "Échéance modifiée",
    "action_dossier": "Action de suivi", "cloture_dossier": "Clôture d'un dossier", "ouverture_dossier": "Ouverture manuelle",
    "mise_a_jour_resultats": "Mise à jour des résultats", "saisie_devenir": "Saisie du devenir réel", "referent": "Référent",
    "creation_compte": "Création de compte", "modification_compte": "Modification de compte",
    "reinitialisation_mdp": "Réinitialisation de mot de passe", "suppression_promotion": "Suppression d'une promotion",
    "purge": "Purge de données", "vidage_base": "Vidage de la base",
}


def _mot_de_passe_provisoire() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        mdp = "".join(secrets.choice(alphabet) for _ in range(12))
        if any(ch.isdigit() for ch in mdp) and any(ch.isalpha() for ch in mdp):
            return mdp


def _public(u):
    return {"id": u["id"], "identifiant": u["identifiant"], "nom": u["nom"], "email": u["email"], "role": u["role"],
            "libelle_role": ROLES[u["role"]], "actif": u["actif"], "doit_changer_mdp": u["doit_changer_mdp"],
            "derniere_connexion": u["derniere_connexion"].isoformat() if u["derniere_connexion"] else None}


@bp.route("/admin/utilisateurs")
@role_requis("admin")
def page_utilisateurs():
    return render_template("admin_utilisateurs.html", actif="admin_utilisateurs")


@bp.get("/api/admin/utilisateurs")
@role_requis("admin")
def utilisateurs():
    with db.connexion() as c:
        lignes = db.lignes(c.execute(select(db.utilisateur).order_by(db.utilisateur.c.actif.desc(), db.utilisateur.c.nom)))
    return jsonify([_public(u) for u in lignes])


@bp.post("/api/admin/utilisateurs")
@role_requis("admin")
@interdit_en_demo
def creer_utilisateur():
    d = request.get_json(silent=True) or {}
    identifiant = (d.get("identifiant") or "").strip().lower()
    nom = (d.get("nom") or "").strip()
    if not identifiant or not nom or d.get("role") not in ROLES:
        return jsonify({"erreur": "Identifiant, nom et rôle sont obligatoires."}), 400
    if not all(ch.isalnum() or ch in "._-" for ch in identifiant):
        return jsonify({"erreur": "L'identifiant ne doit contenir que des lettres, chiffres, points, tirets."}), 400
    mdp = _mot_de_passe_provisoire()
    with db.connexion() as c:
        if db.ligne(c.execute(select(db.utilisateur.c.id).where(db.utilisateur.c.identifiant == identifiant))):
            return jsonify({"erreur": "Cet identifiant existe déjà."}), 400
        uid = c.execute(db.utilisateur.insert().values(
            identifiant=identifiant, nom=nom, email=(d.get("email") or "").strip() or None, role=d["role"],
            mdp_hache=generate_password_hash(mdp), actif=True, doit_changer_mdp=True, cree_le=db.maintenant())).inserted_primary_key[0]
        tracer(c, utilisateur_courant(), "creation_compte", "utilisateur", uid, {"identifiant": identifiant, "role": d["role"]})
    return jsonify({"ok": True, "id": uid, "mot_de_passe_provisoire": mdp})


def _admins_actifs(c, sauf=None):
    q = select(func.count()).select_from(db.utilisateur).where(and_(db.utilisateur.c.role == "admin", db.utilisateur.c.actif.is_(True)))
    if sauf:
        q = q.where(db.utilisateur.c.id != sauf)
    return c.execute(q).scalar()


@bp.post("/api/admin/utilisateurs/<int:uid>")
@role_requis("admin")
@interdit_en_demo
def modifier_utilisateur(uid):
    d = request.get_json(silent=True) or {}
    moi = utilisateur_courant()
    with db.connexion() as c:
        u = db.ligne(c.execute(select(db.utilisateur).where(db.utilisateur.c.id == uid)))
        if u is None:
            return jsonify({"erreur": "Compte introuvable."}), 404
        valeurs = {}
        if "nom" in d and (d["nom"] or "").strip():
            valeurs["nom"] = d["nom"].strip()
        if "email" in d:
            valeurs["email"] = (d["email"] or "").strip() or None
        if "role" in d:
            if d["role"] not in ROLES:
                return jsonify({"erreur": "Rôle inconnu."}), 400
            valeurs["role"] = d["role"]
        if "actif" in d:
            valeurs["actif"] = bool(d["actif"])
        perd_admin = u["role"] == "admin" and (valeurs.get("role", "admin") != "admin" or valeurs.get("actif") is False)
        if perd_admin and _admins_actifs(c, sauf=uid) == 0:
            return jsonify({"erreur": "Il doit rester au moins un administrateur actif."}), 400
        if uid == moi["id"] and valeurs.get("actif") is False:
            return jsonify({"erreur": "Vous ne pouvez pas désactiver votre propre compte."}), 400
        c.execute(db.utilisateur.update().where(db.utilisateur.c.id == uid).values(**valeurs))
        if valeurs.get("actif") is False:
            # ses dossiers ouverts redeviennent non attribues : rien ne reste en souffrance chez un compte ferme
            c.execute(db.dossier.update().where(and_(db.dossier.c.conseiller_id == uid, db.dossier.c.statut != "clos"))
                      .values(conseiller_id=None))
        tracer(c, moi, "modification_compte", "utilisateur", uid, valeurs)
    return jsonify({"ok": True})


@bp.post("/api/admin/utilisateurs/<int:uid>/reinitialiser")
@role_requis("admin")
@interdit_en_demo
def reinitialiser(uid):
    mdp = _mot_de_passe_provisoire()
    with db.connexion() as c:
        if c.execute(db.utilisateur.update().where(db.utilisateur.c.id == uid)
                     .values(mdp_hache=generate_password_hash(mdp), doit_changer_mdp=True)).rowcount == 0:
            return jsonify({"erreur": "Compte introuvable."}), 404
        tracer(c, utilisateur_courant(), "reinitialisation_mdp", "utilisateur", uid)
    return jsonify({"ok": True, "mot_de_passe_provisoire": mdp})


# ---------------------------------------------------------------- journal d'activite
@bp.route("/admin/journal")
@role_requis("admin")
def page_journal():
    return render_template("admin_journal.html", actif="admin_journal", libelles=LIBELLES_JOURNAL)


@bp.get("/api/admin/journal")
@role_requis("admin")
def lire_journal():
    page = max(0, request.args.get("page", 0, type=int))
    q = select(db.journal).order_by(db.journal.c.cree_le.desc(), db.journal.c.id.desc())
    if request.args.get("action"):
        q = q.where(db.journal.c.action == request.args["action"])
    if request.args.get("identifiant"):
        q = q.where(db.journal.c.identifiant == request.args["identifiant"])
    with db.connexion() as c:
        lignes = db.lignes(c.execute(q.limit(51).offset(page * 50)))
    return jsonify({"page": page, "suivante": len(lignes) > 50,
                    "lignes": [{**l, "cree_le": l["cree_le"].isoformat(), "libelle": LIBELLES_JOURNAL.get(l["action"], l["action"])}
                               for l in lignes[:50]]})


# ---------------------------------------------------------------- donnees et conservation
@bp.route("/admin/donnees")
@role_requis("admin")
def page_donnees():
    return render_template("admin_donnees.html", actif="admin_donnees", duree=DUREE_CONSERVATION_ANNEES,
                           modele_version=current_app.moteur.version, base=db.url_base().split(":", 1)[0])


@bp.get("/api/admin/donnees")
@role_requis("admin")
def etat_donnees():
    limite = db.maintenant() - timedelta(days=365 * DUREE_CONSERVATION_ANNEES)
    with db.connexion() as c:
        promotions = db.lignes(c.execute(
            select(db.promotion.c.id, db.promotion.c.nom, db.promotion.c.origine, db.promotion.c.cree_le,
                   func.count(db.etudiant.c.id).label("effectif"), func.max(db.etudiant.c.maj_le).label("derniere_maj"))
            .select_from(db.promotion.outerjoin(db.etudiant, db.etudiant.c.promotion_id == db.promotion.c.id))
            .group_by(db.promotion.c.id).order_by(db.promotion.c.id)))
        totaux = {t.name: c.execute(select(func.count()).select_from(t)).scalar()
                  for t in (db.utilisateur, db.promotion, db.etudiant, db.evaluation, db.dossier, db.action, db.journal)}
    for p in promotions:
        derniere = aware(p["derniere_maj"] or p["cree_le"])
        p["a_purger"] = derniere < limite
        p["cree_le"], p["derniere_maj"] = p["cree_le"].isoformat(), derniere.isoformat()
    return jsonify({"promotions": promotions, "totaux": totaux, "duree_annees": DUREE_CONSERVATION_ANNEES})


@bp.post("/api/admin/purge")
@role_requis("admin")
@interdit_en_demo
def purger():
    """Supprime definitivement les promotions dont la conservation est echue (etudiants, estimations, dossiers)."""
    ids = [int(i) for i in (request.get_json(silent=True) or {}).get("promotions", [])]
    limite = db.maintenant() - timedelta(days=365 * DUREE_CONSERVATION_ANNEES)
    supprimees = []
    with db.connexion() as c:
        for pid in ids:
            p = db.ligne(c.execute(select(db.promotion.c.nom, db.promotion.c.cree_le, func.max(db.etudiant.c.maj_le).label("derniere"))
                                   .select_from(db.promotion.outerjoin(db.etudiant, db.etudiant.c.promotion_id == db.promotion.c.id))
                                   .where(db.promotion.c.id == pid).group_by(db.promotion.c.id)))
            if p is None or aware(p["derniere"] or p["cree_le"]) >= limite:
                continue
            c.execute(delete(db.promotion).where(db.promotion.c.id == pid))
            supprimees.append(p["nom"])
        tracer(c, utilisateur_courant(), "purge", "promotion", None, {"promotions": supprimees})
    return jsonify({"ok": True, "supprimees": supprimees})
