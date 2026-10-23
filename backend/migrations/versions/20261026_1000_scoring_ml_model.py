"""scoring: ML model estimate next to the PD model

Revision ID: scoring_0003
Revises: decision_0003
Create Date: 2026-10-26 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "scoring_0003"
down_revision: str | None = "decision_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESULTS = "scoring_results"


def upgrade() -> None:
    op.add_column(RESULTS, sa.Column("ml", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column(RESULTS, "ml")
