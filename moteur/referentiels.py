"""Referentiels partages : libelles francais, filieres, champs du formulaire, seuils de risque.

Les cles restent en anglais car ce sont les noms de colonnes du jeu de donnees UCI
(Realinho et al., 2021) sur lequel les modeles ont ete entraines.
"""

# Seuils de categorisation du risque (Chapitre IV) : faible < 0,30 <= moyen < 0,60 <= eleve
SEUIL_MOYEN = 0.30
SEUIL_ELEVE = 0.60

NIVEAUX = {"faible": "Faible", "moyen": "Moyen", "eleve": "Élevé"}

FILIERES = {
    33: "Technologies de production de biocarburants", 171: "Design d'animation et multimédia",
    8014: "Service social (soir)", 9003: "Agronomie", 9070: "Design de communication",
    9085: "Soins vétérinaires", 9119: "Génie informatique", 9130: "Équinculture",
    9147: "Gestion", 9238: "Service social", 9254: "Tourisme", 9500: "Soins infirmiers",
    9556: "Hygiène dentaire", 9670: "Publicité et marketing", 9773: "Journalisme et communication",
    9853: "Éducation de base", 9991: "Gestion (soir)",
}

def sans_accents(texte: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(texte)) if unicodedata.category(c) != "Mn").lower().strip()


_CODES_PAR_LIBELLE = {sans_accents(nom): code for code, nom in FILIERES.items()}


def code_filiere(texte) -> int | None:
    """Code UCI d'une filiere a partir de son libelle (sans tenir compte des accents ni de la casse)."""
    return _CODES_PAR_LIBELLE.get(sans_accents(texte))


# Champs exposes dans le formulaire individuel (facteurs les plus determinants, Objectif 1)
CHAMPS_FORMULAIRE = [
    "Curricular units 1st sem (enrolled)",
    "Curricular units 1st sem (approved)",
    "Curricular units 1st sem (evaluations)",
    "Curricular units 2nd sem (enrolled)",
    "Curricular units 2nd sem (approved)",
    "Curricular units 2nd sem (evaluations)",
    "Curricular units 1st sem (grade)",
    "Curricular units 2nd sem (grade)",
    "Tuition fees up to date",
    "Scholarship holder",
    "Debtor",
    "Age at enrollment",
    "Course",
]
# Sous-ensemble independant du 2e semestre (mode precoce)
CHAMPS_FORMULAIRE_PRECOCE = [c for c in CHAMPS_FORMULAIRE if "2nd sem" not in c]
CHAMPS_2E_SEMESTRE = [c for c in CHAMPS_FORMULAIRE if "2nd sem" in c]
CHAMPS_OUI_NON = ["Tuition fees up to date", "Scholarship holder", "Debtor"]

LIBELLES_CHAMPS = {
    "Marital status": "État civil",
    "Application mode": "Mode de candidature",
    "Application order": "Ordre de candidature",
    "Course": "Filière",
    "Daytime/evening attendance": "Cours du jour ou du soir",
    "Previous qualification": "Qualification précédente",
    "Previous qualification (grade)": "Note de la qualification précédente",
    "Nacionality": "Nationalité",
    "Mother's qualification": "Qualification de la mère",
    "Father's qualification": "Qualification du père",
    "Mother's occupation": "Profession de la mère",
    "Father's occupation": "Profession du père",
    "Admission grade": "Note d'admission",
    "Displaced": "Déplacé",
    "Educational special needs": "Besoins éducatifs spécifiques",
    "Debtor": "Débiteur",
    "Tuition fees up to date": "Frais de scolarité à jour",
    "Gender": "Genre",
    "Scholarship holder": "Boursier",
    "Age at enrollment": "Âge à l'inscription",
    "International": "Étudiant international",
    "Curricular units 1st sem (credited)": "Unités créditées, 1er semestre",
    "Curricular units 1st sem (enrolled)": "Unités inscrites, 1er semestre",
    "Curricular units 1st sem (evaluations)": "Évaluations passées, 1er semestre",
    "Curricular units 1st sem (approved)": "Unités validées, 1er semestre",
    "Curricular units 1st sem (grade)": "Moyenne, 1er semestre (/20)",
    "Curricular units 1st sem (without evaluations)": "Unités sans évaluation, 1er semestre",
    "Curricular units 2nd sem (credited)": "Unités créditées, 2e semestre",
    "Curricular units 2nd sem (enrolled)": "Unités inscrites, 2e semestre",
    "Curricular units 2nd sem (evaluations)": "Évaluations passées, 2e semestre",
    "Curricular units 2nd sem (approved)": "Unités validées, 2e semestre",
    "Curricular units 2nd sem (grade)": "Moyenne, 2e semestre (/20)",
    "Curricular units 2nd sem (without evaluations)": "Unités sans évaluation, 2e semestre",
    "Unemployment rate": "Taux de chômage",
    "Inflation rate": "Taux d'inflation",
    "GDP": "PIB",
}

# Devenir reel (colonne Target du jeu de donnees UCI)
DEVENIRS = {"Dropout": "Abandon", "Graduate": "Diplômé", "Enrolled": "Inscrit"}
