"""products: a product only for a company without turnover (startup)

Revision ID: products_0002
Revises: decision_0002
Create Date: 2026-10-25 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "products_0002"
down_revision: str | None = "decision_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCTS = "products_credit_products"


def upgrade() -> None:
    op.add_column(
        PRODUCTS,
        sa.Column("startup_only", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column(PRODUCTS, "startup_only")
