"""Pistes d'accompagnement, tirees des leviers sur lesquels l'etablissement peut agir.

Elles partent des valeurs reellement fournies (une valeur absente ne declenche rien) et
sont rangees par domaine : resultats, finances, situation personnelle. Ce sont des pistes
pour le conseiller, pas des decisions du modele.
"""
from .scoring import vers_nombre


def generer_conseils(reponses: dict) -> list[dict]:
    def nombre(cle):
        try:
            return vers_nombre(reponses.get(cle))
        except ValueError:
            return None

    conseils = []

    def ajouter(type_, titre, message):
        conseils.append({"type": type_, "titre": titre, "message": message})

    for s, libelle in (("1st", "1er"), ("2nd", "2e")):
        inscrites = nombre(f"Curricular units {s} sem (enrolled)")
        validees = nombre(f"Curricular units {s} sem (approved)")
        note = nombre(f"Curricular units {s} sem (grade)")
        evaluations = nombre(f"Curricular units {s} sem (evaluations)")
        if inscrites and validees is not None and validees / inscrites < 0.5:
            ajouter("academique", f"Rattrapage du {libelle} semestre",
                    f"{int(validees)} unité(s) validée(s) sur {int(inscrites)} au {libelle} semestre : "
                    "faire le point sur les unités à repasser, proposer un tutorat et, si besoin, alléger la charge de cours.")
        elif note is not None and 0 < note < 10:
            ajouter("academique", f"Soutien pédagogique ({libelle} semestre)",
                    f"Moyenne de {note:.1f}/20 au {libelle} semestre : orienter vers un tutorat ou un groupe de travail.".replace(".", ",", 1))
        if inscrites and evaluations is not None and evaluations < inscrites:
            ajouter("academique", f"Assiduité aux évaluations ({libelle} semestre)",
                    f"{int(evaluations)} évaluation(s) passée(s) pour {int(inscrites)} unités inscrites : "
                    "vérifier les absences aux examens et leurs raisons.")

    debiteur = nombre("Debtor") == 1
    frais_a_jour = nombre("Tuition fees up to date")
    boursier = nombre("Scholarship holder") == 1
    if debiteur:
        ajouter("financier", "Plan d'apurement",
                "Étudiant débiteur : orienter vers le service financier pour un plan d'apurement "
                "(71 % d'abandon chez les étudiants débiteurs des cohortes 2008 à 2014).")
    if frais_a_jour == 0:
        ajouter("financier", "Aide financière",
                "Frais de scolarité en retard de paiement : vérifier l'éligibilité à une aide d'urgence ou à un échelonnement"
                + (" et à une bourse." if not boursier else "."))

    age = nombre("Age at enrollment")
    if age is not None and age >= 23:
        ajouter("social", "Conciliation études et vie personnelle",
                "Étudiant de 23 ans ou plus à l'inscription : vérifier la compatibilité entre un emploi ou des charges "
                "familiales et la charge d'études (aménagement d'emploi du temps, cours du soir).")

    if not conseils:
        ajouter("aucun", "Suivi habituel",
                "Aucun signal particulier parmi les résultats, les finances et la situation renseignés : suivi habituel.")
    return conseils
