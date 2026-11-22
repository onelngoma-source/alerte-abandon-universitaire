"""Surveillance du modele sur l'etablissement lui-meme.

Le modele a appris sur une universite portugaise (cohortes 2008 a 2014). Des que le devenir reel d'etudiants de
l'etablissement est connu (fin d'annee), on recalcule ses performances sur EUX et on les compare a l'evaluation
de reference. Un ecart net est signale : il faut alors recalibrer ou reentrainer le modele (voir le guide).
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import brier_score_loss, roc_auc_score
from sqlalchemy import select

import db
from moteur.referentiels import LIBELLES_MOMENTS, SEUIL_ALERTE

EFFECTIF_MIN, ABANDONS_MIN = 100, 20
ECART_AUC, ECART_CALIBRATION = 0.05, 0.05


def etat(c, moteur, origine: str | None = None) -> dict:
    """Performances par moment sur les etudiants au devenir connu (derniere estimation de chacun)."""
    requete = (select(db.etudiant.c.probabilite, db.etudiant.c.moment, db.etudiant.c.abandon_reel, db.promotion.c.origine)
               .join(db.promotion, db.promotion.c.id == db.etudiant.c.promotion_id)
               .where(db.etudiant.c.abandon_reel.isnot(None)))
    if origine:
        requete = requete.where(db.promotion.c.origine == origine)
    lignes = db.lignes(c.execute(requete))
    sortie = []
    for m in ("T0", "T1", "T2"):
        sous = [l for l in lignes if l["moment"] == m]
        y = np.array([l["abandon_reel"] for l in sous], dtype=int)
        p = np.array([l["probabilite"] for l in sous], dtype=float)
        ref = moteur.reference["logistique"][m]
        bloc = {"moment": m, "libelle": LIBELLES_MOMENTS[m], "effectif": int(len(y)), "abandons": int(y.sum()),
                "reference": ref, "suffisant": bool(len(y) >= EFFECTIF_MIN and y.sum() >= ABANDONS_MIN and y.sum() < len(y))}
        if bloc["suffisant"]:
            alerte = p >= SEUIL_ALERTE
            bloc.update({
                "auc": float(roc_auc_score(y, p)), "brier": float(brier_score_loss(y, p)),
                "risque_moyen": float(p.mean()), "taux_observe": float(y.mean()),
                "rappel": float((alerte & (y == 1)).sum() / y.sum()),
                "precision": float((alerte & (y == 1)).sum() / max(alerte.sum(), 1)),
            })
            signaux = []
            if bloc["auc"] < ref["auc"] - ECART_AUC:
                signaux.append(f"Le classement des étudiants est nettement moins bon que la référence "
                               f"(ROC-AUC {bloc['auc']:.3f} contre {ref['auc']:.3f}).".replace(".", ",", 1))
            if abs(bloc["risque_moyen"] - bloc["taux_observe"]) > ECART_CALIBRATION:
                sens = "surestime" if bloc["risque_moyen"] > bloc["taux_observe"] else "sous-estime"
                signaux.append(f"Le modèle {sens} le risque : {round(100 * bloc['risque_moyen'])} % annoncé en moyenne, "
                               f"{round(100 * bloc['taux_observe'])} % d'abandons observés. Une recalibration est conseillée.")
            bloc["signaux"] = signaux
        sortie.append(bloc)
    return {"moments": sortie, "effectif_min": EFFECTIF_MIN, "abandons_min": ABANDONS_MIN,
            "devenirs_connus": len(lignes)}
