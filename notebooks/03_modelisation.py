"""
Chapitre II.3 - Demarche methodologique, etapes 3 et 4 :
Implementation des modeles (noyau + ML) et evaluation comparative
"""
import pathlib

# Racine du depot, deduite de l'emplacement de ce fichier : le script reste
# executable quel que soit le dossier d'ou on le lance.
RACINE = pathlib.Path(__file__).resolve().parents[1]
DONNEES, MODELES = RACINE / "data", RACINE / "models"
MODELES.mkdir(exist_ok=True)

import numpy as np
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from xgboost import XGBClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix
)

data = joblib.load(DONNEES / "donnees_pretraitees.joblib")
X_train_bal, y_train_bal = data["X_train_bal"], data["y_train_bal"]
X_test, y_test = data["X_test_scaled"], data["y_test"]

resultats = {}

def evaluer(nom, y_pred, y_proba):
    resultats[nom] = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred),
        "recall": recall_score(y_test, y_pred),
        "f1": f1_score(y_test, y_pred),
        "auc": roc_auc_score(y_test, y_proba),
        "matrice_confusion": confusion_matrix(y_test, y_pred).tolist(),
    }
    print(f"\n{nom}")
    print(f"  Accuracy  : {resultats[nom]['accuracy']:.3f}")
    print(f"  Precision : {resultats[nom]['precision']:.3f}")
    print(f"  Recall    : {resultats[nom]['recall']:.3f}")
    print(f"  F1-score  : {resultats[nom]['f1']:.3f}")
    print(f"  AUC-ROC   : {resultats[nom]['auc']:.3f}")

# ---------------------------------------------------------------
# 1. APPROCHE NON-PARAMETRIQUE A NOYAU
# Implementee via un estimateur a noyau gaussien (Nadaraya-Watson) :
# KNeighborsClassifier avec ponderation par distance approxime cette logique.
# Pour rester fidele a Nadaraya-Watson (moyenne ponderee par noyau, pas k-plus-proches-voisins
# stricts), on utilise ici un noyau gaussien explicite via 'weights=gaussian_kernel'.
# ---------------------------------------------------------------
import sys
sys.path.insert(0, str(RACINE))
from kernel_utils import noyau_gaussien

modele_noyau = KNeighborsClassifier(
    n_neighbors=75, weights=noyau_gaussien, metric="euclidean"
)
modele_noyau.fit(X_train_bal, y_train_bal)
y_pred_noyau = modele_noyau.predict(X_test)
y_proba_noyau = modele_noyau.predict_proba(X_test)[:, 1]
evaluer("Approche non-parametrique a noyau (noyau gaussien)", y_pred_noyau, y_proba_noyau)

# ---------------------------------------------------------------
# 2. MACHINE LEARNING - Random Forest
# ---------------------------------------------------------------
modele_rf = RandomForestClassifier(n_estimators=300, max_depth=12, random_state=42, n_jobs=-1)
modele_rf.fit(X_train_bal, y_train_bal)
y_pred_rf = modele_rf.predict(X_test)
y_proba_rf = modele_rf.predict_proba(X_test)[:, 1]
evaluer("Random Forest", y_pred_rf, y_proba_rf)

# ---------------------------------------------------------------
# 3. MACHINE LEARNING - XGBoost
# ---------------------------------------------------------------
modele_xgb = XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
                             random_state=42, eval_metric="logloss")
modele_xgb.fit(X_train_bal, y_train_bal)
y_pred_xgb = modele_xgb.predict(X_test)
y_proba_xgb = modele_xgb.predict_proba(X_test)[:, 1]
evaluer("XGBoost", y_pred_xgb, y_proba_xgb)

# ---------------------------------------------------------------
# 4. Regression logistique (reference classique, pour situer les deux familles)
# ---------------------------------------------------------------
modele_lr = LogisticRegression(max_iter=1000, random_state=42)
modele_lr.fit(X_train_bal, y_train_bal)
y_pred_lr = modele_lr.predict(X_test)
y_proba_lr = modele_lr.predict_proba(X_test)[:, 1]
evaluer("Regression logistique (reference)", y_pred_lr, y_proba_lr)

# Sauvegarde des modeles et resultats
joblib.dump(modele_noyau, MODELES / "modele_noyau.joblib")
joblib.dump(modele_rf, MODELES / "modele_rf.joblib")
joblib.dump(modele_xgb, MODELES / "modele_xgb.joblib")
joblib.dump(modele_lr, MODELES / "modele_lr.joblib")
joblib.dump(data["scaler"], MODELES / "scaler.joblib")
joblib.dump(data["feature_names"], MODELES / "feature_names.joblib")
joblib.dump(resultats, MODELES / "resultats_comparatifs.joblib")

print("\n" + "=" * 70)
print("TABLEAU COMPARATIF")
print("=" * 70)
print(f"{'Modele':<45}{'Accuracy':<10}{'AUC':<10}{'F1':<10}")
for nom, r in resultats.items():
    print(f"{nom:<45}{r['accuracy']:<10.3f}{r['auc']:<10.3f}{r['f1']:<10.3f}")
