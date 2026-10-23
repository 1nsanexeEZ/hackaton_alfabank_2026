"""identity: company consents (credit bureau of the company), who revoked a consent

Revision ID: identity_0003
Revises: scoring_0004
Create Date: 2026-10-28 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "identity_0003"
down_revision: str | None = "scoring_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSENTS = "identity_consents"


def upgrade() -> None:
    # NULL — a personal consent; the company of a company consent otherwise.
    op.add_column(CONSENTS, sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column(CONSENTS, sa.Column("revoked_by", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_identity_consents_organization_type",
        CONSENTS,
        ["organization_id", "type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_identity_consents_organization_type", table_name=CONSENTS)
    op.drop_column(CONSENTS, "revoked_by")
    op.drop_column(CONSENTS, "organization_id")
