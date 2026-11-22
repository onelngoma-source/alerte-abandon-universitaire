"""Journal d'activite : qui a consulte ou modifie quoi, et quand. Indispensable pour des donnees personnelles."""
import json

from flask import has_request_context, request

import db


def tracer(c, utilisateur: dict | None, action: str, objet: str | None = None, objet_id: int | None = None,
           detail=None) -> None:
    if detail is not None and not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False)
    adresse = None
    if has_request_context():
        adresse = (request.remote_addr or "")[:60] or None  # reprise de X-Forwarded-For par ProxyFix (voir auth.py)
    c.execute(db.journal.insert().values(
        utilisateur_id=utilisateur["id"] if utilisateur else None,
        identifiant=utilisateur["identifiant"] if utilisateur else None,
        action=action, objet=objet, objet_id=objet_id, detail=detail, adresse=adresse, cree_le=db.maintenant()))
