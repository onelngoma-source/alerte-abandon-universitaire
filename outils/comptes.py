"""Comptes, en ligne de commande : pour la direction informatique, quand plus personne ne peut se connecter.

    python -m outils.comptes lister
    python -m outils.comptes reinitialiser IDENTIFIANT     mot de passe provisoire, a changer a la connexion
    python -m outils.comptes debloquer IDENTIFIANT         efface les echecs de connexion de ce compte

Chaque operation est tracee dans le journal (identifiant « console »), comme si elle avait ete faite dans l'application.
"""
import argparse
import sys
from pathlib import Path

from sqlalchemy import select
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db  # noqa: E402
from metier.journal import tracer  # noqa: E402

CONSOLE = {"id": None, "identifiant": "console"}


def main(arguments=None) -> int:
    p = argparse.ArgumentParser(prog="python -m outils.comptes", description=__doc__.split("\n\n")[0])
    sous = p.add_subparsers(dest="commande", required=True)
    sous.add_parser("lister")
    for nom in ("reinitialiser", "debloquer"):
        sous.add_parser(nom).add_argument("identifiant")
    a = p.parse_args(arguments)
    db.initialiser()
    u = db.utilisateur
    with db.connexion() as c:
        if a.commande == "lister":
            for r in c.execute(select(u.c.identifiant, u.c.nom, u.c.role, u.c.actif, u.c.derniere_connexion).order_by(u.c.id)):
                print(f"{r.identifiant}\t{r.nom}\t{r.role}\t{'actif' if r.actif else 'désactivé'}\t{r.derniere_connexion or 'jamais'}")
            return 0
        compte = db.ligne(c.execute(select(u).where(u.c.identifiant == a.identifiant)))
        if compte is None:
            print(f"Aucun compte « {a.identifiant} ».", file=sys.stderr)
            return 2
        from auth import _identifiant_normalise
        c.execute(db.echec_connexion.delete().where(db.echec_connexion.c.identifiant == _identifiant_normalise(a.identifiant)))
        if a.commande == "debloquer":
            tracer(c, CONSOLE, "modification_compte", "utilisateur", compte["id"], {"deblocage": True})
            print(f"Échecs de connexion effacés pour « {a.identifiant} ».")
            return 0
        from volets.administration import _mot_de_passe_provisoire
        provisoire = _mot_de_passe_provisoire()
        c.execute(u.update().where(u.c.id == compte["id"]).values(
            mdp_hache=generate_password_hash(provisoire), doit_changer_mdp=True, actif=True))
        tracer(c, CONSOLE, "reinitialisation_mdp", "utilisateur", compte["id"])
    print(f"Mot de passe provisoire de « {a.identifiant} » : {provisoire}")
    print("À transmettre par un canal sûr ; il devra être changé à la première connexion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
