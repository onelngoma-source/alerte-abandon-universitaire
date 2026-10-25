"""Recommandations d'accompagnement fondees sur le profil saisi (Objectif 3, Chapitre IV)."""
from .scoring import vers_nombre


def generer_conseils(reponses: dict) -> list[dict]:
    def nombre(cle, defaut):
        try:
            valeur = vers_nombre(reponses.get(cle))
        except ValueError:
            valeur = None
        return defaut if valeur is None else valeur

    note_s1 = nombre("Curricular units 1st sem (grade)", 20)
    note_s2 = nombre("Curricular units 2nd sem (grade)", 20)
    validees_s1 = nombre("Curricular units 1st sem (approved)", 10)
    validees_s2 = nombre("Curricular units 2nd sem (approved)", 10)
    inscrites_s1 = nombre("Curricular units 1st sem (enrolled)", validees_s1 or 1)
    inscrites_s2 = nombre("Curricular units 2nd sem (enrolled)", validees_s2 or 1)
    debiteur = nombre("Debtor", 0) == 1
    boursier = nombre("Scholarship holder", 0) == 1
    frais_a_jour = nombre("Tuition fees up to date", 1) == 1
    age = nombre("Age at enrollment", 18)

    conseils = []
    if note_s1 < 10 or note_s2 < 10:
        conseils.append({"type": "academique", "message":
            "Résultats académiques fragiles (moyenne inférieure à 10/20) : orienter vers un dispositif de tutorat ou de soutien pédagogique."})
    if validees_s1 < 4 or validees_s2 < 4:
        conseils.append({"type": "academique", "message":
            "Peu d'unités curriculaires validées : vérifier la charge de cours et envisager un aménagement du parcours."})
    for libelle, inscrites, validees in (("1er", inscrites_s1, validees_s1), ("2e", inscrites_s2, validees_s2)):
        if inscrites > 0 and validees / inscrites < 0.5:
            conseils.append({"type": "academique", "message":
                f"Taux de réussite au {libelle} semestre inférieur à 50 % ({int(validees)}/{int(inscrites)} unités) : "
                "signal plus fort qu'un simple nombre bas, même avec une charge de cours normale."})
    if debiteur:
        conseils.append({"type": "financier", "message":
            "Situation de débiteur : orienter vers le service financier pour un plan d'apurement "
            "(facteur associé à 62 % d'abandon dans les données observées)."})
    if not boursier and not frais_a_jour:
        conseils.append({"type": "financier", "message":
            "Pas de bourse et retard de paiement des frais : évaluer l'éligibilité à une aide financière d'urgence."})
    if age >= 23:
        conseils.append({"type": "social", "message":
            "Profil d'étudiant non traditionnel (Bean et Metzner, 1985) : vérifier la compatibilité entre emploi ou charges familiales et charge d'études."})
    if not conseils:
        conseils.append({"type": "aucun", "message":
            "Aucun facteur de risque majeur identifié parmi les indicateurs suivis : poursuivre le suivi standard."})
    return conseils
