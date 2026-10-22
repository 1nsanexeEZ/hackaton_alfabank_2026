"""products: credit products catalog

Revision ID: products_0001
Revises: clients_0001
Create Date: 2026-10-22 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "products_0001"
down_revision: str | None = "clients_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products_credit_products",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("frontend_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("short_description", sa.String(length=500), nullable=False),
        sa.Column("description_plain", sa.Text(), nullable=False),
        sa.Column("purposes", postgresql.JSONB(), nullable=False),
        sa.Column("facility", sa.String(length=32), nullable=False),
        sa.Column("repayment_options", postgresql.JSONB(), nullable=False),
        sa.Column("amount_min", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("amount_max", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("term_min_months", sa.Integer(), nullable=False),
        sa.Column("term_max_months", sa.Integer(), nullable=False),
        sa.Column("rate_base", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("rate_max", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("collateral_kind", sa.String(length=16), nullable=False),
        sa.Column("collateral_types", postgresql.JSONB(), nullable=False),
        sa.Column("collateral_required_from", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("guarantee", sa.String(length=32), nullable=False),
        sa.Column("target_use_confirmation", sa.Boolean(), nullable=False),
        sa.Column("support_program", postgresql.JSONB(), nullable=True),
        sa.Column("min_business_age_months", sa.Integer(), nullable=False),
        sa.Column("allowed_legal_forms", postgresql.JSONB(), nullable=False),
        sa.Column("min_annual_revenue", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("required_documents", postgresql.JSONB(), nullable=False),
        sa.Column("application_fields_schema", postgresql.JSONB(), nullable=False),
        sa.Column("workflow_code", sa.String(length=64), nullable=False),
        sa.Column("auto_decision_limit", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name=op.f("ck_products_credit_products_status"),
        ),
        sa.CheckConstraint(
            "amount_min > 0 AND amount_min <= amount_max",
            name=op.f("ck_products_credit_products_amount_range"),
        ),
        sa.CheckConstraint(
            "term_min_months >= 1 AND term_min_months <= term_max_months",
            name=op.f("ck_products_credit_products_term_range"),
        ),
        sa.CheckConstraint(
            "rate_base >= 0 AND rate_base <= rate_max",
            name=op.f("ck_products_credit_products_rate_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products_credit_products")),
        sa.UniqueConstraint("code", "version", name=op.f("uq_products_credit_products_code")),
    )


def downgrade() -> None:
    op.drop_table("products_credit_products")
