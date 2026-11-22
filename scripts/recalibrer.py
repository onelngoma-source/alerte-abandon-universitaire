"""Recalibrer le modele sur les etudiants de l'etablissement.

Le modele a appris sur une autre universite : son classement des etudiants (qui est plus a risque que qui)
se transpose souvent bien, mais le NIVEAU des probabilites peut etre decale (taux d'abandon different).
Ce script ajuste, pour chaque moment (inscription, 1er semestre, 2e semestre), une correction de Platt
p' = sigmoide(a + b x logit(p)) sur des promotions PASSEES dont le devenir est connu.

    python scripts/recalibrer.py promotions_passees.csv            affiche le diagnostic, n'ecrit rien
    python scripts/recalibrer.py promotions_passees.csv --ecrire   ecrit models/recalibration.joblib

Le fichier a le format d'import habituel (matricule, variables, colonne « Target » ou « devenir »).
Il faut au moins 300 etudiants et 50 abandons par moment ; sinon, la correction est refusee pour ce moment.
La correction est evaluee par validation croisee (5 plis) avant d'etre retenue : si elle n'ameliore pas le
score de Brier, elle n'est pas ecrite. Redemarrez l'application ensuite : la version du modele affichee change.
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.environ["RECALIBRATION"] = str(RACINE / "models" / "__aucune__")  # on part toujours du modele d'origine

from moteur import cohortes  # noqa: E402
from moteur.scoring import Moteur, recalibrer  # noqa: E402
from moteur.variables import semestre  # noqa: E402

EFFECTIF_MIN, ABANDONS_MIN = 300, 50


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def main():
    parseur = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parseur.add_argument("fichier")
    parseur.add_argument("--ecrire", action="store_true")
    args = parseur.parse_args()

    moteur = Moteur()
    df, erreur = cohortes.lire_csv(Path(args.fichier).read_bytes())
    if erreur:
        sys.exit(erreur)
    colonne = next((c for c in df.columns if moteur.normaliser(c) in cohortes.NOMS_DEVENIR), None)
    if colonne is None:
        sys.exit("Colonne du devenir réel introuvable (Target, devenir).")
    devenir = df[colonne].map(lambda v: moteur.normaliser(v))
    connus = devenir.isin(["dropout", "abandon", "graduate", "diplome", "diplômé", "enrolled", "inscrit"])
    df, devenir = df[connus].reset_index(drop=True), devenir[connus].reset_index(drop=True)
    y = devenir.isin(["dropout", "abandon"]).astype(int).to_numpy()
    valeurs, erreurs = moteur.nettoyer(df)
    garder = ~valeurs.index.isin(list(erreurs))
    valeurs, y = valeurs[garder], y[garder]
    print(f"{len(y)} étudiants au devenir connu, dont {y.sum()} abandons ({100 * y.mean():.1f} %).\n")

    parametres = {}
    for m in ("T0", "T1", "T2"):
        v = valeurs.copy()
        if m != "T2":
            v[semestre("2nd")] = np.nan
        if m == "T0":
            v[semestre("1st")] = np.nan
        if m != "T0" and v[semestre("1st")].isna().all().all():
            print(f"{m} : pas de résultats de semestre dans le fichier, moment ignoré.")
            continue
        p = moteur.scorer_valeurs(v)["probabilite_ml"].to_numpy(float)
        if len(y) < EFFECTIF_MIN or y.sum() < ABANDONS_MIN:
            print(f"{m} : effectif insuffisant ({len(y)} étudiants, {y.sum()} abandons ; il en faut {EFFECTIF_MIN} et {ABANDONS_MIN}).")
            continue
        # evaluation honnete de la correction : ajustee sur 4/5, mesuree sur le 1/5 restant
        corrige = np.zeros_like(p)
        for app, val in StratifiedKFold(5, shuffle=True, random_state=0).split(p.reshape(-1, 1), y):
            lr = LogisticRegression(C=1e6).fit(logit(p[app]).reshape(-1, 1), y[app])
            corrige[val] = recalibrer(p[val], lr.intercept_[0], lr.coef_[0, 0])
        avant, apres = brier_score_loss(y, p), brier_score_loss(y, corrige)
        print(f"{m} : ROC-AUC {roc_auc_score(y, p):.3f} · risque moyen annoncé {100 * p.mean():.1f} % pour {100 * y.mean():.1f} % "
              f"d'abandons · Brier {avant:.4f} → {apres:.4f} après correction (validation croisée)")
        if apres < avant:
            lr = LogisticRegression(C=1e6).fit(logit(p).reshape(-1, 1), y)
            parametres[m] = (float(lr.intercept_[0]), float(lr.coef_[0, 0]))
            print(f"     correction retenue : a = {parametres[m][0]:.3f}, b = {parametres[m][1]:.3f}")
        else:
            print("     correction non retenue : elle n'améliore pas les probabilités.")

    if not parametres:
        print("\nAucune correction retenue : le modèle d'origine reste en service.")
        return
    if args.ecrire:
        chemin = RACINE / "models" / "recalibration.joblib"
        joblib.dump({"parametres": parametres, "date": date.today().strftime("%d/%m/%Y"), "effectif": int(len(y)),
                     "fichier": Path(args.fichier).name}, chemin)
        print(f"\nÉcrit : {chemin}. Redémarrez l'application pour l'appliquer.")
    else:
        print("\nRien n'a été écrit (ajoutez --ecrire pour enregistrer la correction).")


if __name__ == "__main__":
    main()
