"""sujet_verification_t3_t4_t5

Revision ID: fe6cb3723c1f
Revises: cab106d96cf9
Create Date: 2026-08-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fe6cb3723c1f'
down_revision: Union[str, Sequence[str], None] = 'cab106d96cf9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('session_suivi', sa.Column('sujet_verification_type', sa.String(length=2), nullable=True))
    op.add_column('session_suivi', sa.Column('sujet_verification_exercices', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=True))
    op.add_column('suivi_probleme', sa.Column('exercices_verification', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False, server_default='[]'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('suivi_probleme', 'exercices_verification')
    op.drop_column('session_suivi', 'sujet_verification_exercices')
    op.drop_column('session_suivi', 'sujet_verification_type')
