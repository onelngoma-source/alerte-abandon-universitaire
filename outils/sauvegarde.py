"""Sauvegarde et restauration de la base, quel que soit le moteur (SQLite ou PostgreSQL).

    python -m outils.sauvegarde cle                              tire une cle de chiffrement (a mettre dans SAUVEGARDE_CLE)
    python -m outils.sauvegarde creer [--dossier D] [--garder N] [--verifier]
    python -m outils.sauvegarde verifier FICHIER                 essai de restauration dans une base temporaire
    python -m outils.sauvegarde restaurer FICHIER [--forcer]     restauration dans la base configuree
    python -m outils.sauvegarde lister [--dossier D]

A planifier chaque nuit, par exemple (cron) :
    15 2 * * *  cd /srv/alerte && python -m outils.sauvegarde creer --dossier /srv/sauvegardes --garder 30 --verifier

Format d'un fichier .sauvegarde : gzip d'un objet JSON par ligne (en-tete, puis une ligne par enregistrement),
chiffre et scelle (Fernet : AES-128 et HMAC-SHA256) si la variable SAUVEGARDE_CLE est definie. L'en-tete donne,
pour chaque table, le nombre de lignes et une empreinte SHA-256 de leur contenu.

« Restauration testee » : `verifier` restaure le fichier dans une base vierge (SQLite temporaire), au schema de la
sauvegarde, relit toutes les lignes et recalcule les empreintes. Une seule valeur differente, une ligne manquante,
un fichier tronque ou altere : la verification echoue. La sauvegarde ne compte comme bonne qu'une fois verifiee.

Ce format est independant du moteur : une sauvegarde PostgreSQL se verifie dans SQLite, et une base peut changer
de moteur. Pour PostgreSQL, un `pg_dump` quotidien reste un complement utile (voir docs/PASSATION.md).
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db  # noqa: E402

FORMAT = "alerte-precoce/sauvegarde/1"
EXTENSION = ".sauvegarde"
LOT = 1000
IGNOREES = {"alembic_version"}


class SauvegardeInvalide(Exception):
    """Fichier illisible, altere, tronque, ou qui ne se restaure pas a l'identique."""


# ------------------------------------------------------------------ valeurs
def _vers_json(v):
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)  # les dates sont enregistrees en UTC (db.Horodatage)
        return {"$dt": v.astimezone(timezone.utc).isoformat()}
    if isinstance(v, date):
        return {"$d": v.isoformat()}
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (bytes, memoryview)):
        return {"$b": base64.b64encode(bytes(v)).decode()}
    return v


def _depuis_json(v):
    if isinstance(v, dict):
        if "$dt" in v:
            return datetime.fromisoformat(v["$dt"])
        if "$d" in v:
            return date.fromisoformat(v["$d"])
        if "$b" in v:
            return base64.b64decode(v["$b"])
    return v


def _ligne_canonique(ligne: dict) -> str:
    return json.dumps({k: _vers_json(v) for k, v in ligne.items()}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ------------------------------------------------------------------ lecture de la base
def _tables(moteur) -> list:
    meta = MetaData()
    meta.reflect(moteur)
    return [t for t in meta.sorted_tables if t.name not in IGNOREES]


def _parcourir(c, table):
    """Lignes d'une table dans un ordre stable (cle primaire), sous forme de textes canoniques."""
    ordre = list(table.primary_key.columns) or list(table.columns)
    for r in c.execute(select(table).order_by(*ordre)).mappings():
        yield _ligne_canonique(dict(r))


def empreintes(moteur) -> dict:
    """Pour chaque table : nombre de lignes et empreinte SHA-256 de leur contenu canonique."""
    resultat = {}
    with moteur.connect() as c:
        for t in _tables(moteur):
            h, n = hashlib.sha256(), 0
            for ligne in _parcourir(c, t):
                h.update(ligne.encode() + b"\n")
                n += 1
            resultat[t.name] = {"lignes": n, "empreinte": h.hexdigest()}
    return resultat


def _revision(moteur) -> str | None:
    from alembic.runtime.migration import MigrationContext
    with moteur.connect() as c:
        return MigrationContext.configure(c).get_current_revision()


# ------------------------------------------------------------------ chiffrement
def _fernet(cle: str | None = None):
    cle = cle if cle is not None else os.environ.get("SAUVEGARDE_CLE", "").strip()
    if not cle:
        return None
    from cryptography.fernet import Fernet
    try:
        return Fernet(cle.encode())
    except (ValueError, TypeError) as e:
        raise SauvegardeInvalide("SAUVEGARDE_CLE n'est pas une cle valide : utilisez `python -m outils.sauvegarde cle`.") from e


def nouvelle_cle() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


# ------------------------------------------------------------------ creation
def creer(moteur, chemin: Path, cle: str | None = None) -> dict:
    """Ecrit la sauvegarde complete de la base dans `chemin`. Rend l'en-tete (tables, lignes, empreintes)."""
    tables = _tables(moteur)
    entete = {"format": FORMAT, "revision": _revision(moteur), "moteur": moteur.dialect.name,
              "cree_le": db.maintenant().isoformat(), "tables": {}}
    corps = io.BytesIO()
    with gzip.GzipFile(fileobj=corps, mode="wb", mtime=0) as gz:
        lignes_par_table = {}
        with moteur.connect() as c:  # une seule transaction : image coherente de la base
            for t in tables:
                h, n, contenu = hashlib.sha256(), 0, []
                for ligne in _parcourir(c, t):
                    h.update(ligne.encode() + b"\n")
                    contenu.append(ligne)
                    n += 1
                entete["tables"][t.name] = {"lignes": n, "empreinte": h.hexdigest()}
                lignes_par_table[t.name] = contenu
        gz.write((json.dumps(entete, ensure_ascii=False) + "\n").encode())
        for nom, contenu in lignes_par_table.items():
            for ligne in contenu:
                gz.write(('{"t":' + json.dumps(nom) + ',"l":' + ligne + "}\n").encode())
    donnees = corps.getvalue()
    fernet = _fernet(cle)
    if fernet:
        donnees = fernet.encrypt(donnees)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_suffix(chemin.suffix + ".partiel")
    temporaire.write_bytes(donnees)
    os.chmod(temporaire, 0o600)
    temporaire.replace(chemin)  # jamais de fichier a moitie ecrit sous le nom definitif
    entete["chiffree"] = bool(fernet)
    entete["taille"] = len(donnees)
    return entete


# ------------------------------------------------------------------ lecture d'un fichier
def lire(chemin: Path, cle: str | None = None):
    """Rend (en-tete, lignes) ; leve SauvegardeInvalide si le fichier est altere, tronque ou mal dechiffre."""
    brut = Path(chemin).read_bytes()
    if brut[:2] != b"\x1f\x8b":  # pas un gzip : fichier chiffre
        fernet = _fernet(cle)
        if fernet is None:
            raise SauvegardeInvalide("Sauvegarde chiffrée : définissez SAUVEGARDE_CLE pour la lire.")
        from cryptography.fernet import InvalidToken
        try:
            brut = fernet.decrypt(brut)
        except InvalidToken as e:
            raise SauvegardeInvalide("Déchiffrement impossible : clé incorrecte, ou fichier modifié depuis sa création.") from e
    try:
        texte = gzip.decompress(brut).decode()
    except (OSError, EOFError, UnicodeDecodeError) as e:
        raise SauvegardeInvalide("Fichier illisible ou tronqué.") from e
    lignes = texte.splitlines()
    try:
        entete = json.loads(lignes[0])
    except (IndexError, json.JSONDecodeError) as e:
        raise SauvegardeInvalide("En-tête de sauvegarde illisible.") from e
    if entete.get("format") != FORMAT:
        raise SauvegardeInvalide(f"Format inconnu : {entete.get('format')!r}.")
    return entete, lignes[1:]


# ------------------------------------------------------------------ restauration
def _vider(moteur) -> None:
    meta = MetaData()
    meta.reflect(moteur)
    meta.drop_all(moteur)


def _base_vide(moteur) -> bool:
    with moteur.connect() as c:
        for t in _tables(moteur):
            if c.execute(select(func.count()).select_from(t)).scalar():
                return False
    return True


def restaurer(chemin: Path, moteur, forcer: bool = False, cle: str | None = None) -> dict:
    """Restaure `chemin` dans la base `moteur`, verifie les empreintes, puis met le schema a jour.
    Refuse d'ecraser une base qui contient des donnees, sauf `forcer`."""
    from alembic import command
    entete, lignes = lire(chemin, cle)
    if not _base_vide(moteur):
        if not forcer:
            raise SauvegardeInvalide("La base cible contient déjà des données : utilisez --forcer pour la remplacer.")
    _vider(moteur)
    with moteur.begin() as c:
        cfg = db.config_migrations(c)
        if entete.get("revision"):
            command.upgrade(cfg, entete["revision"])  # meme schema que la base sauvegardee
    meta = MetaData()
    meta.reflect(moteur)
    tables = {t.name: t for t in meta.sorted_tables}
    inconnues = set(entete["tables"]) - set(tables)
    if inconnues:
        raise SauvegardeInvalide(f"Tables absentes du schéma : {', '.join(sorted(inconnues))}.")
    par_table: dict[str, list] = {nom: [] for nom in entete["tables"]}
    try:
        for brute in lignes:
            if brute:
                r = json.loads(brute)
                par_table[r["t"]].append({k: _depuis_json(v) for k, v in r["l"].items()})
    except (json.JSONDecodeError, KeyError) as e:
        raise SauvegardeInvalide("Contenu de sauvegarde illisible.") from e
    with moteur.begin() as c:
        for t in meta.sorted_tables:  # ordre des cles etrangeres
            contenu = par_table.get(t.name, [])
            for i in range(0, len(contenu), LOT):
                c.execute(t.insert(), contenu[i:i + LOT])
        if c.dialect.name == "postgresql":  # les compteurs d'identifiants reprennent apres le plus grand restaure
            for t in meta.sorted_tables:
                if "id" in t.c and t.c.id.primary_key:
                    # nom de table lu dans le schema de la base (jamais une saisie), cite par le dialecte
                    nom = c.dialect.identifier_preparer.quote(t.name)
                    c.execute(text("SELECT setval(pg_get_serial_sequence(:t, 'id'), "  # nosec B608
                                   f"COALESCE((SELECT MAX(id) FROM {nom}), 1), (SELECT MAX(id) FROM {nom}) IS NOT NULL)"),
                              {"t": t.name})
    relues = empreintes(moteur)
    ecarts = [nom for nom, attendu in entete["tables"].items() if relues.get(nom) != attendu]
    if ecarts:
        raise SauvegardeInvalide(f"Restauration non conforme pour : {', '.join(ecarts)}.")
    with moteur.begin() as c:
        command.upgrade(db.config_migrations(c), "head")
    return {"revision": entete["revision"], "cree_le": entete["cree_le"],
            "lignes": sum(t["lignes"] for t in entete["tables"].values()), "tables": len(entete["tables"])}


def verifier(chemin: Path, cle: str | None = None) -> dict:
    """Essai de restauration complet dans une base SQLite temporaire, effacee ensuite."""
    with tempfile.TemporaryDirectory() as dossier:
        moteur = create_engine(f"sqlite:///{dossier}/essai.db")
        try:
            return restaurer(chemin, moteur, cle=cle)
        finally:
            moteur.dispose()


# ------------------------------------------------------------------ rotation et suivi
def nom_de_fichier() -> str:
    return "alerte-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + EXTENSION


def lister(dossier: Path) -> list[Path]:
    return sorted(Path(dossier).glob("alerte-*" + EXTENSION))


def faire_tourner(dossier: Path, garder: int) -> list[Path]:
    fichiers = lister(dossier)
    supprimes = fichiers[:-garder] if garder > 0 else []
    for f in supprimes:
        f.unlink()
    return supprimes


def noter(etat: dict) -> None:
    """Garde en base l'etat de la derniere sauvegarde : la page Donnees l'affiche, /sante le signale."""
    from metier.journal import tracer
    db.ecrire_parametre("derniere_sauvegarde", json.dumps(etat, ensure_ascii=False))
    with db.connexion() as c:
        tracer(c, None, "sauvegarde", detail={k: etat[k] for k in ("fichier", "lignes", "chiffree", "verifiee")})


def derniere() -> dict | None:
    valeur = db.lire_parametre("derniere_sauvegarde")
    return json.loads(valeur) if valeur else None


# ------------------------------------------------------------------ ligne de commande
def main(arguments=None) -> int:
    p = argparse.ArgumentParser(prog="python -m outils.sauvegarde", description=__doc__.split("\n\n")[0])
    sous = p.add_subparsers(dest="commande", required=True)
    sous.add_parser("cle", help="tire une cle de chiffrement")
    c = sous.add_parser("creer", help="sauvegarde la base configuree")
    c.add_argument("--dossier", default=os.environ.get("SAUVEGARDE_DOSSIER", "sauvegardes"))
    c.add_argument("--garder", type=int, default=int(os.environ.get("SAUVEGARDE_GARDER", "30")))
    c.add_argument("--verifier", action="store_true", help="essai de restauration juste apres")
    v = sous.add_parser("verifier", help="essai de restauration dans une base temporaire")
    v.add_argument("fichier")
    r = sous.add_parser("restaurer", help="restaure dans la base configuree (DATABASE_URL ou DB_PATH)")
    r.add_argument("fichier")
    r.add_argument("--forcer", action="store_true", help="remplace une base qui contient deja des donnees")
    li = sous.add_parser("lister", help="sauvegardes presentes dans le dossier")
    li.add_argument("--dossier", default=os.environ.get("SAUVEGARDE_DOSSIER", "sauvegardes"))
    a = p.parse_args(arguments)

    try:
        if a.commande == "cle":
            print(nouvelle_cle())
            print("A garder hors du serveur (coffre de mots de passe) : sans elle, les sauvegardes sont illisibles.", file=sys.stderr)
            return 0
        if a.commande == "lister":
            for f in lister(Path(a.dossier)):
                print(f"{f.name}\t{f.stat().st_size} octets")
            return 0
        if a.commande == "verifier":
            bilan = verifier(Path(a.fichier))
            print(f"Sauvegarde valide : {bilan['lignes']} lignes dans {bilan['tables']} tables, restaurées à l'identique "
                  f"(schéma {bilan['revision']}, créée le {bilan['cree_le']}).")
            return 0
        db.initialiser()
        moteur = db.moteur_bd()
        if a.commande == "creer":
            if not os.environ.get("SAUVEGARDE_CLE"):
                print("Attention : SAUVEGARDE_CLE absente, la sauvegarde n'est pas chiffrée.", file=sys.stderr)
            chemin = Path(a.dossier) / nom_de_fichier()
            entete = creer(moteur, chemin)
            lignes = sum(t["lignes"] for t in entete["tables"].values())
            etat = {"fichier": chemin.name, "cree_le": entete["cree_le"], "taille": entete["taille"], "lignes": lignes,
                    "chiffree": entete["chiffree"], "verifiee": False}
            if a.verifier:
                verifier(chemin)
                etat.update(verifiee=True, verifiee_le=db.maintenant().isoformat())
            noter(etat)
            supprimes = faire_tourner(Path(a.dossier), a.garder)
            print(f"{chemin} : {lignes} lignes, {entete['taille']} octets"
                  + (", chiffrée" if entete["chiffree"] else "") + (", vérifiée" if etat["verifiee"] else "")
                  + (f" ; {len(supprimes)} ancienne(s) supprimée(s)" if supprimes else "") + ".")
            return 0
        if a.commande == "restaurer":
            bilan = restaurer(Path(a.fichier), moteur, forcer=a.forcer)
            print(f"Base restaurée : {bilan['lignes']} lignes ({bilan['tables']} tables), schéma mis à jour.")
            return 0
    except SauvegardeInvalide as e:
        print(f"ÉCHEC : {e}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
