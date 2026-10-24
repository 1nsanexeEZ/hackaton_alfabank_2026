"""applications: the client's answer about the beneficiary (115-FZ)

Revision ID: applications_0003
Revises: scoring_0005
Create Date: 2026-10-30 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "applications_0003"
down_revision: str | None = "scoring_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications_applications",
        sa.Column("beneficiary", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("applications_applications", "beneficiary")
