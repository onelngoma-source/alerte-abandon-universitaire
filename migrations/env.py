"""Environnement Alembic : la base visee est celle de l'application (DATABASE_URL, sinon DB_PATH).

Deux usages :
  - au demarrage, db.initialiser() passe sa propre connexion (attribut « connexion ») et met la base a jour ;
  - en ligne de commande, depuis la racine du projet : `alembic upgrade head`, `alembic current`,
    `alembic revision --autogenerate -m "..."` (a relire avant de valider).
"""
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db  # noqa: E402


def rendu(type_, objet, autogen_context):
    """Horodatage est un type Python (fuseau UTC restitue a la lecture) : en base, c'est un DateTime avec fuseau.
    Les migrations n'importent donc pas db.py, qui pourra evoluer sans les casser."""
    if type_ == "type" and isinstance(objet, db.Horodatage):
        return "sa.DateTime(timezone=True)"
    return False


def executer(connexion) -> None:
    context.configure(
        connection=connexion, target_metadata=db.meta, compare_type=True, render_item=rendu,
        # SQLite ne sait pas modifier une colonne : Alembic recree la table (mode « batch »)
        render_as_batch=connexion.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


connexion = context.config.attributes.get("connexion")
if connexion is not None:
    executer(connexion)
elif context.is_offline_mode():
    context.configure(url=db.url_base(), target_metadata=db.meta, literal_binds=True, render_item=rendu)
    with context.begin_transaction():
        context.run_migrations()
else:
    moteur = create_engine(db.url_base())
    with moteur.begin() as c:
        executer(c)
    moteur.dispose()
