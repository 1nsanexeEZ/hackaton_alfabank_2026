"""enrichment: snapshots and source results

Revision ID: enrichment_0001
Revises: applications_0001
Create Date: 2026-10-21 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "enrichment_0001"
down_revision: str | None = "applications_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SNAPSHOTS = "enrichment_snapshots"
RESULTS = "enrichment_source_results"


def upgrade() -> None:
    op.create_table(
        SNAPSHOTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("inn", sa.String(length=12), nullable=False),
        sa.Column("requested_by_command", sa.Uuid(), nullable=False),
        sa.Column("requested_sources", postgresql.JSONB(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrichment_snapshots")),
        sa.UniqueConstraint(
            "requested_by_command", name=op.f("uq_enrichment_snapshots_requested_by_command")
        ),
    )
    op.create_index(
        "ix_enrichment_snapshots_application", SNAPSHOTS, ["application_id", "started_at"]
    )
    op.create_table(
        RESULTS,
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("error_kind", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            [f"{SNAPSHOTS}.id"],
            name=op.f(f"fk_{RESULTS}_snapshot_id_{SNAPSHOTS}"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("snapshot_id", "source", name=op.f("pk_enrichment_source_results")),
    )


def downgrade() -> None:
    op.drop_table(RESULTS)
    op.drop_index("ix_enrichment_snapshots_application", table_name=SNAPSHOTS)
    op.drop_table(SNAPSHOTS)
