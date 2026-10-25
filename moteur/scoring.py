"""Moteur de calcul unique du dispositif d'alerte precoce.

Le tableau de bord, la saisie individuelle et l'import CSV passent TOUS par ce module :
c'est ce qui garantit qu'un meme etudiant recoit le meme score partout.

Chaine de calcul (inchangee par rapport a l'application d'origine, Chapitres II et III) :
  1. nettoyage des valeurs et bornage a la plage observee a l'entrainement ;
  2. completion des variables absentes par la mediane des 15 etudiants les plus proches ;
  3. normalisation (StandardScaler appris sur l'entrainement) ;
  4. estimateur a noyau gaussien (Nadaraya-Watson, k = 75) et Random Forest ;
  5. mode precoce (modeles dedies, sans 2e semestre) si aucune donnee de 2e semestre n'est fournie.
"""
from __future__ import annotations

import threading
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.neighbors import KNeighborsClassifier, NearestNeighbors
from sklearn.preprocessing import StandardScaler

import kernel_utils
from kernel_utils import noyau_gaussien  # noqa: F401  (requis pour deserialiser le modele a noyau)

from .referentiels import (
    CHAMPS_2E_SEMESTRE, CHAMPS_FORMULAIRE, CHAMPS_FORMULAIRE_PRECOCE, CHAMPS_OUI_NON,
    LIBELLES_CHAMPS, SEUIL_ELEVE, SEUIL_MOYEN, code_filiere,
)

RACINE = Path(__file__).resolve().parent.parent
NB_VOISINS_IMPUTATION = 15
LARGEURS_DE_BANDE = (1.0, 3.0, 8.0, 20.0)
NB_VOISINS_AFFICHES = 5
# Variables montrees pour chaque voisin dans l'explication du noyau (les memes que dans la fiche)
COLONNES_VOISINS = [
    "Curricular units 1st sem (approved)", "Curricular units 2nd sem (approved)",
    "Curricular units 1st sem (grade)", "Curricular units 2nd sem (grade)",
    "Tuition fees up to date", "Age at enrollment",
]
_EQUIVALENCES = {"oui": 1, "yes": 1, "vrai": 1, "true": 1, "non": 0, "no": 0, "faux": 0, "false": 0}


def categorie(probabilite: float) -> str:
    """Niveau de risque a partir de la probabilite AFFICHEE (arrondie a 3 decimales)."""
    p = round(float(probabilite), 3)
    if p >= SEUIL_ELEVE:
        return "eleve"
    if p >= SEUIL_MOYEN:
        return "moyen"
    return "faible"


def vers_nombre(valeur) -> float | None:
    """Convertit une valeur en nombre. Renvoie None pour une valeur vide ou absente.
    Accepte Oui/Non, Yes/No, Vrai/Faux et la virgule decimale (fichiers francais).
    Leve ValueError si la valeur est reellement inconvertible."""
    if valeur is None:
        return None
    if isinstance(valeur, (bool, np.bool_)):
        return float(valeur)
    if isinstance(valeur, (int, float, np.integer, np.floating)):
        v = float(valeur)
        return None if np.isnan(v) else v
    texte = str(valeur).strip().lower()
    if texte in ("", "nan", "none", "null", "na", "n/a"):
        return None
    if texte in _EQUIVALENCES:
        return float(_EQUIVALENCES[texte])
    return float(texte.replace(",", "."))


def libelle_variable(nom: str) -> str:
    return LIBELLES_CHAMPS.get(nom.strip(), nom.strip())


def verifier_coherence(reponses: dict) -> str | None:
    """Les unites validees ne peuvent pas depasser les unites inscrites (par semestre)."""
    for sem, libelle in (("1st", "1er"), ("2nd", "2e")):
        try:
            inscrites = vers_nombre(reponses.get(f"Curricular units {sem} sem (enrolled)"))
            validees = vers_nombre(reponses.get(f"Curricular units {sem} sem (approved)"))
        except ValueError:
            continue
        if inscrites is None or validees is None:
            continue
        if validees > inscrites:
            return (f"Incohérence au {libelle} semestre : {int(validees)} unités validées "
                    f"pour seulement {int(inscrites)} unités inscrites. "
                    f"Le nombre validé ne peut pas dépasser le nombre inscrit.")
    return None


class Moteur:
    def __init__(self, racine: Path = RACINE):
        modeles = racine / "models"
        self.noyau = joblib.load(modeles / "modele_noyau.joblib")
        self.rf = joblib.load(modeles / "modele_rf.joblib")
        self.scaler = joblib.load(modeles / "scaler.joblib")
        self.variables = list(joblib.load(modeles / "feature_names.joblib"))
        self.noyau_precoce = joblib.load(modeles / "modele_noyau_precoce.joblib")
        self.rf_precoce = joblib.load(modeles / "modele_rf_precoce.joblib")
        self.scaler_precoce = joblib.load(modeles / "scaler_precoce.joblib")
        self.variables_precoce = list(joblib.load(modeles / "feature_names_precoce.joblib"))
        self.defauts = joblib.load(modeles / "valeurs_par_defaut.joblib")
        self.bornes = joblib.load(modeles / "bornes_variables.joblib")
        self.resultats_memoire = joblib.load(modeles / "resultats_comparatifs.joblib")

        # Modele de repli (poids uniformes) pour les profils trop atypiques pour le noyau gaussien
        entrainement = joblib.load(racine / "data" / "donnees_pretraitees.joblib")
        self.noyau_repli = KNeighborsClassifier(n_neighbors=75, weights="uniform").fit(
            entrainement["X_train_bal"], entrainement["y_train_bal"])
        # Les lignes d'apprentissage sont les etudiants reels (en tete) suivis des profils synthetiques SMOTE
        self._nb_reels_apprentissage = len(entrainement["X_train_scaled"])

        # Base d'apprentissage pour la completion par voisins (les 4 424 etudiants du jeu UCI)
        base = pd.read_csv(racine / "data" / "data_avec_cible_binaire.csv")
        self._base = base[self.variables].to_numpy(dtype=float)
        self._voisins = {
            "complet": self._preparer_voisins(base, CHAMPS_FORMULAIRE),
            "precoce": self._preparer_voisins(base, CHAMPS_FORMULAIRE_PRECOCE),
        }
        self._shap = {"complet": shap.TreeExplainer(self.rf),
                      "precoce": shap.TreeExplainer(self.rf_precoce)}
        self._verrou = threading.Lock()

        # Table de correspondance : nom de colonne normalise -> nom canonique
        self.noms_canoniques = {self.normaliser(v): v for v in self.variables}

    # ------------------------------------------------------------------ utilitaires
    @staticmethod
    def normaliser(nom: str) -> str:
        return " ".join(str(nom).replace("\t", " ").split()).lower()

    def _preparer_voisins(self, base: pd.DataFrame, champs: list[str]):
        scaler = StandardScaler().fit(base[champs].to_numpy(dtype=float))
        index = NearestNeighbors(n_neighbors=NB_VOISINS_IMPUTATION).fit(
            scaler.transform(base[champs].to_numpy(dtype=float)))
        return champs, scaler, index

    # ------------------------------------------------------------------ preparation
    def nettoyer(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        """Renvoie (valeurs numeriques bornees, erreurs par ligne). Les colonnes sont les 36 variables ;
        une variable absente du fichier ou une cellule vide vaut NaN. Les colonnes du fichier sont
        reconnues sans tenir compte de la casse ni des espaces."""
        sortie = pd.DataFrame(np.nan, index=df.index, columns=self.variables)
        erreurs: dict = {}
        renommage = {}
        for col in df.columns:
            canonique = self.noms_canoniques.get(self.normaliser(col))
            if canonique is not None and canonique not in renommage.values():
                renommage[col] = canonique
        for col, canonique in renommage.items():
            serie = df[col]
            numerique = pd.to_numeric(serie, errors="coerce")
            suspects = numerique.isna() & serie.notna() & (serie.astype(str).str.strip() != "")
            for idx in serie.index[suspects]:
                try:
                    valeur = vers_nombre(serie.at[idx])
                    numerique.at[idx] = np.nan if valeur is None else valeur
                except (ValueError, TypeError):
                    if canonique == "Course":
                        # Filiere donnee par son nom : reconnue si elle figure dans le referentiel UCI,
                        # sinon laissee absente (estimee) ; son libelle reste affiche dans le tableau.
                        code = code_filiere(serie.at[idx])
                        numerique.at[idx] = np.nan if code is None else float(code)
                        continue
                    erreurs.setdefault(idx, f"valeur invalide pour « {libelle_variable(canonique)} » : {serie.at[idx]!r}")
            sortie[canonique] = numerique.astype(float)
        bornes_min = pd.Series({v: self.bornes[v][0] for v in self.variables})
        bornes_max = pd.Series({v: self.bornes[v][1] for v in self.variables})
        sortie = sortie.clip(lower=bornes_min, upper=bornes_max, axis=1)  # NaN reste NaN
        return sortie, erreurs

    def _requete_voisins(self, matrice: np.ndarray, lignes: np.ndarray,
                         colonnes: list[str], champs: list[str]) -> np.ndarray:
        """Construit la requete envoyee a l'index des voisins.

        L'index n'est bati que sur les champs du formulaire : on en extrait les
        colonnes utiles, et un champ du formulaire laisse vide prend sa valeur
        par defaut, sinon la distance ne pourrait pas etre calculee.
        """
        pos = [colonnes.index(c) for c in champs]
        requete = matrice[np.ix_(lignes, pos)].copy()
        for j, c in enumerate(champs):
            vide = np.isnan(requete[:, j])
            requete[vide, j] = self.defauts[c]
        return requete

    def _completer(self, valeurs: pd.DataFrame, mode: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Complete les valeurs absentes par la mediane des 15 voisins les plus proches.
        Renvoie les profils completes et le masque des valeurs estimees."""
        colonnes = self.variables if mode == "complet" else self.variables_precoce
        champs, scaler, index = self._voisins[mode]
        matrice = valeurs[colonnes].to_numpy(dtype=float).copy()
        manquants = np.isnan(matrice)
        lignes = np.where(manquants.any(axis=1))[0]
        if len(lignes):
            # la recherche des voisins se fait sur les seuls champs du formulaire
            requete = self._requete_voisins(matrice, lignes, colonnes, champs)
            _, voisins = index.kneighbors(scaler.transform(requete))
            colonnes_base = [self.variables.index(c) for c in colonnes]
            medianes = np.median(self._base[:, colonnes_base][voisins], axis=1)
            matrice[lignes] = np.where(manquants[lignes], medianes, matrice[lignes])
        profils = pd.DataFrame(matrice, index=valeurs.index, columns=colonnes)
        masque = pd.DataFrame(manquants, index=valeurs.index, columns=colonnes)
        return profils, masque

    # ------------------------------------------------------------------ prediction
    def _proba_noyau(self, modele, X: np.ndarray, repli: bool) -> np.ndarray:
        """Largeur de bande adaptative : on elargit le noyau avant d'abandonner l'approche a noyau."""
        with self._verrou:
            try:
                kernel_utils.LARGEUR_BANDE_ACTIVE = LARGEURS_DE_BANDE[0]
                return modele.predict_proba(X)[:, 1]
            except ValueError:
                pass
            sortie = np.empty(len(X))
            for i in range(len(X)):
                valeur = None
                for largeur in LARGEURS_DE_BANDE:
                    kernel_utils.LARGEUR_BANDE_ACTIVE = largeur
                    try:
                        valeur = float(modele.predict_proba(X[i:i + 1])[:, 1][0])
                        break
                    except ValueError:
                        continue
                if valeur is None:
                    valeur = float(self.noyau_repli.predict_proba(X[i:i + 1])[:, 1][0]) if repli else 0.5
                sortie[i] = valeur
            kernel_utils.LARGEUR_BANDE_ACTIVE = LARGEURS_DE_BANDE[0]
            return sortie

    def _modeles(self, mode: str) -> tuple:
        """Le couple (modele a noyau, normalisateur, variables) correspondant au mode."""
        if mode == "complet":
            return self.noyau, self.scaler, self.variables
        return self.noyau_precoce, self.scaler_precoce, self.variables_precoce

    # Le mode est "precoce" lorsque les 4 champs du 2e semestre sont tous vides :
    # on change alors de modeles plutot que d'imputer ces variables.
    def _predire(self, profils: pd.DataFrame, mode: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if mode == "complet":
            X = self.scaler.transform(profils)
            noyau, rf = self.noyau, self.rf
        else:
            X = self.scaler_precoce.transform(profils)      # modeles entraines sur 30 variables
            noyau, rf = self.noyau_precoce, self.rf_precoce
        return (self._proba_noyau(noyau, X, repli=(mode == "complet")),
                rf.predict_proba(X)[:, 1], X)

    def voisins_noyau(self, X: np.ndarray, mode: str) -> dict:
        """Explication du modele a noyau : les voisins qui fixent la probabilite, avec leur poids.

        Rejoue le calcul de Nadaraya-Watson avec la meme largeur de bande que `_proba_noyau` :
        probabilite = somme des poids des voisins ayant abandonne / somme des poids. Les lignes
        d'apprentissage au-dela des etudiants reels sont des profils synthetiques (SMOTE)."""
        modele, scaler, variables = self._modeles(mode)
        requete = X[:1]
        largeur = None
        with self._verrou:                                  # la largeur est un etat partage
            for essai in LARGEURS_DE_BANDE:                 # 1, puis 3, 8 et 20
                kernel_utils.LARGEUR_BANDE_ACTIVE = essai
                distances, indices = modele.kneighbors(requete, n_neighbors=modele.n_neighbors)
                poids = noyau_gaussien(distances[0])
                if poids.sum() > 0:                         # un voisin au moins pese
                    largeur = essai
                    break
            kernel_utils.LARGEUR_BANDE_ACTIVE = LARGEURS_DE_BANDE[0]
        indices = indices[0]
        issues = modele._y[indices]                         # 1 = abandon, 0 = non
        repli = None
        if largeur is None:
            # Aucun voisin ne pese : poids uniformes (profil complet) ou probabilite neutre 0,5 (mode precoce)
            poids = np.ones(len(indices))
            repli = "uniforme" if mode == "complet" else "neutre"
        part = poids / poids.sum()
        proba = float((part * issues).sum()) if repli != "neutre" else 0.5  # redonne la probabilite du modele
        reel = indices < self._nb_reels_apprentissage       # au-dela : profils SMOTE
        affiches = indices[:NB_VOISINS_AFFICHES]
        valeurs = scaler.inverse_transform(modele._fit_X[affiches])
        colonnes = [c for c in COLONNES_VOISINS if c in variables]
        pos = [variables.index(c) for c in colonnes]
        plus_proches = []
        for rang in range(len(affiches)):
            ligne = {"rang": rang + 1, "reel": bool(reel[rang]), "abandon": int(issues[rang]),
                     "distance": round(float(distances[0][rang]), 2), "poids": round(float(part[rang]), 4), "valeurs": []}
            for c, j in zip(colonnes, pos):
                v = float(valeurs[rang, j])
                ligne["valeurs"].append(("Oui" if v >= 0.5 else "Non") if c in CHAMPS_OUI_NON else round(v, 1))
            plus_proches.append(ligne)
        courts = {"Curricular units 1st sem (approved)": "Val. S1", "Curricular units 2nd sem (approved)": "Val. S2",
                  "Curricular units 1st sem (grade)": "Moy. S1", "Curricular units 2nd sem (grade)": "Moy. S2",
                  "Tuition fees up to date": "Frais à jour", "Age at enrollment": "Âge"}
        return {
            "nb_voisins": int(len(indices)),
            "nb_reels": int(reel.sum()), "nb_synthetiques": int((~reel).sum()),
            "part_poids_synthetique": round(float(part[~reel].sum()), 4),
            "poids_plus_proches": round(float(part[:NB_VOISINS_AFFICHES].sum()), 4),
            "largeur_bande": largeur, "repli": repli,
            "probabilite_recalculee": round(proba, 6),
            "abandons_parmi_plus_proches": int(sum(l["abandon"] for l in plus_proches)),
            "colonnes": [courts.get(c, libelle_variable(c)) for c in colonnes],
            "plus_proches": plus_proches,
        }

    def preparer(self, df: pd.DataFrame) -> dict:
        """Nettoyage + choix du mode + completion. Renvoie un dictionnaire de travail."""
        valeurs, erreurs = self.nettoyer(df)
        valides = valeurs.drop(index=list(erreurs))
        return {**self.preparer_valeurs(valides), "erreurs": erreurs, "valeurs": valides}

    def preparer_valeurs(self, valeurs: pd.DataFrame) -> dict:
        """A partir de valeurs deja nettoyees : choix du mode (complet ou precoce) puis completion."""
        precoce = valeurs[CHAMPS_2E_SEMESTRE].isna().all(axis=1)
        profils, masques = {}, {}
        for mode, filtre in (("complet", ~precoce), ("precoce", precoce)):
            if filtre.any():
                profils[mode], masques[mode] = self._completer(valeurs[filtre], mode)
        return {"profils": profils, "masques": masques}

    def scorer_valeurs(self, valeurs: pd.DataFrame) -> pd.DataFrame:
        """Score des valeurs deja nettoyees (index unique). Renvoie, dans l'ordre de `valeurs` :
        probabilite_noyau, probabilite_ml, categorie_noyau, categorie_ml, mode_calcul, nb_estimees."""
        prep = self.preparer_valeurs(valeurs)
        morceaux = []
        for mode, profils in prep["profils"].items():
            p_noyau, p_rf, _ = self._predire(profils, mode)
            morceaux.append(pd.DataFrame({
                "probabilite_noyau": np.round(p_noyau, 6),
                "probabilite_ml": np.round(p_rf, 6),
                "mode_calcul": mode,
                "nb_estimees": prep["masques"][mode].sum(axis=1).to_numpy(),
            }, index=profils.index))
        colonnes = ["probabilite_noyau", "probabilite_ml", "categorie_noyau", "categorie_ml",
                    "mode_calcul", "nb_estimees"]
        if not morceaux:
            return pd.DataFrame(columns=colonnes)
        res = pd.concat(morceaux).reindex(valeurs.index)
        res["categorie_noyau"] = res["probabilite_noyau"].map(categorie)
        res["categorie_ml"] = res["probabilite_ml"].map(categorie)
        return res[colonnes]

    def scorer(self, df: pd.DataFrame) -> pd.DataFrame:
        """Nettoie puis score un tableau brut. Les lignes invalides sont omises du resultat."""
        valeurs, erreurs = self.nettoyer(df)
        return self.scorer_valeurs(valeurs.drop(index=list(erreurs)))

    # ------------------------------------------------------------------ saisie individuelle
    def scorer_un(self, reponses: dict) -> dict:
        """Score un etudiant saisi au formulaire, avec explication SHAP (modele Random Forest)."""
        message = verifier_coherence(reponses)
        if message:
            raise ValueError(message)
        return self.expliquer(reponses)

    def expliquer(self, reponses: dict) -> dict:
        """Score un etudiant (saisi ou deja enregistre) et explique la prediction du Random Forest."""
        prep = self.preparer(pd.DataFrame([reponses]))
        if prep["erreurs"]:
            raise ValueError("Données invalides : " + next(iter(prep["erreurs"].values())))
        (mode, profils), = prep["profils"].items()
        p_noyau, p_rf, X = self._predire(profils, mode)
        p_noyau, p_rf = round(float(p_noyau[0]), 3), round(float(p_rf[0]), 3)
        variables = list(profils.columns)
        estimees = set(prep["masques"][mode].columns[prep["masques"][mode].iloc[0].to_numpy()])
        contributions = self._shap[mode](X).values[0, :, 1]
        ordre = sorted(zip(variables, contributions), key=lambda x: abs(x[1]), reverse=True)[:5]
        facteurs = []
        for nom, valeur_shap in ordre:
            libelle = libelle_variable(nom)
            sens = "augmente" if valeur_shap > 0 else "diminue"
            brute = float(profils.iloc[0][nom])
            affichee = ("Oui" if brute == 1 else "Non") if nom in CHAMPS_OUI_NON else round(brute, 1)
            facteurs.append({
                "variable": libelle, "valeur": affichee, "sens": sens,
                "contribution": round(float(valeur_shap), 4),
                "estimee": nom in estimees,
            })
        return {
            "probabilite_noyau": p_noyau, "probabilite_ml": p_rf,
            "categorie_noyau": categorie(p_noyau), "categorie_ml": categorie(p_rf),
            "mode_precoce": mode == "precoce",
            "facteurs_contributifs": facteurs,
            "nb_variables_estimees": len(estimees),
            "nb_variables_modele": len(variables),
            "voisins_noyau": self.voisins_noyau(X, mode),
        }

    # ------------------------------------------------------------------ indicateurs sur une cohorte
    def metriques(self, y_reel: np.ndarray, p_noyau: np.ndarray, p_ml: np.ndarray) -> dict:
        """AUC, exactitude et F1 (seuil 0,5), comme au Chapitre III."""
        from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
        if len(set(y_reel)) < 2:
            return {}
        sortie = {}
        for cle, p in (("noyau", p_noyau), ("ml", p_ml)):
            sortie[cle] = {
                "auc": float(roc_auc_score(y_reel, p)),
                "exactitude": float(accuracy_score(y_reel, p >= 0.5)),
                "f1": float(f1_score(y_reel, p >= 0.5)),
            }
        return sortie

    def valeurs_memoire(self) -> dict:
        """Valeurs publiees dans le memoire (Chapitre III), lues dans le fichier d'entrainement."""
        r = self.resultats_memoire
        cle_noyau = next(k for k in r if k.lower().startswith("approche"))
        cle_rf = next(k for k in r if k.lower().startswith("random"))
        return {
            "noyau": {"auc": r[cle_noyau]["auc"], "exactitude": r[cle_noyau]["accuracy"], "f1": r[cle_noyau]["f1"]},
            "ml": {"auc": r[cle_rf]["auc"], "exactitude": r[cle_rf]["accuracy"], "f1": r[cle_rf]["f1"]},
        }
