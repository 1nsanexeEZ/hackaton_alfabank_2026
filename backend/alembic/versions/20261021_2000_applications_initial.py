"""applications: applications, documents, info requests, history, signatures

Revision ID: applications_0001
Revises: core_0001
Create Date: 2026-10-21 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateSequence, DropSequence

revision: str = "applications_0001"
down_revision: str | None = "core_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FINAL = "status NOT IN ('disbursed', 'rejected', 'offer_declined', 'expired', 'cancelled')"
APPLICATIONS = "applications_applications"


def _application_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["application_id"],
        [f"{APPLICATIONS}.id"],
        name=op.f(f"fk_{table}_application_id_{APPLICATIONS}"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.execute(CreateSequence(sa.Sequence("applications_number_seq")))
    op.create_table(
        APPLICATIONS,
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("applicant_account_id", sa.Uuid(), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("client_stage", sa.String(length=255), nullable=True),
        sa.Column("product_terms", postgresql.JSONB(), nullable=False),
        sa.Column("request", postgresql.JSONB(), nullable=False),
        sa.Column("product_fields", postgresql.JSONB(), nullable=False),
        sa.Column("collateral", postgresql.JSONB(), nullable=True),
        sa.Column("consents", postgresql.JSONB(), nullable=False),
        sa.Column("org_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("offer", postgresql.JSONB(), nullable=True),
        sa.Column("decision_summary", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications_applications")),
        sa.UniqueConstraint("number", name=op.f("uq_applications_applications_number")),
    )
    op.create_index(
        op.f("ix_applications_applications_organization_id"),
        APPLICATIONS,
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_applications_applications_org_status",
        APPLICATIONS,
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_applications_applications_active_product",
        APPLICATIONS,
        ["organization_id", "product_code"],
        unique=True,
        postgresql_where=sa.text(FINAL),
    )
    op.create_table(
        "applications_documents",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("s3_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("info_request_id", sa.Uuid(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        _application_fk("applications_documents"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications_documents")),
        sa.UniqueConstraint("s3_key", name=op.f("uq_applications_documents_s3_key")),
    )
    op.create_index(
        op.f("ix_applications_documents_application_id"),
        "applications_documents",
        ["application_id"],
        unique=False,
    )
    op.create_table(
        "applications_info_requests",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("requested_fields", postgresql.JSONB(), nullable=False),
        sa.Column("requested_documents", postgresql.JSONB(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        _application_fk("applications_info_requests"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications_info_requests")),
    )
    op.create_index(
        op.f("ix_applications_info_requests_application_id"),
        "applications_info_requests",
        ["application_id"],
        unique=False,
    )
    op.create_table(
        "applications_status_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        _application_fk("applications_status_history"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications_status_history")),
    )
    op.create_index(
        op.f("ix_applications_status_history_application_id"),
        "applications_status_history",
        ["application_id"],
        unique=False,
    )
    op.create_table(
        "applications_signatures",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("signed_by", sa.Uuid(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("offer_hash", sa.String(length=64), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("edo_document_id", sa.String(length=128), nullable=True),
        _application_fk("applications_signatures"),
        sa.PrimaryKeyConstraint("application_id", name=op.f("pk_applications_signatures")),
    )


def downgrade() -> None:
    op.drop_table("applications_signatures")
    op.drop_index(
        op.f("ix_applications_status_history_application_id"),
        table_name="applications_status_history",
    )
    op.drop_table("applications_status_history")
    op.drop_index(
        op.f("ix_applications_info_requests_application_id"),
        table_name="applications_info_requests",
    )
    op.drop_table("applications_info_requests")
    op.drop_index(
        op.f("ix_applications_documents_application_id"), table_name="applications_documents"
    )
    op.drop_table("applications_documents")
    op.drop_index(
        "uq_applications_applications_active_product",
        table_name=APPLICATIONS,
        postgresql_where=sa.text(FINAL),
    )
    op.drop_index("ix_applications_applications_org_status", table_name=APPLICATIONS)
    op.drop_index(op.f("ix_applications_applications_organization_id"), table_name=APPLICATIONS)
    op.drop_table(APPLICATIONS)
    op.execute(DropSequence(sa.Sequence("applications_number_seq")))
