"""scoring: data quality of a result ("is the data complete?")

Revision ID: scoring_0004
Revises: scoring_0003
Create Date: 2026-10-27 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "scoring_0004"
down_revision: str | None = "scoring_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESULTS = "scoring_results"


def upgrade() -> None:
    op.add_column(RESULTS, sa.Column("quality", sa.String(16), nullable=True))
    op.add_column(RESULTS, sa.Column("quality_reasons", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column(RESULTS, "quality_reasons")
    op.drop_column(RESULTS, "quality")
