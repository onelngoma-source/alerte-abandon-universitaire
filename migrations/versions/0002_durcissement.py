"""Durcissement : parametres, echecs de connexion partages, jetons de service

Revision : 0002_durcissement
Precedente : 0001_reference
Creee le : 2026-11-22 11:57:52.555163
"""
from alembic import op
import sqlalchemy as sa


revision = '0002_durcissement'
down_revision = '0001_reference'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('echec_connexion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('adresse', sa.String(length=60), nullable=True),
    sa.Column('identifiant', sa.String(length=80), nullable=True),
    sa.Column('cree_le', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('echec_connexion', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_echec_connexion_adresse'), ['adresse'], unique=False)
        batch_op.create_index(batch_op.f('ix_echec_connexion_cree_le'), ['cree_le'], unique=False)
        batch_op.create_index(batch_op.f('ix_echec_connexion_identifiant'), ['identifiant'], unique=False)

    op.create_table('parametre',
    sa.Column('cle', sa.String(length=60), nullable=False),
    sa.Column('valeur', sa.Text(), nullable=False),
    sa.Column('maj_le', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('cle')
    )
    op.create_table('jeton_service',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=120), nullable=False),
    sa.Column('prefixe', sa.String(length=12), nullable=False),
    sa.Column('empreinte', sa.String(length=64), nullable=False),
    sa.Column('cree_par', sa.Integer(), nullable=True),
    sa.Column('cree_le', sa.DateTime(timezone=True), nullable=False),
    sa.Column('derniere_utilisation', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoque_le', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['cree_par'], ['utilisateur.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('empreinte')
    )


def downgrade() -> None:
    op.drop_table('jeton_service')
    op.drop_table('parametre')
    with op.batch_alter_table('echec_connexion', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_echec_connexion_identifiant'))
        batch_op.drop_index(batch_op.f('ix_echec_connexion_cree_le'))
        batch_op.drop_index(batch_op.f('ix_echec_connexion_adresse'))

    op.drop_table('echec_connexion')
