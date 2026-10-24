"""applications: beneficial owners named by the client (115-FZ art. 6.1)

Revision ID: applications_0005
Revises: applications_0004
Create Date: 2026-11-01 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "applications_0005"
down_revision: str | None = "applications_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications_applications",
        sa.Column("beneficial_owners", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("applications_applications", "beneficial_owners")
