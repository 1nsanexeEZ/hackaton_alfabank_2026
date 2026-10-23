"""scoring: segment, scorecard, PD and reason codes of the PD model

Revision ID: scoring_0002
Revises: identity_0002
Create Date: 2026-10-25 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "scoring_0002"
down_revision: str | None = "identity_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESULTS = "scoring_results"


def upgrade() -> None:
    op.add_column(RESULTS, sa.Column("segment", sa.String(length=16), nullable=True))
    op.add_column(RESULTS, sa.Column("scorecard", sa.String(length=32), nullable=True))
    op.add_column(RESULTS, sa.Column("pd_12m", sa.Numeric(precision=5, scale=4), nullable=True))
    op.add_column(RESULTS, sa.Column("reason_codes", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column(RESULTS, "reason_codes")
    op.drop_column(RESULTS, "pd_12m")
    op.drop_column(RESULTS, "scorecard")
    op.drop_column(RESULTS, "segment")
