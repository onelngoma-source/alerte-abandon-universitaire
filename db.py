"""Base de donnees de l'outil d'alerte (SQLAlchemy Core) : SQLite par defaut, PostgreSQL en production.

Modele logique :
  UTILISATEUR (conseiller, responsable, administrateur)
  PROMOTION 1-n ETUDIANT 1-n EVALUATION        un etudiant garde l'historique de ses estimations
  PROMOTION 1-n LOT (import d'un fichier)      chaque import cree une evaluation par etudiant du fichier
  ETUDIANT 1-n DOSSIER 1-n ACTION              suivi apres alerte : statut, conseiller, echeance, journal
  JOURNAL                                      qui a fait quoi, quand (consultations, modifications, exports)
  PARAMETRE                                    reglages durables (cle de session si aucune n'est fournie, derniere sauvegarde)
  ECHEC_CONNEXION                              tentatives manquees, communes a tous les processus du serveur
  JETON_SERVICE                                acces du systeme de scolarite pour les imports automatiques

Le schema evolue par migrations (dossier migrations/, Alembic) : la base est mise a jour au demarrage.

Un etudiant est identifie par son matricule A L'INTERIEUR de sa promotion : importer les resultats du
1er semestre d'une promotion met a jour les memes etudiants au lieu d'en creer de nouveaux.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Integer, MetaData, String, Table, Text, UniqueConstraint,
    TypeDecorator, create_engine, event, inspect, text,
)

RACINE = Path(__file__).resolve().parent
FICHIER_JEU_DE_TEST = "jeu_de_test_2015_2017.csv"  # cohortes 2015 a 2017, jamais vues a l'entrainement
# Une base creee avant les migrations (create_all) a exactement ce schema : on la reconnait et on la reprend.
REVISION_DE_REFERENCE = "0001_reference"
VERROU_MIGRATION = 724001  # verrou PostgreSQL : un seul processus met la base a jour a la fois

class Horodatage(TypeDecorator):
    """Date et heure toujours en UTC, avec fuseau : SQLite ne garde pas le fuseau, on le restitue a la lecture."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, valeur, dialect):
        if valeur is not None and valeur.tzinfo is None:
            valeur = valeur.replace(tzinfo=timezone.utc)
        return valeur.astimezone(timezone.utc) if valeur is not None else None

    def process_result_value(self, valeur, dialect):
        if valeur is not None and valeur.tzinfo is None:
            valeur = valeur.replace(tzinfo=timezone.utc)
        return valeur


meta = MetaData()

utilisateur = Table(
    "utilisateur", meta,
    Column("id", Integer, primary_key=True),
    Column("identifiant", String(80), nullable=False, unique=True),
    Column("nom", String(160), nullable=False),
    Column("email", String(200)),
    Column("role", String(20), nullable=False),               # conseiller, responsable, admin
    Column("mdp_hache", String(255), nullable=False),
    Column("actif", Boolean, nullable=False, default=True),
    Column("doit_changer_mdp", Boolean, nullable=False, default=False),
    Column("cree_le", Horodatage(), nullable=False),
    Column("derniere_connexion", Horodatage()),
    CheckConstraint("role IN ('conseiller', 'responsable', 'admin')", name="ck_utilisateur_role"),
)

promotion = Table(
    "promotion", meta,
    Column("id", Integer, primary_key=True),
    Column("nom", String(200), nullable=False, unique=True),
    Column("origine", String(20), nullable=False),            # demonstration ou etablissement
    Column("cree_le", Horodatage(), nullable=False),
)

lot = Table(
    "lot", meta,
    Column("id", Integer, primary_key=True),
    Column("promotion_id", Integer, ForeignKey("promotion.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("fichier", String(255)),
    Column("effectif", Integer, nullable=False),
    Column("nouveaux", Integer, nullable=False, default=0),
    Column("mis_a_jour", Integer, nullable=False, default=0),
    Column("ignorees", Integer, nullable=False, default=0),
    Column("alertes_ouvertes", Integer, nullable=False, default=0),
    Column("utilisateur_id", Integer, ForeignKey("utilisateur.id", ondelete="SET NULL")),
    Column("cree_le", Horodatage(), nullable=False),
)

etudiant = Table(
    "etudiant", meta,
    Column("id", Integer, primary_key=True),
    Column("promotion_id", Integer, ForeignKey("promotion.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("matricule", String(80), nullable=False),
    Column("nom", String(200)),
    Column("email", String(200)),
    Column("telephone", String(60)),
    Column("filiere", String(200)),
    Column("genre", String(10)),
    Column("age", Float),
    Column("boursier", Integer), Column("debiteur", Integer), Column("frais_a_jour", Integer),
    Column("note_s1", Float), Column("note_s2", Float),
    Column("inscrites_s1", Integer), Column("validees_s1", Integer),
    Column("inscrites_s2", Integer), Column("validees_s2", Integer),
    Column("caracteristiques", Text),                         # JSON : dernieres valeurs connues des 36 variables
    Column("referent_id", Integer, ForeignKey("utilisateur.id", ondelete="SET NULL")),
    # derniere estimation (copie de l'evaluation la plus recente, pour lister vite)
    Column("evaluation_id", Integer),
    Column("probabilite", Float), Column("probabilite_noyau", Float), Column("categorie", String(10)),
    Column("moment", String(2)), Column("facteur", String(255)), Column("domaine_facteur", String(20)),
    # devenir reel, connu en fin d'annee : sert a verifier le modele sur l'etablissement
    Column("devenir_reel", String(10)), Column("abandon_reel", Integer), Column("devenir_saisi_le", Horodatage()),
    Column("cree_le", Horodatage(), nullable=False),
    Column("maj_le", Horodatage(), nullable=False),
    UniqueConstraint("promotion_id", "matricule", name="uq_etudiant_matricule"),
)

evaluation = Table(
    "evaluation", meta,
    Column("id", Integer, primary_key=True),
    Column("etudiant_id", Integer, ForeignKey("etudiant.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("lot_id", Integer, ForeignKey("lot.id", ondelete="SET NULL"), index=True),
    Column("utilisateur_id", Integer, ForeignKey("utilisateur.id", ondelete="SET NULL")),
    Column("moment", String(2), nullable=False),
    Column("probabilite", Float, nullable=False),
    Column("probabilite_noyau", Float, nullable=False),
    Column("categorie", String(10), nullable=False),
    Column("facteur", String(255)), Column("domaine_facteur", String(20)),
    Column("nb_estimees", Integer),
    Column("caracteristiques", Text, nullable=False),
    Column("modele_version", String(60), nullable=False),
    Column("cree_le", Horodatage(), nullable=False),
    CheckConstraint("moment IN ('T0', 'T1', 'T2')", name="ck_evaluation_moment"),
    CheckConstraint("categorie IN ('faible', 'moyen', 'eleve')", name="ck_evaluation_categorie"),
    CheckConstraint("probabilite >= 0 AND probabilite <= 1", name="ck_evaluation_probabilite"),
)

dossier = Table(
    "dossier", meta,
    Column("id", Integer, primary_key=True),
    Column("etudiant_id", Integer, ForeignKey("etudiant.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("statut", String(20), nullable=False, index=True),  # a_contacter, contacte, entretien, accompagnement, clos
    Column("conseiller_id", Integer, ForeignKey("utilisateur.id", ondelete="SET NULL"), index=True),
    Column("echeance", Date),
    Column("ouvert_le", Horodatage(), nullable=False),
    Column("ouvert_par", Integer, ForeignKey("utilisateur.id", ondelete="SET NULL")),  # NULL : ouverture automatique
    Column("evaluation_id", Integer),
    Column("probabilite_ouverture", Float),
    Column("relance", Boolean, nullable=False, default=False),  # le risque a nettement monte depuis l'ouverture
    Column("premier_contact_le", Horodatage()),
    Column("clos_le", Horodatage()),
    Column("motif_cloture", String(40)),
    Column("probabilite_cloture", Float),  # risque au moment de la cloture : un dossier ne se rouvre que s'il monte encore
    Column("maj_le", Horodatage(), nullable=False),
    CheckConstraint("statut IN ('a_contacter', 'contacte', 'entretien', 'accompagnement', 'clos')", name="ck_dossier_statut"),
    CheckConstraint("(statut = 'clos') = (motif_cloture IS NOT NULL)", name="ck_dossier_motif"),
)

action = Table(
    "action", meta,
    Column("id", Integer, primary_key=True),
    Column("dossier_id", Integer, ForeignKey("dossier.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("utilisateur_id", Integer, ForeignKey("utilisateur.id", ondelete="SET NULL")),
    Column("type", String(30), nullable=False),
    Column("texte", Text),
    Column("statut_avant", String(20)), Column("statut_apres", String(20)),
    Column("cree_le", Horodatage(), nullable=False),
)

journal = Table(
    "journal", meta,
    Column("id", Integer, primary_key=True),
    Column("utilisateur_id", Integer, ForeignKey("utilisateur.id", ondelete="SET NULL")),
    Column("identifiant", String(80)),
    Column("action", String(40), nullable=False, index=True),
    Column("objet", String(30)), Column("objet_id", Integer),
    Column("detail", Text),
    Column("adresse", String(60)),
    Column("cree_le", Horodatage(), nullable=False, index=True),
)

parametre = Table(
    "parametre", meta,
    Column("cle", String(60), primary_key=True),
    Column("valeur", Text, nullable=False),
    Column("maj_le", Horodatage(), nullable=False),
)

echec_connexion = Table(
    "echec_connexion", meta,
    Column("id", Integer, primary_key=True),
    Column("adresse", String(60), index=True),
    Column("identifiant", String(80), index=True),
    Column("cree_le", Horodatage(), nullable=False, index=True),
)

jeton_service = Table(
    "jeton_service", meta,
    Column("id", Integer, primary_key=True),
    Column("nom", String(120), nullable=False),
    Column("prefixe", String(12), nullable=False),            # debut du jeton, pour le reconnaitre dans la liste
    Column("empreinte", String(64), nullable=False, unique=True),  # SHA-256 du jeton : le jeton lui-meme n'est jamais stocke
    Column("cree_par", Integer, ForeignKey("utilisateur.id", ondelete="SET NULL")),
    Column("cree_le", Horodatage(), nullable=False),
    Column("derniere_utilisation", Horodatage()),
    Column("revoque_le", Horodatage()),
)

_moteur_bd = None


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def url_base() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # Render et Heroku donnent postgres:// ; SQLAlchemy attend postgresql+psycopg://
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url
    chemin = Path(os.environ.get("DB_PATH", RACINE / "instance" / "alerte.db"))
    chemin.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{chemin}"


def moteur_bd():
    return _moteur_bd


def config_migrations(connexion=None):
    from alembic.config import Config
    cfg = Config()
    cfg.set_main_option("script_location", str(RACINE / "migrations"))
    if connexion is not None:
        cfg.attributes["connexion"] = connexion
    return cfg


def mettre_a_jour_schema(moteur) -> None:
    """Applique les migrations en attente. Une base creee avant les migrations est d'abord reconnue (« stamp »)
    comme etant au schema de reference, sans rien toucher a ses donnees."""
    from alembic import command
    with moteur.begin() as c:
        if c.dialect.name == "postgresql":
            c.execute(text("SELECT pg_advisory_xact_lock(:v)"), {"v": VERROU_MIGRATION})
        tables = set(inspect(c).get_table_names())
        cfg = config_migrations(c)
        if "alembic_version" not in tables and "utilisateur" in tables:
            command.stamp(cfg, REVISION_DE_REFERENCE)
        command.upgrade(cfg, "head")


def revision_schema() -> str | None:
    from alembic.runtime.migration import MigrationContext
    with _moteur_bd.connect() as c:
        return MigrationContext.configure(c).get_current_revision()


def initialiser() -> None:
    """Cree le moteur de base et met le schema a jour (migrations). Une base d'une version tres ancienne
    (sans comptes) est remplacee : elle ne contenait que des donnees recalculables (jeu de test et imports)."""
    global _moteur_bd
    url = url_base()
    if _moteur_bd is not None:
        _moteur_bd.dispose()
    _moteur_bd = create_engine(url, future=True, pool_pre_ping=True)
    if url.startswith("sqlite"):
        @event.listens_for(_moteur_bd, "connect")
        def _pragmas(connexion, _):
            c = connexion.cursor()
            c.execute("PRAGMA foreign_keys = ON")
            c.execute("PRAGMA journal_mode = WAL")
            c.execute("PRAGMA busy_timeout = 15000")
            c.close()
        with _moteur_bd.begin() as c:
            anciennes = {r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
            if "cohorte" in anciennes and "utilisateur" not in anciennes:
                for t in ("score", "etudiant", "cohorte"):
                    c.execute(text(f"DROP TABLE IF EXISTS {t}"))
    mettre_a_jour_schema(_moteur_bd)


def lire_parametre(cle: str, defaut: str | None = None) -> str | None:
    with connexion() as c:
        r = c.execute(parametre.select().where(parametre.c.cle == cle)).first()
    return r.valeur if r else defaut


def ecrire_parametre(cle: str, valeur: str) -> None:
    with connexion() as c:
        if c.execute(parametre.select().where(parametre.c.cle == cle)).first():
            c.execute(parametre.update().where(parametre.c.cle == cle).values(valeur=valeur, maj_le=maintenant()))
        else:
            c.execute(parametre.insert().values(cle=cle, valeur=valeur, maj_le=maintenant()))


def parametre_cree_une_fois(cle: str, fabrique) -> str:
    """Valeur creee au premier besoin puis toujours la meme, pour tous les processus (premier arrive, seul retenu)."""
    from sqlalchemy.exc import IntegrityError
    existante = lire_parametre(cle)
    if existante is not None:
        return existante
    try:
        with connexion() as c:
            c.execute(parametre.insert().values(cle=cle, valeur=fabrique(), maj_le=maintenant()))
    except IntegrityError:
        pass  # un autre processus l'a creee entre-temps : on prend la sienne
    return lire_parametre(cle)


def connexion():
    """Transaction : `with db.connexion() as c:` valide a la sortie, annule en cas d'erreur."""
    return _moteur_bd.begin()


def lignes(resultat) -> list[dict]:
    return [dict(r._mapping) for r in resultat]


def ligne(resultat) -> dict | None:
    r = resultat.first()
    return dict(r._mapping) if r else None
