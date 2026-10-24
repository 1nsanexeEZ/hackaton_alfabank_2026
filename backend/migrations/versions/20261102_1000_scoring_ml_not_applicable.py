"""scoring: why a result has no ML estimate (the model does not apply)

Revision ID: scoring_0006
Revises: applications_0005
Create Date: 2026-11-02 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "scoring_0006"
down_revision: str | None = "applications_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESULTS = "scoring_results"


def upgrade() -> None:
    op.add_column(RESULTS, sa.Column("ml_not_applicable", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column(RESULTS, "ml_not_applicable")
