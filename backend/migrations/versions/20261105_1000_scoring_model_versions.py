"""scoring: versions of the PD model kept by the admin (draft, active, archived)

Revision ID: scoring_0007
Revises: support_0001
Create Date: 2026-11-05 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "scoring_0007"
down_revision: str | None = "support_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERSIONS = "scoring_model_versions"


def upgrade() -> None:
    op.create_table(
        VERSIONS,
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("based_on", sa.String(32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_by", sa.Uuid(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("version", name=op.f("pk_scoring_model_versions")),
    )
    # Only one version is active: the built-in model from YAML is in force without it.
    op.create_index(
        "uq_scoring_model_versions_active",
        VERSIONS,
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_scoring_model_versions_active", table_name=VERSIONS)
    op.drop_table(VERSIONS)
