"""decision: soft triggers and the rate breakdown of policy_v3

Extended limits (by_turnover, by_grade, by_group, binding) go to the `limits`
JSON as they are: the column does not change.

Revision ID: decision_0002
Revises: scoring_0002
Create Date: 2026-10-25 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "decision_0002"
down_revision: str | None = "scoring_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESULTS = "decision_results"


def upgrade() -> None:
    op.add_column(RESULTS, sa.Column("triggers", postgresql.JSONB(), nullable=True))
    op.add_column(RESULTS, sa.Column("rate_breakdown", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column(RESULTS, "rate_breakdown")
    op.drop_column(RESULTS, "triggers")
