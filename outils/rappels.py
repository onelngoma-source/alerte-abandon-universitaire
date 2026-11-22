"""Rappels par courriel : a lancer une fois par jour ouvre (tache planifiee, cron).

    python -m outils.rappels            envoie les courriels (variables SMTP_* requises)
    python -m outils.rappels --essai    affiche les courriels sans rien envoyer

Chaque conseiller recoit la liste de ses dossiers en retard ou dont l'echeance arrive dans les 2 jours ;
le responsable et l'administrateur recoivent en plus le nombre de dossiers non attribues. Les courriels ne
contiennent que le matricule et l'echeance : aucune donnee scolaire ou financiere ne quitte l'outil.

Variables : SMTP_HOTE, SMTP_PORT (587), SMTP_UTILISATEUR, SMTP_MDP, SMTP_EXPEDITEUR, URL_APPLICATION.
"""
import os
import smtplib
import sys
from datetime import timedelta
from email.message import EmailMessage

from sqlalchemy import and_, func, select

import db


def preparer() -> list[EmailMessage]:
    url = os.environ.get("URL_APPLICATION", "").rstrip("/")
    aujourd_hui = db.maintenant().date()
    messages = []
    with db.connexion() as c:
        utilisateurs = db.lignes(c.execute(select(db.utilisateur).where(and_(db.utilisateur.c.actif.is_(True),
                                                                            db.utilisateur.c.email.isnot(None)))))
        non_attribues = c.execute(select(func.count()).select_from(db.dossier).where(
            and_(db.dossier.c.statut != "clos", db.dossier.c.conseiller_id.is_(None)))).scalar()
        for u in utilisateurs:
            dossiers = db.lignes(c.execute(
                select(db.dossier.c.echeance, db.etudiant.c.matricule, db.etudiant.c.id)
                .join(db.etudiant, db.etudiant.c.id == db.dossier.c.etudiant_id)
                .where(and_(db.dossier.c.conseiller_id == u["id"], db.dossier.c.statut != "clos",
                            db.dossier.c.echeance <= aujourd_hui + timedelta(days=2)))
                .order_by(db.dossier.c.echeance)))
            lignes = []
            for d in dossiers:
                etat = "en retard" if d["echeance"] < aujourd_hui else "à traiter d'ici le " + d["echeance"].strftime("%d/%m")
                lien = f" : {url}/etudiants/{d['id']}" if url else ""
                lignes.append(f"  - {d['matricule']}, {etat}{lien}")
            if u["role"] in ("responsable", "admin") and non_attribues:
                lignes.append(f"\n{non_attribues} dossier(s) en attente d'attribution" + (f" : {url}/dossiers?vue=non_attribues" if url else "."))
            if not lignes:
                continue
            m = EmailMessage()
            m["Subject"] = f"Alerte précoce : {len(dossiers)} dossier(s) à traiter"
            m["From"] = os.environ.get("SMTP_EXPEDITEUR", "alerte-precoce@localhost")
            m["To"] = u["email"]
            m.set_content(f"Bonjour {u['nom']},\n\nDossiers de suivi qui demandent votre attention :\n"
                          + "\n".join(lignes) + "\n\nCe message est envoyé automatiquement par l'outil d'alerte précoce.\n")
            messages.append(m)
    return messages


def envoyer(messages: list[EmailMessage]) -> None:
    hote = os.environ["SMTP_HOTE"]
    with smtplib.SMTP(hote, int(os.environ.get("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        if os.environ.get("SMTP_UTILISATEUR"):
            s.login(os.environ["SMTP_UTILISATEUR"], os.environ["SMTP_MDP"])
        for m in messages:
            s.send_message(m)


if __name__ == "__main__":
    db.initialiser()
    a_envoyer = preparer()
    if "--essai" in sys.argv or not os.environ.get("SMTP_HOTE"):
        for m in a_envoyer:
            print(f"À : {m['To']}\nObjet : {m['Subject']}\n\n{m.get_content()}\n{'-' * 60}")
        print(f"{len(a_envoyer)} courriel(s) préparé(s), aucun envoyé (mode essai ou SMTP_HOTE absent).")
    else:
        envoyer(a_envoyer)
        print(f"{len(a_envoyer)} courriel(s) envoyé(s).")
