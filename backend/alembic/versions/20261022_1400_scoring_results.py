"""scoring: results

Revision ID: scoring_0001
Revises: projector_0001
Create Date: 2026-10-22 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "scoring_0001"
down_revision: str | None = "projector_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESULTS = "scoring_results"


def upgrade() -> None:
    op.create_table(
        RESULTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_command", sa.Uuid(), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(length=1), nullable=False),
        sa.Column("factors", postgresql.JSONB(), nullable=False),
        sa.Column("flags", postgresql.JSONB(), nullable=False),
        sa.Column("bank_notes", postgresql.JSONB(), nullable=False),
        sa.Column("data_completeness", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scoring_results")),
        sa.UniqueConstraint(
            "requested_by_command", name=op.f("uq_scoring_results_requested_by_command")
        ),
    )
    op.create_index("ix_scoring_results_application", RESULTS, ["application_id", "computed_at"])


def downgrade() -> None:
    op.drop_index("ix_scoring_results_application", table_name=RESULTS)
    op.drop_table(RESULTS)
