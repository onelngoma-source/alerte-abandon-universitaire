"""Estimateur de Nadaraya-Watson (noyau gaussien, tous les points d'entraînement).

Même calcul que src/abandon_universitaire/noyau.py du projet de recherche, avec en plus
la méthode `poids`, qui sert à expliquer une estimation par les étudiants qui la fixent.
"""

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin


class NadarayaWatson(ClassifierMixin, BaseEstimator):
    """P(abandon | x) = somme des K(x, xi) * yi / somme des K(x, xi), avec K gaussien de largeur `bande`."""

    def __init__(self, bande: float = 1.0):
        self.bande = bande

    def fit(self, X, y):
        y = np.asarray(y)
        self.classes_ = np.unique(y)
        self.X_ = np.asarray(X, dtype=float)
        self.y_ = (y == self.classes_[-1]).astype(float)
        self.carres_ = (self.X_ ** 2).sum(axis=1)
        return self

    def poids(self, X):
        """Poids normalisés (somme 1) de chaque étudiant d'apprentissage, pour chaque ligne de X."""
        X = np.asarray(X, dtype=float)
        d2 = (X ** 2).sum(axis=1)[:, None] + self.carres_[None, :] - 2 * X @ self.X_.T
        log_poids = -np.maximum(d2, 0) / (2 * self.bande ** 2)
        log_poids -= log_poids.max(axis=1, keepdims=True)  # stabilité numérique : jamais 0/0
        poids = np.exp(log_poids)
        return poids / poids.sum(axis=1, keepdims=True), np.sqrt(np.maximum(d2, 0))

    def predict_proba(self, X):
        X = np.asarray(X, dtype=float)
        p = np.empty(len(X))
        for i in range(0, len(X), 512):
            bloc = X[i:i + 512]
            d2 = (bloc ** 2).sum(axis=1)[:, None] + self.carres_[None, :] - 2 * bloc @ self.X_.T
            log_poids = -np.maximum(d2, 0) / (2 * self.bande ** 2)
            log_poids -= log_poids.max(axis=1, keepdims=True)  # stabilité numérique : jamais 0/0
            poids = np.exp(log_poids)
            p[i:i + 512] = np.clip(poids @ self.y_ / poids.sum(axis=1), 0.0, 1.0)  # arrondis flottants
        return np.column_stack([1 - p, p])

    def predict(self, X):
        return self.classes_[(self.predict_proba(X)[:, 1] >= 0.5).astype(int)]
