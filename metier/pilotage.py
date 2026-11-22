"""Indicateurs de pilotage du dispositif : le suivi des alertes est-il fait, a temps, et par qui ?"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

import db
from .regles import DELAIS, MOTIFS_CLOTURE, ROLES, STATUTS, STATUTS_OUVERTS, TYPES_ACTION


def aware(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _dossiers(c, promotion_id=None):
    requete = (select(db.dossier, db.etudiant.c.promotion_id, db.etudiant.c.abandon_reel, db.etudiant.c.probabilite)
               .join(db.etudiant, db.etudiant.c.id == db.dossier.c.etudiant_id))
    if promotion_id:
        requete = requete.where(db.etudiant.c.promotion_id == promotion_id)
    return db.lignes(c.execute(requete))


def indicateurs(c, promotion_id: int | None = None) -> dict:
    aujourd_hui = db.maintenant().date()
    dossiers = _dossiers(c, promotion_id)
    ouverts = [d for d in dossiers if d["statut"] != "clos"]
    en_retard = [d for d in ouverts if d["echeance"] is not None and d["echeance"] < aujourd_hui]

    delais = [(aware(d["premier_contact_le"]) - aware(d["ouvert_le"])).total_seconds() / 86400
              for d in dossiers if d["premier_contact_le"] is not None]
    a_temps = sum(1 for x in delais if x <= DELAIS["a_contacter"])

    utilisateurs = db.lignes(c.execute(select(db.utilisateur).order_by(db.utilisateur.c.nom)))
    il_y_a_30j = db.maintenant() - timedelta(days=30)
    charge = []
    for u in utilisateurs:
        siens = [d for d in dossiers if d["conseiller_id"] == u["id"]]
        if u["role"] != "conseiller" and not siens:
            continue
        charge.append({
            "id": u["id"], "nom": u["nom"], "role": ROLES[u["role"]], "actif": u["actif"],
            "ouverts": sum(d["statut"] != "clos" for d in siens),
            "en_retard": sum(d in en_retard for d in siens),
            "a_revoir": sum(d["statut"] != "clos" and d["relance"] for d in siens),
            "clos_30j": sum(d["statut"] == "clos" and aware(d["clos_le"]) >= il_y_a_30j for d in siens),
        })

    ids = {d["id"] for d in dossiers}
    actions = db.lignes(c.execute(select(db.action.c.type, db.action.c.dossier_id)
                                  .where(db.action.c.cree_le >= db.maintenant() - timedelta(days=90))))
    par_type = {}
    for a in actions:
        if a["dossier_id"] in ids and a["type"] in TYPES_ACTION:
            par_type[a["type"]] = par_type.get(a["type"], 0) + 1

    # resultats en fin d'annee, quand le devenir reel est connu (association, pas preuve d'effet)
    groupes = {"accompagnes": [], "alertes_sans_entretien": []}
    for d in dossiers:
        if d["abandon_reel"] is None:
            continue
        accompagne = d["statut"] in ("entretien", "accompagnement") or d["motif_cloture"] == "accompagnement_termine"
        groupes["accompagnes" if accompagne else "alertes_sans_entretien"].append(d["abandon_reel"])
    resultats = {k: {"effectif": len(v), "taux_abandon": (sum(v) / len(v)) if v else None} for k, v in groupes.items()}

    return {
        "ouverts": len(ouverts),
        "non_attribues": sum(d["conseiller_id"] is None for d in ouverts),
        "en_retard": len(en_retard),
        "a_revoir": sum(d["relance"] for d in ouverts),
        "clos": len(dossiers) - len(ouverts),
        "par_statut": [{"statut": s, "libelle": STATUTS[s], "nombre": sum(d["statut"] == s for d in dossiers)}
                       for s in STATUTS_OUVERTS + ["clos"]],
        "delai_median_jours": round(statistics.median(delais), 1) if delais else None,
        "part_contactes_a_temps": (a_temps / len(delais)) if delais else None,
        "delai_cible_jours": DELAIS["a_contacter"],
        "charge": charge,
        "actions_90j": [{"type": k, "libelle": TYPES_ACTION[k], "nombre": v} for k, v in sorted(par_type.items(), key=lambda x: -x[1])],
        "motifs": [{"motif": m, "libelle": MOTIFS_CLOTURE[m], "nombre": sum(d["motif_cloture"] == m for d in dossiers)}
                   for m in MOTIFS_CLOTURE if any(d["motif_cloture"] == m for d in dossiers)],
        "resultats": resultats,
    }
