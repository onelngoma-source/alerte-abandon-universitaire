"""Dossiers d'accompagnement : la liste de travail des conseillers et les operations de suivi."""
import csv
import io

from flask import Blueprint, Response, jsonify, render_template, request
from sqlalchemy import and_, select

import db
from auth import connexion_requise, utilisateur_courant
from metier import dossiers as suivi
from metier.journal import tracer
from metier.regles import MOTIFS_CLOTURE, STATUTS

bp = Blueprint("dossiers", __name__)

VUES = {
    "mes": "Mes dossiers", "non_attribues": "Non attribués", "retard": "En retard", "a_revoir": "Risque en hausse",
    "ouverts": "Tous les dossiers ouverts", "clos": "Clos",
}


@bp.route("/dossiers")
@connexion_requise
def page():
    u = utilisateur_courant()
    with db.connexion() as c:
        promotions = db.lignes(c.execute(select(db.promotion.c.id, db.promotion.c.nom).order_by(db.promotion.c.id)))
        conseillers = db.lignes(c.execute(select(db.utilisateur.c.id, db.utilisateur.c.nom)
                                          .where(db.utilisateur.c.actif.is_(True)).order_by(db.utilisateur.c.nom)))
    vue = request.args.get("vue") or ("mes" if u["role"] == "conseiller" else "non_attribues")
    return render_template("dossiers.html", actif="dossiers", vues=VUES, vue=vue if vue in VUES else "mes",
                           promotions=promotions, conseillers=conseillers, statuts=STATUTS, motifs=MOTIFS_CLOTURE)


def requete_dossiers(u, vue, promotion_id=None, conseiller_id=None):
    conseiller = db.utilisateur.alias("conseiller")
    aujourd_hui = db.maintenant().date()
    q = (select(db.dossier.c.id, db.dossier.c.statut, db.dossier.c.echeance, db.dossier.c.ouvert_le, db.dossier.c.relance,
                db.dossier.c.maj_le, db.dossier.c.clos_le, db.dossier.c.motif_cloture, db.dossier.c.probabilite_ouverture,
                db.dossier.c.conseiller_id, conseiller.c.nom.label("conseiller"),
                db.etudiant.c.id.label("etudiant_id"), db.etudiant.c.matricule, db.etudiant.c.nom, db.etudiant.c.filiere,
                db.etudiant.c.probabilite, db.etudiant.c.moment, db.etudiant.c.facteur, db.etudiant.c.domaine_facteur,
                db.promotion.c.nom.label("promotion"))
         .select_from(db.dossier.join(db.etudiant, db.etudiant.c.id == db.dossier.c.etudiant_id)
                      .join(db.promotion, db.promotion.c.id == db.etudiant.c.promotion_id)
                      .outerjoin(conseiller, conseiller.c.id == db.dossier.c.conseiller_id)))
    ouverts = db.dossier.c.statut != "clos"
    filtres = {
        "mes": and_(ouverts, db.dossier.c.conseiller_id == u["id"]),
        "non_attribues": and_(ouverts, db.dossier.c.conseiller_id.is_(None)),
        "retard": and_(ouverts, db.dossier.c.echeance < aujourd_hui),
        "a_revoir": and_(ouverts, db.dossier.c.relance.is_(True)),
        "ouverts": ouverts,
        "clos": db.dossier.c.statut == "clos",
    }
    q = q.where(filtres[vue])
    if promotion_id:
        q = q.where(db.etudiant.c.promotion_id == promotion_id)
    if conseiller_id:
        q = q.where(db.dossier.c.conseiller_id == conseiller_id)
    return q


def _trier(lignes, vue):
    aujourd_hui = db.maintenant().date()
    for l in lignes:
        l["en_retard"] = l["statut"] != "clos" and l["echeance"] is not None and l["echeance"] < aujourd_hui
        l["libelle_statut"] = STATUTS[l["statut"]]
        l["motif"] = MOTIFS_CLOTURE.get(l["motif_cloture"])
        for k in ("echeance", "ouvert_le", "maj_le", "clos_le"):
            l[k] = l[k].isoformat() if l[k] else None
    if vue == "clos":
        return sorted(lignes, key=lambda l: l["clos_le"] or "", reverse=True)
    # d'abord les retards, puis les hausses de risque, puis l'echeance la plus proche, puis le risque
    return sorted(lignes, key=lambda l: (not l["en_retard"], not l["relance"], l["echeance"] or "9999", -l["probabilite"]))


@bp.get("/api/dossiers")
@connexion_requise
def lister():
    u = utilisateur_courant()
    vue = request.args.get("vue", "mes")
    if vue not in VUES:
        return jsonify({"erreur": "Vue inconnue."}), 400
    with db.connexion() as c:
        lignes = db.lignes(c.execute(requete_dossiers(u, vue, request.args.get("promotion", type=int),
                                                      request.args.get("conseiller", type=int))))
    return jsonify({"vue": vue, "dossiers": _trier(lignes, vue)})


@bp.get("/api/dossiers/export.csv")
@connexion_requise
def exporter():
    u = utilisateur_courant()
    vue = request.args.get("vue", "ouverts")
    if vue not in VUES:
        vue = "ouverts"
    with db.connexion() as c:
        lignes = _trier(db.lignes(c.execute(requete_dossiers(u, vue, request.args.get("promotion", type=int),
                                                             request.args.get("conseiller", type=int)))), vue)
        tracer(c, u, "export", "dossiers", None, {"vue": vue, "lignes": len(lignes)})
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(["Matricule", "Nom", "Promotion", "Filière", "Risque (%)", "Statut", "Conseiller", "Échéance", "En retard",
                "Ouvert le", "Motif de clôture"])
    for l in lignes:
        w.writerow([l["matricule"], l["nom"] or "", l["promotion"], l["filiere"] or "", f"{100 * l['probabilite']:.1f}".replace(".", ","),
                    l["libelle_statut"], l["conseiller"] or "", l["echeance"] or "", "Oui" if l["en_retard"] else "Non",
                    (l["ouvert_le"] or "")[:10], l["motif"] or ""])
    return Response("﻿" + sortie.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=dossiers_{vue}.csv"})


def _operation(dossier_id, fonction, action_journal):
    u = utilisateur_courant()
    donnees = request.get_json(silent=True) or {}
    try:
        with db.connexion() as c:
            d = fonction(c, u, donnees)
            tracer(c, u, action_journal, "dossier", dossier_id, {k: v for k, v in donnees.items() if k != "texte"} or None)
    except suivi.Refus as e:
        return jsonify({"erreur": str(e)}), e.code
    return jsonify({"ok": True, "dossier_id": d["id"], "etudiant_id": d["etudiant_id"], "statut": d["statut"]})


@bp.post("/api/dossiers/<int:dossier_id>/statut")
@connexion_requise
def statut(dossier_id):
    return _operation(dossier_id, lambda c, u, d: suivi.changer_statut(c, dossier_id, d.get("statut"), u, d.get("texte")),
                      "changement_statut")


@bp.post("/api/dossiers/<int:dossier_id>/attribution")
@connexion_requise
def attribution(dossier_id):
    return _operation(dossier_id, lambda c, u, d: suivi.attribuer(c, dossier_id, d.get("conseiller_id"), u), "attribution")


@bp.post("/api/dossiers/<int:dossier_id>/echeance")
@connexion_requise
def echeance(dossier_id):
    return _operation(dossier_id, lambda c, u, d: suivi.definir_echeance(c, dossier_id, d.get("echeance"), u), "echeance")


@bp.post("/api/dossiers/<int:dossier_id>/actions")
@connexion_requise
def action(dossier_id):
    return _operation(dossier_id, lambda c, u, d: suivi.ajouter_action(c, dossier_id, d.get("type"), d.get("texte"), u),
                      "action_dossier")


@bp.post("/api/dossiers/<int:dossier_id>/cloture")
@connexion_requise
def cloture(dossier_id):
    return _operation(dossier_id, lambda c, u, d: suivi.cloturer(c, dossier_id, d.get("motif"), d.get("texte"), u),
                      "cloture_dossier")


@bp.post("/api/dossiers/attribution-groupee")
@connexion_requise
def attribution_groupee():
    """Le responsable repartit plusieurs dossiers d'un coup."""
    u = utilisateur_courant()
    if u["role"] not in ("responsable", "admin"):
        return jsonify({"erreur": "Réservé au responsable et à l'administrateur."}), 403
    donnees = request.get_json(silent=True) or {}
    ids = [int(i) for i in donnees.get("dossiers", [])][:500]
    try:
        with db.connexion() as c:
            for i in ids:
                suivi.attribuer(c, i, donnees.get("conseiller_id"), u)
            tracer(c, u, "attribution_groupee", "dossier", None, {"nombre": len(ids), "conseiller_id": donnees.get("conseiller_id")})
    except suivi.Refus as e:
        return jsonify({"erreur": str(e)}), e.code
    return jsonify({"ok": True, "nombre": len(ids)})

