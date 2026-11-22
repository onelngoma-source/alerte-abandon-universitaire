"""Import automatique depuis un dossier de depot, alimente par le systeme de scolarite.

    python -m outils.synchroniser --depot /srv/depot-scolarite

Chaque fichier « <Nom de la promotion>.csv » du dossier est importe dans la promotion de ce nom (creee au besoin),
puis range dans depot/traites/ ; un fichier refuse va dans depot/erreurs/, avec un .txt qui explique pourquoi.
A planifier (cron), par exemple toutes les heures en journee :
    5 7-19 * * 1-5  cd /srv/alerte && python -m outils.synchroniser --depot /srv/depot-scolarite
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db  # noqa: E402
from metier import synchronisation as sync  # noqa: E402


def traiter(depot: Path, moteur) -> dict:
    depot = Path(depot)
    traites, erreurs = depot / "traites", depot / "erreurs"
    traites.mkdir(exist_ok=True)
    erreurs.mkdir(exist_ok=True)
    bilan = {"importes": [], "refuses": []}
    for fichier in sorted(depot.glob("*.csv")):
        horodatage = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        try:
            compte = sync.synchroniser(moteur, fichier.read_bytes(), fichier.stem, fichier.name, "depot")
        except sync.ImportRefuse as e:
            cible = erreurs / f"{horodatage}-{fichier.name}"
            fichier.replace(cible)
            cible.with_suffix(".txt").write_text(f"{fichier.name} refusé le {horodatage} (UTC) : {e}\n", encoding="utf-8")
            bilan["refuses"].append({"fichier": fichier.name, "motif": str(e)})
            continue
        fichier.replace(traites / f"{horodatage}-{fichier.name}")
        bilan["importes"].append({"fichier": fichier.name, "effectif": compte["effectif"], "nouveaux": compte["nouveaux"],
                                  "mis_a_jour": compte["mis_a_jour"], "dossiers_ouverts": compte["dossiers_ouverts"]})
    return bilan


def main(arguments=None) -> int:
    p = argparse.ArgumentParser(prog="python -m outils.synchroniser", description=__doc__.split("\n\n")[0])
    p.add_argument("--depot", default=os.environ.get("DEPOT_SCOLARITE"), required=not os.environ.get("DEPOT_SCOLARITE"))
    a = p.parse_args(arguments)
    db.initialiser()
    from moteur.scoring import Moteur
    bilan = traiter(Path(a.depot), Moteur())
    for i in bilan["importes"]:
        print(f"importé  {i['fichier']} : {i['effectif']} étudiants ({i['nouveaux']} nouveaux, {i['mis_a_jour']} mis à jour), "
              f"{i['dossiers_ouverts']} dossier(s) ouvert(s)")
    for r in bilan["refuses"]:
        print(f"REFUSÉ   {r['fichier']} : {r['motif']}", file=sys.stderr)
    return 1 if bilan["refuses"] else 0


if __name__ == "__main__":
    sys.exit(main())
