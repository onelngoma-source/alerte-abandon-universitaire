"""Parametres du suivi apres alerte. Tous sont modifiables par variable d'environnement, sans toucher au code."""
import os

from moteur.referentiels import SEUIL_ALERTE, SEUIL_ELEVE  # noqa: F401  (reexportes pour les volets)

ROLES = {"conseiller": "Conseiller", "responsable": "Responsable", "admin": "Administrateur"}

STATUTS = {
    "a_contacter": "À contacter",
    "contacte": "Contacté",
    "entretien": "Entretien réalisé",
    "accompagnement": "En accompagnement",
    "clos": "Clos",
}
STATUTS_OUVERTS = ["a_contacter", "contacte", "entretien", "accompagnement"]

TYPES_ACTION = {
    "note": "Note",
    "appel": "Appel ou message",
    "entretien": "Entretien",
    "tutorat": "Orientation vers un tutorat",
    "financier": "Orientation vers le service financier",
    "social": "Orientation vers le service social ou de santé",
    "amenagement": "Aménagement du parcours",
    "reorientation": "Conseil de réorientation",
}
TYPES_AUTOMATIQUES = {
    "ouverture": "Ouverture du dossier",
    "statut": "Changement de statut",
    "attribution": "Attribution",
    "echeance": "Échéance modifiée",
    "reevaluation": "Nouvelle estimation du risque",
    "cloture": "Clôture",
}

MOTIFS_CLOTURE = {
    "accompagnement_termine": "Accompagnement terminé, situation stabilisée",
    "risque_ecarte": "Risque écarté après entretien",
    "refus": "Accompagnement refusé par l'étudiant",
    "injoignable": "Étudiant injoignable",
    "reorientation": "Réorientation",
    "abandon": "Abandon des études",
    "autre": "Autre motif",
}


def _jours(nom, defaut):
    try:
        return max(1, int(os.environ.get(nom, defaut)))
    except ValueError:
        return defaut


# delai pour passer a l'etape suivante : l'echeance du dossier est fixee automatiquement a chaque changement de statut
DELAIS = {
    "a_contacter": _jours("DELAI_PREMIER_CONTACT_JOURS", 7),
    "contacte": _jours("DELAI_ENTRETIEN_JOURS", 14),
    "entretien": _jours("DELAI_POINT_SUIVI_JOURS", 30),
    "accompagnement": _jours("DELAI_POINT_SUIVI_JOURS", 30),
}
# une hausse du risque d'au moins 10 points sur un dossier ouvert le signale comme « à revoir »
SEUIL_RELANCE = 0.10
DUREE_CONSERVATION_ANNEES = _jours("DUREE_CONSERVATION_ANNEES", 3)
