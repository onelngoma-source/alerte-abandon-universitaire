"""Acces a la base SQLite (module standard sqlite3, sans ORM).

Modele logique : COHORTE 1-n ETUDIANT 1-2 SCORE (un score par modele : noyau et logistique).
Une cohorte est soit le jeu de test (cohortes 2015 a 2017, 1 227 etudiants), soit un fichier CSV importe.
"""
import os
import sqlite3
from pathlib import Path

RACINE = Path(__file__).resolve().parent
FICHIER_JEU_DE_TEST = "jeu_de_test_2015_2017.csv"  # cohortes 2015 a 2017, jamais vues a l'entrainement

SCHEMA = """
CREATE TABLE IF NOT EXISTS cohorte (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nom           TEXT    NOT NULL,
    origine       TEXT    NOT NULL CHECK (origine IN ('test_uci', 'import')),
    fichier       TEXT,
    effectif      INTEGER NOT NULL,
    ignorees      INTEGER NOT NULL DEFAULT 0,
    proprietaire  TEXT,                       -- NULL = cohorte partagee, visible de tous
    date_creation TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS etudiant (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cohorte_id    INTEGER NOT NULL REFERENCES cohorte(id) ON DELETE CASCADE,
    reference     TEXT    NOT NULL,
    filiere       TEXT,
    genre         TEXT,
    age           REAL,
    boursier      INTEGER,
    debiteur      INTEGER,
    frais_a_jour  INTEGER,
    note_s1       REAL,
    note_s2       REAL,
    inscrites_s1  INTEGER,
    validees_s1   INTEGER,
    inscrites_s2  INTEGER,
    validees_s2   INTEGER,
    facteur       TEXT,                       -- facteur qui pese le plus vers l'abandon, en clair
    domaine_facteur TEXT,
    devenir_reel  TEXT CHECK (devenir_reel IN ('Dropout', 'Graduate', 'Enrolled')),
    abandon_reel  INTEGER CHECK (abandon_reel IN (0, 1)),
    caracteristiques TEXT           -- JSON : valeurs des variables fournies (sert a la fiche d'explication)
);
CREATE INDEX IF NOT EXISTS idx_etudiant_cohorte ON etudiant(cohorte_id);
CREATE TABLE IF NOT EXISTS score (
    etudiant_id   INTEGER NOT NULL REFERENCES etudiant(id) ON DELETE CASCADE,
    modele        TEXT    NOT NULL CHECK (modele IN ('noyau', 'logistique')),
    probabilite   REAL    NOT NULL,
    categorie     TEXT    NOT NULL CHECK (categorie IN ('faible', 'moyen', 'eleve')),
    mode_calcul   TEXT    NOT NULL CHECK (mode_calcul IN ('T0', 'T1', 'T2')),
    PRIMARY KEY (etudiant_id, modele)
);
"""

REQUETE_LIGNES = """
SELECT e.id, e.reference, e.filiere, e.genre, e.age, e.boursier, e.debiteur, e.frais_a_jour,
       e.note_s1, e.note_s2, e.inscrites_s1, e.validees_s1, e.inscrites_s2, e.validees_s2,
       e.facteur, e.domaine_facteur, e.devenir_reel, e.abandon_reel,
       MAX(CASE WHEN s.modele = 'noyau' THEN s.probabilite END) AS p_noyau,
       MAX(CASE WHEN s.modele = 'noyau' THEN s.categorie   END) AS c_noyau,
       MAX(CASE WHEN s.modele = 'logistique' THEN s.probabilite END) AS p_ml,
       MAX(CASE WHEN s.modele = 'logistique' THEN s.categorie   END) AS c_ml,
       MAX(s.mode_calcul) AS mode
FROM etudiant e JOIN score s ON s.etudiant_id = e.id
WHERE e.cohorte_id = ?
GROUP BY e.id
ORDER BY e.id
"""


def chemin_base() -> Path:
    return Path(os.environ.get("DB_PATH", RACINE / "instance" / "alerte.db"))


def connecter() -> sqlite3.Connection:
    chemin = chemin_base()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    connexion = sqlite3.connect(chemin, timeout=15)
    connexion.row_factory = sqlite3.Row
    connexion.execute("PRAGMA foreign_keys = ON")
    # WAL : les lectures ne bloquent plus pendant une ecriture. Indispensable des que
    # plusieurs personnes consultent l'application en meme temps.
    connexion.execute("PRAGMA journal_mode = WAL")
    connexion.execute("PRAGMA busy_timeout = 15000")
    return connexion


def initialiser() -> None:
    with connecter() as c:
        # Base creee par la version du memoire (modeles noyau / rf, modes complet / precoce) :
        # ses scores ne correspondent plus aux modeles actuels. Elle ne contient que des donnees
        # recalculables (jeu de test et imports) : on la reconstruit.
        ancien = c.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'score'").fetchone()
        colonnes_avant = {r["name"] for r in c.execute("PRAGMA table_info(etudiant)")}
        if (ancien and "'rf'" in ancien["sql"]) or (colonnes_avant and "facteur" not in colonnes_avant):
            # base d'une version precedente : tout y est recalculable (jeu de test et imports)
            c.executescript("DROP TABLE score; DROP TABLE etudiant; DROP TABLE cohorte;")
        c.executescript(SCHEMA)
        colonnes = {r["name"] for r in c.execute("PRAGMA table_info(etudiant)")}
        if "caracteristiques" not in colonnes:  # base creee par une version precedente
            c.execute("ALTER TABLE etudiant ADD COLUMN caracteristiques TEXT")
        colonnes_cohorte = {r["name"] for r in c.execute("PRAGMA table_info(cohorte)")}
        if "proprietaire" not in colonnes_cohorte:
            c.execute("ALTER TABLE cohorte ADD COLUMN proprietaire TEXT")


def lister_cohortes(proprietaire: str | None = None) -> list[dict]:
    """Les cohortes visibles. Avec un proprietaire, on ne rend que les cohortes partagees
    (proprietaire NULL) et celles de ce visiteur : deux personnes qui importent chacune
    leur fichier ne se voient pas mutuellement."""
    with connecter() as c:
        if proprietaire is None:
            return [dict(r) for r in c.execute(
                "SELECT id, nom, origine, fichier, effectif, ignorees, date_creation FROM cohorte ORDER BY id")]
        return [dict(r) for r in c.execute(
            "SELECT id, nom, origine, fichier, effectif, ignorees, date_creation FROM cohorte "
            "WHERE proprietaire IS NULL OR proprietaire = ? ORDER BY id", (proprietaire,))]


def lire_cohorte(cohorte_id: int, proprietaire: str | None = None) -> dict | None:
    with connecter() as c:
        if proprietaire is None:
            r = c.execute("SELECT id, nom, origine, fichier, effectif, ignorees, date_creation FROM cohorte WHERE id = ?",
                          (cohorte_id,)).fetchone()
        else:
            r = c.execute(
                "SELECT id, nom, origine, fichier, effectif, ignorees, date_creation FROM cohorte "
                "WHERE id = ? AND (proprietaire IS NULL OR proprietaire = ?)",
                (cohorte_id, proprietaire)).fetchone()
        return dict(r) if r else None


def lire_lignes(cohorte_id: int) -> list[dict]:
    with connecter() as c:
        return [dict(r) for r in c.execute(REQUETE_LIGNES, (cohorte_id,))]


def creer_cohorte(nom: str, origine: str, fichier: str | None, etudiants: list[dict], ignorees: int = 0,
                  proprietaire: str | None = None) -> int:
    """Enregistre une cohorte, ses etudiants et leurs deux scores, en une seule transaction."""
    with connecter() as c:
        cur = c.execute(
            "INSERT INTO cohorte (nom, origine, fichier, effectif, ignorees, proprietaire) VALUES (?, ?, ?, ?, ?, ?)",
            (nom, origine, fichier, len(etudiants), ignorees, proprietaire))
        cohorte_id = cur.lastrowid
        for e in etudiants:
            cur = c.execute(
                "INSERT INTO etudiant (cohorte_id, reference, filiere, genre, age, boursier, debiteur, frais_a_jour, "
                "note_s1, note_s2, inscrites_s1, validees_s1, inscrites_s2, validees_s2, facteur, domaine_facteur, "
                "devenir_reel, abandon_reel, caracteristiques) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cohorte_id, e["reference"], e["filiere"], e["genre"], e["age"], e["boursier"], e["debiteur"],
                 e["frais_a_jour"], e["note_s1"], e["note_s2"], e.get("inscrites_s1"), e.get("validees_s1"),
                 e.get("inscrites_s2"), e.get("validees_s2"), e.get("facteur"), e.get("domaine_facteur"),
                 e["devenir_reel"], e["abandon_reel"], e.get("caracteristiques")))
            etudiant_id = cur.lastrowid
            c.executemany(
                "INSERT INTO score (etudiant_id, modele, probabilite, categorie, mode_calcul) VALUES (?, ?, ?, ?, ?)",
                [(etudiant_id, "noyau", e["p_noyau"], e["c_noyau"], e["mode"]),
                 (etudiant_id, "logistique", e["p_ml"], e["c_ml"], e["mode"])])
        return cohorte_id


def lire_etudiant(etudiant_id: int) -> dict | None:
    """Un etudiant avec ses deux scores et les valeurs enregistrees."""
    with connecter() as c:
        r = c.execute(
            "SELECT e.id, e.cohorte_id, e.reference, e.devenir_reel, e.abandon_reel, e.caracteristiques, "
            "MAX(CASE WHEN s.modele = 'noyau' THEN s.probabilite END) AS p_noyau, "
            "MAX(CASE WHEN s.modele = 'logistique' THEN s.probabilite END) AS p_ml, MAX(s.mode_calcul) AS mode "
            "FROM etudiant e JOIN score s ON s.etudiant_id = e.id WHERE e.id = ? GROUP BY e.id", (etudiant_id,)).fetchone()
        return dict(r) if r else None


def supprimer_cohorte(cohorte_id: int, proprietaire: str | None = None) -> int:
    """Rend le nombre de cohortes effacees. Avec un proprietaire, une cohorte partagee
    (proprietaire NULL) ou appartenant a quelqu'un d'autre n'est jamais touchee."""
    with connecter() as c:
        if proprietaire is None:
            cur = c.execute("DELETE FROM cohorte WHERE id = ?", (cohorte_id,))
        else:
            cur = c.execute("DELETE FROM cohorte WHERE id = ? AND proprietaire = ?",
                            (cohorte_id, proprietaire))
        return cur.rowcount


def vider(proprietaire: str | None = None) -> None:
    with connecter() as c:
        if proprietaire is None:
            c.execute("DELETE FROM cohorte")
            c.execute("DELETE FROM sqlite_sequence")
        else:
            c.execute("DELETE FROM cohorte WHERE proprietaire = ?", (proprietaire,))
