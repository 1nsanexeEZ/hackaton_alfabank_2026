"""decision: a pre-approved offer remembers the key rate it was priced at

Revision ID: decision_0006
Revises: market_0001
Create Date: 2026-11-10 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "decision_0006"
down_revision: str | None = "market_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OFFERS = "decision_pre_approved_offers"


def upgrade() -> None:
    # Old rows stay NULL: they count as priced at another rate and get recalculated.
    op.add_column(OFFERS, sa.Column("key_rate", sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    op.drop_column(OFFERS, "key_rate")
