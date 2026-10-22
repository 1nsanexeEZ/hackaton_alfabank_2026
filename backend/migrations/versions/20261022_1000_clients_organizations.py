"""clients: organizations, members, financial reports

Revision ID: clients_0001
Revises: enrichment_0001
Create Date: 2026-10-22 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "clients_0001"
down_revision: str | None = "enrichment_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clients_organizations",
        sa.Column("inn", sa.String(length=12), nullable=False),
        sa.Column("ogrn", sa.String(length=15), nullable=False),
        sa.Column("kpp", sa.String(length=9), nullable=True),
        sa.Column("legal_form", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("registered_at", sa.Date(), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("region_code", sa.String(length=2), nullable=False),
        sa.Column("okved_main", sa.String(length=10), nullable=False),
        sa.Column("okved_extra", postgresql.JSONB(), nullable=False),
        sa.Column("tax_regime", sa.String(length=16), nullable=False),
        sa.Column("employees_count", sa.Integer(), nullable=False),
        sa.Column("registry_status", sa.String(length=16), nullable=False),
        sa.Column("registry_head", postgresql.JSONB(), nullable=True),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column("verification_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_discrepancies", postgresql.JSONB(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients_organizations")),
        sa.UniqueConstraint("inn", name=op.f("uq_clients_organizations_inn")),
        sa.UniqueConstraint("ogrn", name=op.f("uq_clients_organizations_ogrn")),
    )
    op.create_table(
        "clients_members",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("authority", sa.String(length=32), nullable=False),
        sa.Column("power_of_attorney", postgresql.JSONB(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("added_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["clients_organizations.id"],
            name=op.f("fk_clients_members_organization_id_clients_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id", "account_id", name=op.f("pk_clients_members")),
    )
    op.create_index(
        op.f("ix_clients_members_account_id"), "clients_members", ["account_id"], unique=False
    )
    op.create_table(
        "clients_financial_reports",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        # 0 — the whole year (NULL would let duplicates past the unique constraint).
        sa.Column("period_quarter", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("revenue", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("expenses", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("net_profit", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("total_liabilities", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("monthly_debt_payments", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "period_quarter BETWEEN 0 AND 4",
            name=op.f("ck_clients_financial_reports_period_quarter"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["clients_organizations.id"],
            name=op.f("fk_clients_financial_reports_organization_id_clients_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients_financial_reports")),
        sa.UniqueConstraint(
            "organization_id",
            "period_year",
            "period_quarter",
            "source",
            name=op.f("uq_clients_financial_reports_organization_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("clients_financial_reports")
    op.drop_index(op.f("ix_clients_members_account_id"), table_name="clients_members")
    op.drop_table("clients_members")
    op.drop_table("clients_organizations")
