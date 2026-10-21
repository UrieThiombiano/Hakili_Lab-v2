"""fiche_remediation

Revision ID: a1b2c3d4e5f6
Revises: fe6cb3723c1f
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'fe6cb3723c1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'suivi_fiche_remediation',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('competence_id', sa.String(length=20), nullable=False),
        sa.Column('type_erreur_id', sa.String(length=3), nullable=False),
        sa.Column('niveau', sa.String(length=10), nullable=False),
        sa.Column('contenu', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
        sa.Column('version', sa.String(length=10), nullable=False, server_default='generee'),
        sa.Column('date_generation', sa.DateTime(), nullable=False),
        sa.Column('corrigee_par', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('date_correction', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['competence_id'], ['referentiel_competence.code'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['type_erreur_id'], ['referentiel_typeerreur.code'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('competence_id', 'type_erreur_id', 'niveau', name='fiche_remediation_unique_par_couple'),
        sa.CheckConstraint("version IN ('generee', 'corrigee')", name='fiche_remediation_version_valide'),
        sa.CheckConstraint(
            "version = 'generee' OR (corrigee_par <> '' AND date_correction IS NOT NULL)",
            name='fiche_remediation_correction_tracee',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('suivi_fiche_remediation')
