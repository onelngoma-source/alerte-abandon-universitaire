"""Traduction des variables du modele en langage clair, pour un conseiller pedagogique.

Chaque variable recoit :
  - un domaine (Résultats, Finances, Parcours d'entrée, Profil) ;
  - une indication de levier : peut-on agir dessus pendant l'annee (resultats, finances) ou non (profil) ;
  - une phrase longue (fiche) et une phrase courte (liste des etudiants), construites a partir de la valeur.
"""
from __future__ import annotations

import math

from .referentiels import FILIERES

DOMAINES = {"resultats": "Résultats", "finances": "Finances", "parcours": "Parcours d'entrée", "profil": "Profil"}
LEVIERS = {"resultats", "finances"}

SEMESTRES = {"1st": ("1er semestre", "S1"), "2nd": ("2e semestre", "S2")}

MODES_CANDIDATURE = {
    1: "1re phase, contingent général", 17: "2e phase, contingent général", 18: "3e phase, contingent général",
    39: "candidature des plus de 23 ans", 43: "changement de filière", 42: "transfert",
    51: "changement d'établissement et de filière", 44: "titulaire d'un diplôme de spécialisation technologique",
    53: "titulaire d'un diplôme de cycle court", 7: "titulaire d'un autre diplôme supérieur",
    15: "étudiant international",
}
QUALIFICATIONS = {
    1: "enseignement secondaire", 2: "licence", 3: "diplôme supérieur", 4: "master", 5: "doctorat",
    6: "études supérieures non terminées", 9: "12e année non terminée", 10: "11e année non terminée",
    12: "autre, 11e année", 14: "10e année", 15: "10e année non terminée", 19: "enseignement de base",
    38: "enseignement de base", 39: "spécialisation technologique", 40: "licence (1er cycle)",
    42: "cours technique supérieur professionnel", 43: "master (2e cycle)",
}
ETATS_CIVILS = {1: "célibataire", 2: "marié(e)", 3: "veuf ou veuve", 4: "divorcé(e)", 5: "union de fait", 6: "séparé(e)"}


def _vide(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _entier(v) -> int:
    return int(round(float(v)))


def _nombre(v, decimales=1) -> str:
    v = round(float(v), decimales)
    return (f"{v:.{decimales}f}".rstrip("0").rstrip(".") if decimales else str(int(v))).replace(".", ",")


def domaine(variable: str) -> str:
    if variable.startswith(("Curricular units", "taux_validation")):
        return "resultats"
    if variable in ("Debtor", "Tuition fees up to date", "Scholarship holder"):
        return "finances"
    if variable in ("Course", "Application mode", "Application order", "Previous qualification",
                    "Previous qualification (grade)", "Admission grade", "Daytime/evening attendance"):
        return "parcours"
    return "profil"


def _semestre(variable: str) -> tuple[str, str, str]:
    s = "1st" if "1st" in variable else "2nd"
    return (s, *SEMESTRES[s])


def phrase(variable: str, ligne: dict, court: bool = False) -> str:
    """Phrase decrivant la valeur d'une variable pour un etudiant.

    `ligne` contient les valeurs connues du modele (dont les unites inscrites et validees,
    pour exprimer un taux de validation en « 3 sur 6 »)."""
    v = ligne.get(variable)

    if variable.startswith("taux_validation"):
        s = "1st" if variable.endswith("1st") else "2nd"
        long, abr = SEMESTRES[s]
        inscrites = ligne.get(f"Curricular units {s} sem (enrolled)")
        validees = ligne.get(f"Curricular units {s} sem (approved)")
        if _vide(inscrites) or _vide(validees):
            return f"Taux de validation non renseigné ({abr})" if court else f"Taux de validation du {long} non renseigné"
        if _entier(inscrites) == 0:
            return f"Aucune unité inscrite ({abr})" if court else f"Aucune unité inscrite au {long}"
        pct = round(100 * float(validees) / float(inscrites))
        if court:
            return f"{_entier(validees)}/{_entier(inscrites)} unités validées ({abr})"
        return f"{_entier(validees)} unités validées sur {_entier(inscrites)} au {long} ({pct} %)"

    if variable.startswith("Curricular units"):
        s, long, abr = _semestre(variable)
        quoi = variable.split("(")[-1].rstrip(")")
        if quoi == "grade" and _vide(v):
            validees = ligne.get(f"Curricular units {s} sem (approved)")
            if not _vide(validees) and _entier(validees) == 0:
                return f"Aucune unité validée ({abr})" if court else f"Aucune unité validée au {long}, donc pas de moyenne"
        if _vide(v):
            return f"Information du {long} non renseignée"
        n = _entier(v)
        textes = {
            "enrolled": (f"{n} unités inscrites ({abr})", f"{n} unités inscrites au {long}"),
            "approved": (f"{n} unités validées ({abr})", f"{n} unités validées au {long}"),
            "evaluations": (f"{n} évaluations passées ({abr})", f"{n} évaluations passées au {long}"),
            "grade": (f"Moyenne {_nombre(v)}/20 ({abr})", f"Moyenne de {_nombre(v)}/20 au {long}"),
            "credited": (f"{n} unités créditées ({abr})", f"{n} unités créditées par équivalence au {long}"),
            "without evaluations": (f"{n} unités sans évaluation ({abr})", f"{n} unités sans évaluation au {long}"),
        }
        return textes[quoi][0 if court else 1]

    if _vide(v):
        from .referentiels import LIBELLES_CHAMPS
        return f"{LIBELLES_CHAMPS.get(variable, variable)} : non renseigné"

    oui = float(v) >= 0.5
    if variable == "Debtor":
        return ("Débiteur" if court else "Débiteur envers l'établissement") if oui else \
            ("Pas de dette" if court else "Aucune dette envers l'établissement")
    if variable == "Tuition fees up to date":
        return ("Frais à jour" if court else "Frais de scolarité à jour") if oui else \
            ("Frais en retard" if court else "Frais de scolarité en retard")
    if variable == "Scholarship holder":
        return "Boursier" if oui else "Non boursier"
    if variable == "Gender":
        return "Homme" if oui else "Femme"
    if variable == "Daytime/evening attendance":
        return "Cours du jour" if oui else "Cours du soir"
    if variable == "Displaced":
        return ("Déplacé" if court else "Étudiant déplacé, hors de sa région d'origine") if oui else \
            ("Non déplacé" if court else "Étudiant dans sa région d'origine")
    if variable == "International":
        return "Étudiant international" if oui else "Étudiant national"
    if variable == "Educational special needs":
        return "Besoins éducatifs particuliers" if oui else "Pas de besoin éducatif particulier"
    if variable == "Age at enrollment":
        return f"{_entier(v)} ans à l'inscription"
    if variable == "Course":
        nom = FILIERES.get(_entier(v), f"code {_entier(v)}")
        return nom if court else f"Filière : {nom}"
    if variable == "Admission grade":
        return f"Note d'admission {_nombre(v)}/200" if court else f"Note d'admission de {_nombre(v)} sur 200"
    if variable == "Previous qualification (grade)":
        return f"Diplôme précédent {_nombre(v)}/200" if court else f"Note du diplôme précédent : {_nombre(v)} sur 200"
    if variable == "Application order":
        rang = max(1, _entier(v))  # 1 = premier choix dans les donnees (une seule valeur 0)
        return f"Filière demandée en {'1er' if rang == 1 else f'{rang}e'} choix"
    if variable == "Application mode":
        texte = MODES_CANDIDATURE.get(_entier(v), f"code {_entier(v)}")
        return f"Candidature : {texte}"
    if variable == "Previous qualification":
        texte = QUALIFICATIONS.get(_entier(v), f"code {_entier(v)}")
        return f"Diplôme précédent : {texte}"
    if variable == "Marital status":
        return f"Situation familiale : {ETATS_CIVILS.get(_entier(v), f'code {_entier(v)}')}"
    familles = {"Mother's qualification": "Diplôme de la mère", "Father's qualification": "Diplôme du père",
                "Mother's occupation": "Profession de la mère", "Father's occupation": "Profession du père"}
    if variable in familles:
        return f"{familles[variable]} (code {_entier(v)})"
    return f"{variable} : {_nombre(v)}"


def intensite(contribution: float) -> str:
    """Poids d'un facteur, a partir de sa contribution au logit (exp(c) multiplie la cote d'abandon)."""
    a = abs(contribution)
    return "fort" if a >= 0.6 else "modéré" if a >= 0.25 else "léger"
