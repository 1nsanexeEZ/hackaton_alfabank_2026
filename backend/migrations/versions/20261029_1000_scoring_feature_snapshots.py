"""scoring: client feature store (feature snapshots by date)

Revision ID: scoring_0005
Revises: decision_0004
Create Date: 2026-10-29 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "scoring_0005"
down_revision: str | None = "decision_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SNAPSHOTS = "scoring_feature_snapshots"


def upgrade() -> None:
    op.create_table(
        SNAPSHOTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enrichment_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("features", postgresql.JSONB(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scoring_feature_snapshots")),
    )
    op.create_index(
        "ix_scoring_feature_snapshots_organization", SNAPSHOTS, ["organization_id", "as_of"]
    )
    op.create_index(
        "ix_scoring_feature_snapshots_enrichment", SNAPSHOTS, ["enrichment_snapshot_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_scoring_feature_snapshots_enrichment", table_name=SNAPSHOTS)
    op.drop_index("ix_scoring_feature_snapshots_organization", table_name=SNAPSHOTS)
    op.drop_table(SNAPSHOTS)
