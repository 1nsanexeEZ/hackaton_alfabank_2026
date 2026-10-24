"""applications: who made the decision the client got (auto | underwriter)

Applications decided before this revision take it from the last final decision of
the decision module: the one the process handed to the application.

Revision ID: applications_0004
Revises: applications_0003
Create Date: 2026-10-31 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "applications_0004"
down_revision: str | None = "applications_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications_applications",
        sa.Column("decided_by", sa.String(length=16), nullable=True),
    )
    # A missing summary is stored as JSON null, not SQL NULL.
    op.execute(
        """
        UPDATE applications_applications AS a
        SET decided_by = (
            SELECT d.decided_by_type
            FROM decision_results AS d
            WHERE d.application_id = a.id
              AND d.outcome IN ('APPROVE', 'COUNTER_OFFER', 'REJECT')
            ORDER BY d.sequence DESC
            LIMIT 1
        )
        WHERE jsonb_typeof(a.decision_summary) = 'object'
        """
    )


def downgrade() -> None:
    op.drop_column("applications_applications", "decided_by")
