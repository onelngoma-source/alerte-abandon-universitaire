"""Moteur de calcul unique du dispositif d'alerte precoce.

Le tableau de bord, la saisie individuelle et l'import CSV passent TOUS par ce module :
c'est ce qui garantit qu'un meme etudiant recoit le meme score partout.

Chaine de calcul (projet de recherche github.com/onelngoma-source/abandon-universitaire) :
  1. nettoyage des valeurs et bornage a la plage observee sur le developpement (cohortes 2008 a 2014) ;
  2. choix du moment selon l'information fournie : T0 (inscription), T1 (fin du 1er semestre)
     ou T2 (fin du 2e semestre), un modele par moment ;
  3. valeurs absentes : categorie la plus frequente pour les variables a codes et oui/non,
     mediane du developpement (apprise dans le modele) pour les variables numeriques ;
  4. deux estimations : la regression logistique (modele retenu, probabilites calibrees)
     et l'estimateur de Nadaraya-Watson (approche a noyau, pour comparaison) ;
  5. alerte si la probabilite atteint 1/6 (un abandon manque coute 5 accompagnements inutiles).
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .referentiels import (
    CHAMPS_OUI_NON, FILIERES, LIBELLES_CHAMPS, LIBELLES_MOMENTS, SEUIL_ALERTE, SEUIL_ELEVE, SEUIL_MOYEN,
    code_filiere,
)
from .variables import BINAIRES, MOMENTS, NOMINALES, preparer, semestre

RACINE = Path(__file__).resolve().parent.parent
NB_VOISINS_AFFICHES = 5
CATEGORIELLES = set(NOMINALES) | set(BINAIRES) | {"Nacionality"}
_EQUIVALENCES = {"oui": 1, "yes": 1, "vrai": 1, "true": 1, "non": 0, "no": 0, "faux": 0, "false": 0}
_COURTS = {"Curricular units 1st sem (approved)": "Val. S1", "Curricular units 2nd sem (approved)": "Val. S2",
           "Curricular units 1st sem (grade)": "Moy. S1", "Curricular units 2nd sem (grade)": "Moy. S2",
           "Tuition fees up to date": "Frais à jour", "Age at enrollment": "Âge"}


def categorie(probabilite: float) -> str:
    """Niveau de risque a partir de la probabilite AFFICHEE (arrondie a 3 decimales)."""
    p = round(float(probabilite), 3)
    if p >= SEUIL_ELEVE:
        return "eleve"
    if p >= round(SEUIL_MOYEN, 3):
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


def variables_du_moment(moment: str) -> list[str]:
    """Les variables brutes utilisees par le modele d'un moment."""
    from .variables import NUMERIQUES_T0
    return NOMINALES + BINAIRES + NUMERIQUES_T0 + [c for s in MOMENTS[moment] for c in semestre(s)]


class Moteur:
    def __init__(self, racine: Path = RACINE):
        art = joblib.load(racine / "models" / "modeles.joblib")
        self.modeles = art["modeles"]                     # {moment: {"logistique": ..., "noyau": ...}}
        self.moyennes = art["moyennes_transformees"]      # profil moyen du developpement (explications)
        self.reglages = art["reglages"]
        self.variables = list(art["variables"])           # les 36 colonnes du jeu UCI
        self.bornes = art["bornes"]
        self.defauts = art["defauts"]
        self.reference = art["reference"]                 # evaluation finale pre-enregistree (cohortes 2015 a 2017)
        self._voisins = art["voisins"]
        self.noms_canoniques = {self.normaliser(v): v for v in self.variables}

    # ------------------------------------------------------------------ utilitaires
    @staticmethod
    def normaliser(nom: str) -> str:
        return " ".join(str(nom).replace("\t", " ").split()).lower()

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

    @staticmethod
    def moments(valeurs: pd.DataFrame) -> pd.Series:
        """T2 si une donnee du 2e semestre est fournie, T1 si une donnee du 1er l'est, sinon T0."""
        s2 = valeurs[semestre("2nd")].notna().any(axis=1)
        s1 = valeurs[semestre("1st")].notna().any(axis=1)
        return pd.Series(np.where(s2, "T2", np.where(s1, "T1", "T0")), index=valeurs.index)

    def _completer(self, valeurs: pd.DataFrame, moment: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Variables a codes et oui/non absentes : categorie la plus frequente du developpement.
        Les numeriques absentes restent vides : le modele les remplace par la mediane apprise.
        Renvoie les valeurs completees et le masque des valeurs estimees (variables du moment)."""
        utiles = variables_du_moment(moment)
        masque = valeurs[utiles].isna()
        completees = valeurs.copy()
        for c in utiles:
            if c in CATEGORIELLES:
                completees[c] = completees[c].fillna(self.defauts[c])
        return completees, masque

    def _probabilites(self, completees: pd.DataFrame, moment: str):
        X, *_ = preparer(completees, moment)
        m = self.modeles[moment]
        return (m["noyau"].predict_proba(X)[:, 1], m["logistique"].predict_proba(X)[:, 1], X)

    # ------------------------------------------------------------------ scores d'une cohorte
    def scorer_valeurs(self, valeurs: pd.DataFrame) -> pd.DataFrame:
        """Score des valeurs deja nettoyees (index unique). Renvoie, dans l'ordre de `valeurs` :
        probabilite_noyau, probabilite_ml (regression logistique), categorie_noyau, categorie_ml,
        mode_calcul (T0, T1 ou T2), nb_estimees."""
        colonnes = ["probabilite_noyau", "probabilite_ml", "categorie_noyau", "categorie_ml",
                    "mode_calcul", "nb_estimees"]
        if valeurs.empty:
            return pd.DataFrame(columns=colonnes)
        moments = self.moments(valeurs)
        morceaux = []
        for moment in MOMENTS:
            filtre = moments == moment
            if not filtre.any():
                continue
            completees, masque = self._completer(valeurs[filtre], moment)
            p_noyau, p_ml, _ = self._probabilites(completees, moment)
            morceaux.append(pd.DataFrame({
                "probabilite_noyau": np.round(p_noyau, 6),
                "probabilite_ml": np.round(p_ml, 6),
                "mode_calcul": moment,
                "nb_estimees": masque.sum(axis=1).to_numpy(),
            }, index=completees.index))
        res = pd.concat(morceaux).reindex(valeurs.index)
        res["categorie_noyau"] = res["probabilite_noyau"].map(categorie)
        res["categorie_ml"] = res["probabilite_ml"].map(categorie)
        return res[colonnes]

    def scorer(self, df: pd.DataFrame) -> pd.DataFrame:
        """Nettoie puis score un tableau brut. Les lignes invalides sont omises du resultat."""
        valeurs, erreurs = self.nettoyer(df)
        return self.scorer_valeurs(valeurs.drop(index=list(erreurs)))

    # ------------------------------------------------------------------ explications
    def contributions(self, X: pd.DataFrame, moment: str) -> dict[str, float]:
        """Contribution de chaque variable au logit de la regression logistique, par rapport a
        l'etudiant moyen du developpement : coefficient x (valeur - valeur moyenne). Pour un modele
        lineaire, ce sont exactement les valeurs de Shapley ; leur somme vaut logit(p) - logit de reference."""
        modele = self.modeles[moment]["logistique"]
        prep, lr = modele.named_steps["prep"], modele.named_steps["m"]
        z = prep.transform(X)[0]
        brut = lr.coef_[0] * (z - self.moyennes[moment])
        totaux: dict[str, float] = {}
        for nom, c in zip(prep.get_feature_names_out(), brut):
            bloc, variable = nom.split("__", 1)
            if bloc == "nominales":
                variable = next(v for v in NOMINALES if variable.startswith(v + "_"))
            elif variable.startswith("missingindicator_"):
                variable = variable[len("missingindicator_"):]
            totaux[variable] = totaux.get(variable, 0.0) + float(c)
        return totaux

    def logit_reference(self, moment: str) -> float:
        """Logit de l'etudiant moyen du developpement : point de depart des contributions."""
        lr = self.modeles[moment]["logistique"].named_steps["m"]
        return float(lr.intercept_[0] + lr.coef_[0] @ self.moyennes[moment])

    def voisins_noyau(self, X: pd.DataFrame, moment: str) -> dict:
        """Explication de l'approche a noyau : TOUS les etudiants du developpement comptent, avec un poids
        qui decroit avec la distance. On montre les 5 plus lourds ; la probabilite recalculee a partir
        de tous les poids est exactement celle du modele."""
        modele = self.modeles[moment]["noyau"]
        nw = modele.named_steps["m"]
        poids, distances = nw.poids(modele.named_steps["prep"].transform(X))
        poids, distances = poids[0], distances[0]
        ordre = np.argsort(-poids)[:NB_VOISINS_AFFICHES]
        # on ne montre que les informations connues au moment de l'estimation
        connues = set(variables_du_moment(moment))
        positions = [j for j, c in enumerate(self._voisins["colonnes"]) if c in connues]
        colonnes = [self._voisins["colonnes"][j] for j in positions]
        plus_proches = []
        for rang, i in enumerate(ordre, start=1):
            valeurs = []
            for c, j in zip(colonnes, positions):
                v = self._voisins["valeurs"][i][j]
                valeurs.append(("Oui" if v >= 0.5 else "Non") if c in CHAMPS_OUI_NON else round(float(v), 1))
            plus_proches.append({"rang": rang, "abandon": int(nw.y_[i]), "cohorte": int(self._voisins["cohorte"][i]),
                                 "distance": round(float(distances[i]), 2), "poids": round(float(poids[i]), 4),
                                 "valeurs": valeurs})
        return {
            "nb_etudiants": int(len(poids)),
            "nombre_effectif": round(float(1 / (poids ** 2).sum()), 1),
            "largeur_bande": round(float(nw.bande), 3),
            "poids_plus_proches": round(float(poids[ordre].sum()), 4),
            "probabilite_recalculee": round(float(poids @ nw.y_), 6),
            "abandons_parmi_plus_proches": int(sum(l["abandon"] for l in plus_proches)),
            "colonnes": [_COURTS.get(c, libelle_variable(c)) for c in colonnes],
            "plus_proches": plus_proches,
        }

    # ------------------------------------------------------------------ saisie individuelle
    def scorer_un(self, reponses: dict) -> dict:
        """Score un etudiant saisi au formulaire, avec ses explications."""
        message = verifier_coherence(reponses)
        if message:
            raise ValueError(message)
        return self.expliquer(reponses)

    def expliquer(self, reponses: dict) -> dict:
        """Score un etudiant (saisi ou deja enregistre) et explique les deux estimations."""
        valeurs, erreurs = self.nettoyer(pd.DataFrame([reponses]))
        if erreurs:
            raise ValueError("Données invalides : " + next(iter(erreurs.values())))
        moment = self.moments(valeurs).iloc[0]
        completees, masque = self._completer(valeurs, moment)
        p_noyau, p_ml, X = self._probabilites(completees, moment)
        p_noyau, p_ml = round(float(p_noyau[0]), 3), round(float(p_ml[0]), 3)
        estimees = set(masque.columns[masque.iloc[0].to_numpy()])

        contributions = self.contributions(X, moment)
        ordre = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
        ligne = X.iloc[0]
        facteurs = []
        for nom, contribution in ordre:
            brute = ligne[nom]
            if nom.startswith("taux_validation"):
                affichee = "-" if pd.isna(brute) else f"{round(100 * float(brute))} %"
            elif pd.isna(brute):
                affichee = "aucune unité validée" if nom.endswith("(grade)") and nom not in estimees else "-"
            elif nom in CHAMPS_OUI_NON:
                affichee = "Oui" if float(brute) == 1 else "Non"
            elif nom == "Course":
                affichee = FILIERES.get(int(brute), f"code {int(brute)}")
            elif nom in NOMINALES:
                affichee = f"code {int(brute)}"
            else:
                affichee = round(float(brute), 1)
            if nom in estimees and nom not in CATEGORIELLES:
                affichee = round(float(self.defauts[nom]), 1)
            facteurs.append({
                "variable": libelle_variable(nom), "valeur": affichee,
                "sens": "augmente" if contribution > 0 else "diminue",
                "contribution": round(float(contribution), 4),
                "estimee": nom in estimees,
            })
        return {
            "probabilite_noyau": p_noyau, "probabilite_ml": p_ml,
            "categorie_noyau": categorie(p_noyau), "categorie_ml": categorie(p_ml),
            "alerte": p_ml >= round(SEUIL_ALERTE, 3),
            "moment": moment, "libelle_moment": LIBELLES_MOMENTS[moment],
            "facteurs_contributifs": facteurs,
            "nb_variables_estimees": len(estimees),
            "nb_variables_modele": len(variables_du_moment(moment)),
            "voisins_noyau": self.voisins_noyau(X, moment),
        }

    # ------------------------------------------------------------------ indicateurs sur une cohorte
    def metriques(self, y_reel: np.ndarray, p_noyau: np.ndarray, p_ml: np.ndarray) -> dict:
        """ROC-AUC, score de Brier, et, au seuil d'alerte, part des abandons detectes (rappel)
        et part d'alertes justes (precision)."""
        from sklearn.metrics import brier_score_loss, roc_auc_score
        if len(set(y_reel)) < 2:
            return {}
        sortie = {}
        for cle, p in (("noyau", p_noyau), ("ml", p_ml)):
            alerte = p >= SEUIL_ALERTE
            vrais = alerte & (y_reel == 1)
            sortie[cle] = {
                "auc": float(roc_auc_score(y_reel, p)),
                "brier": float(brier_score_loss(y_reel, p)),
                "rappel": float(vrais.sum() / y_reel.sum()),
                "precision": float(vrais.sum() / alerte.sum()) if alerte.any() else 0.0,
            }
        return sortie

    def valeurs_reference(self) -> dict:
        """Evaluation finale pre-enregistree du projet de recherche, sur le meme jeu de test (moment T2)."""
        return {"ml": self.reference["logistique"]["T2"], "noyau": self.reference["noyau"]["T2"]}
