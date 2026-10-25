"""Fonction noyau partagee entre l'entrainement et l'application Flask."""
import numpy as np

# Largeur de bande modifiable au moment de l'appel (voir predire() dans volets/saisie.py) :
# on l'elargit progressivement si un profil est trop atypique, plutot que d'abandonner
# directement l'approche a noyau pour un autre modele.
LARGEUR_BANDE_ACTIVE = 1.0


def noyau_gaussien(distances):
    return np.exp(-(distances ** 2) / (2 * LARGEUR_BANDE_ACTIVE ** 2))
