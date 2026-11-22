"""Schema de reference (version 98ca9ef, outil operationnel)

Revision : 0001_reference
Precedente : aucune
Creee le : 2026-11-22 11:57:25.294495
"""
from alembic import op
import sqlalchemy as sa


revision = '0001_reference'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('promotion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=200), nullable=False),
    sa.Column('origine', sa.String(length=20), nullable=False),
    sa.Column('cree_le', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nom')
    )
    op.create_table('utilisateur',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('identifiant', sa.String(length=80), nullable=False),
    sa.Column('nom', sa.String(length=160), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('mdp_hache', sa.String(length=255), nullable=False),
    sa.Column('actif', sa.Boolean(), nullable=False),
    sa.Column('doit_changer_mdp', sa.Boolean(), nullable=False),
    sa.Column('cree_le', sa.DateTime(timezone=True), nullable=False),
    sa.Column('derniere_connexion', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("role IN ('conseiller', 'responsable', 'admin')", name='ck_utilisateur_role'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('identifiant')
    )
    op.create_table('etudiant',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('promotion_id', sa.Integer(), nullable=False),
    sa.Column('matricule', sa.String(length=80), nullable=False),
    sa.Column('nom', sa.String(length=200), nullable=True),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('telephone', sa.String(length=60), nullable=True),
    sa.Column('filiere', sa.String(length=200), nullable=True),
    sa.Column('genre', sa.String(length=10), nullable=True),
    sa.Column('age', sa.Float(), nullable=True),
    sa.Column('boursier', sa.Integer(), nullable=True),
    sa.Column('debiteur', sa.Integer(), nullable=True),
    sa.Column('frais_a_jour', sa.Integer(), nullable=True),
    sa.Column('note_s1', sa.Float(), nullable=True),
    sa.Column('note_s2', sa.Float(), nullable=True),
    sa.Column('inscrites_s1', sa.Integer(), nullable=True),
    sa.Column('validees_s1', sa.Integer(), nullable=True),
    sa.Column('inscrites_s2', sa.Integer(), nullable=True),
    sa.Column('validees_s2', sa.Integer(), nullable=True),
    sa.Column('caracteristiques', sa.Text(), nullable=True),
    sa.Column('referent_id', sa.Integer(), nullable=True),
    sa.Column('evaluation_id', sa.Integer(), nullable=True),
    sa.Column('probabilite', sa.Float(), nullable=True),
    sa.Column('probabilite_noyau', sa.Float(), nullable=True),
    sa.Column('categorie', sa.String(length=10), nullable=True),
    sa.Column('moment', sa.String(length=2), nullable=True),
    sa.Column('facteur', sa.String(length=255), nullable=True),
    sa.Column('domaine_facteur', sa.String(length=20), nullable=True),
    sa.Column('devenir_reel', sa.String(length=10), nullable=True),
    sa.Column('abandon_reel', sa.Integer(), nullable=True),
    sa.Column('devenir_saisi_le', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cree_le', sa.DateTime(timezone=True), nullable=False),
    sa.Column('maj_le', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['promotion_id'], ['promotion.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['referent_id'], ['utilisateur.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('promotion_id', 'matricule', name='uq_etudiant_matricule')
    )
    with op.batch_alter_table('etudiant', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_etudiant_promotion_id'), ['promotion_id'], unique=False)

    op.create_table('journal',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('utilisateur_id', sa.Integer(), nullable=True),
    sa.Column('identifiant', sa.String(length=80), nullable=True),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('objet', sa.String(length=30), nullable=True),
    sa.Column('objet_id', sa.Integer(), nullable=True),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('adresse', sa.String(length=60), nullable=True),
    sa.Column('cree_le', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('journal', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_journal_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_journal_cree_le'), ['cree_le'], unique=False)

    op.create_table('lot',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('promotion_id', sa.Integer(), nullable=False),
    sa.Column('fichier', sa.String(length=255), nullable=True),
    sa.Column('effectif', sa.Integer(), nullable=False),
    sa.Column('nouveaux', sa.Integer(), nullable=False),
    sa.Column('mis_a_jour', sa.Integer(), nullable=False),
    sa.Column('ignorees', sa.Integer(), nullable=False),
    sa.Column('alertes_ouvertes', sa.Integer(), nullable=False),
    sa.Column('utilisateur_id', sa.Integer(), nullable=True),
    sa.Column('cree_le', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['promotion_id'], ['promotion.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('lot', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lot_promotion_id'), ['promotion_id'], unique=False)

    op.create_table('dossier',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('etudiant_id', sa.Integer(), nullable=False),
    sa.Column('statut', sa.String(length=20), nullable=False),
    sa.Column('conseiller_id', sa.Integer(), nullable=True),
    sa.Column('echeance', sa.Date(), nullable=True),
    sa.Column('ouvert_le', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ouvert_par', sa.Integer(), nullable=True),
    sa.Column('evaluation_id', sa.Integer(), nullable=True),
    sa.Column('probabilite_ouverture', sa.Float(), nullable=True),
    sa.Column('relance', sa.Boolean(), nullable=False),
    sa.Column('premier_contact_le', sa.DateTime(timezone=True), nullable=True),
    sa.Column('clos_le', sa.DateTime(timezone=True), nullable=True),
    sa.Column('motif_cloture', sa.String(length=40), nullable=True),
    sa.Column('probabilite_cloture', sa.Float(), nullable=True),
    sa.Column('maj_le', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("(statut = 'clos') = (motif_cloture IS NOT NULL)", name='ck_dossier_motif'),
    sa.CheckConstraint("statut IN ('a_contacter', 'contacte', 'entretien', 'accompagnement', 'clos')", name='ck_dossier_statut'),
    sa.ForeignKeyConstraint(['conseiller_id'], ['utilisateur.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['etudiant_id'], ['etudiant.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['ouvert_par'], ['utilisateur.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('dossier', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dossier_conseiller_id'), ['conseiller_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_dossier_etudiant_id'), ['etudiant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_dossier_statut'), ['statut'], unique=False)

    op.create_table('evaluation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('etudiant_id', sa.Integer(), nullable=False),
    sa.Column('lot_id', sa.Integer(), nullable=True),
    sa.Column('utilisateur_id', sa.Integer(), nullable=True),
    sa.Column('moment', sa.String(length=2), nullable=False),
    sa.Column('probabilite', sa.Float(), nullable=False),
    sa.Column('probabilite_noyau', sa.Float(), nullable=False),
    sa.Column('categorie', sa.String(length=10), nullable=False),
    sa.Column('facteur', sa.String(length=255), nullable=True),
    sa.Column('domaine_facteur', sa.String(length=20), nullable=True),
    sa.Column('nb_estimees', sa.Integer(), nullable=True),
    sa.Column('caracteristiques', sa.Text(), nullable=False),
    sa.Column('modele_version', sa.String(length=60), nullable=False),
    sa.Column('cree_le', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("categorie IN ('faible', 'moyen', 'eleve')", name='ck_evaluation_categorie'),
    sa.CheckConstraint("moment IN ('T0', 'T1', 'T2')", name='ck_evaluation_moment'),
    sa.CheckConstraint('probabilite >= 0 AND probabilite <= 1', name='ck_evaluation_probabilite'),
    sa.ForeignKeyConstraint(['etudiant_id'], ['etudiant.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lot_id'], ['lot.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('evaluation', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_evaluation_etudiant_id'), ['etudiant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_evaluation_lot_id'), ['lot_id'], unique=False)

    op.create_table('action',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dossier_id', sa.Integer(), nullable=False),
    sa.Column('utilisateur_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.String(length=30), nullable=False),
    sa.Column('texte', sa.Text(), nullable=True),
    sa.Column('statut_avant', sa.String(length=20), nullable=True),
    sa.Column('statut_apres', sa.String(length=20), nullable=True),
    sa.Column('cree_le', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['dossier_id'], ['dossier.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateur.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('action', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_action_dossier_id'), ['dossier_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('action', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_action_dossier_id'))

    op.drop_table('action')
    with op.batch_alter_table('evaluation', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_evaluation_lot_id'))
        batch_op.drop_index(batch_op.f('ix_evaluation_etudiant_id'))

    op.drop_table('evaluation')
    with op.batch_alter_table('dossier', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dossier_statut'))
        batch_op.drop_index(batch_op.f('ix_dossier_etudiant_id'))
        batch_op.drop_index(batch_op.f('ix_dossier_conseiller_id'))

    op.drop_table('dossier')
    with op.batch_alter_table('lot', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lot_promotion_id'))

    op.drop_table('lot')
    with op.batch_alter_table('journal', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_journal_cree_le'))
        batch_op.drop_index(batch_op.f('ix_journal_action'))

    op.drop_table('journal')
    with op.batch_alter_table('etudiant', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_etudiant_promotion_id'))

    op.drop_table('etudiant')
    op.drop_table('utilisateur')
    op.drop_table('promotion')
