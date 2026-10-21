"""projector: application overview, underwriting queue, timeline, dashboard, metrics

Revision ID: projector_0001
Revises: notifications_0001
Create Date: 2026-10-22 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "projector_0001"
down_revision: str | None = "notifications_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projector_application_overview",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("inn", sa.String(length=12), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("term_months", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("client_stage", sa.String(length=255), nullable=True),
        sa.Column("action_required", sa.String(length=16), nullable=False),
        sa.Column("offer_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("offer_rate", sa.Numeric(7, 4), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("decision_outcome", sa.String(length=32), nullable=True),
        sa.Column("decided_by", sa.String(length=16), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manual_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_to_decision_sec", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("application_id", name=op.f("pk_projector_application_overview")),
    )
    op.create_index(
        op.f("ix_projector_application_overview_organization_id"),
        "projector_application_overview",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_projector_application_overview_submitted_at"),
        "projector_application_overview",
        ["submitted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_projector_application_overview_decided_at"),
        "projector_application_overview",
        ["decided_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_projector_application_overview_manual_review_at"),
        "projector_application_overview",
        ["manual_review_at"],
        unique=False,
    )
    op.create_index(
        "ix_projector_application_overview_org_updated_at",
        "projector_application_overview",
        ["organization_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_projector_application_overview_org_status",
        "projector_application_overview",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_table(
        "projector_underwriting_queue",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("candidate_role", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("inn", sa.String(length=12), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("risk_grade", sa.String(length=8), nullable=True),
        sa.Column("cash_gap", sa.Boolean(), nullable=False),
        sa.Column("routing_reasons", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("task_id", name=op.f("pk_projector_underwriting_queue")),
    )
    op.create_index(
        op.f("ix_projector_underwriting_queue_application_id"),
        "projector_underwriting_queue",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "ix_projector_underwriting_queue_role_due_at",
        "projector_underwriting_queue",
        ["candidate_role", "status", "due_at"],
        unique=False,
    )
    op.create_index(
        "ix_projector_underwriting_queue_role_amount",
        "projector_underwriting_queue",
        ["candidate_role", "status", "amount"],
        unique=False,
    )
    op.create_index(
        "ix_projector_underwriting_queue_role_score",
        "projector_underwriting_queue",
        ["candidate_role", "status", "score"],
        unique=False,
    )
    op.create_index(
        "ix_projector_underwriting_queue_role_created_at",
        "projector_underwriting_queue",
        ["candidate_role", "status", "created_at"],
        unique=False,
    )

    op.create_table(
        "projector_application_timeline",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projector_application_timeline")),
        sa.UniqueConstraint(
            "source_event_id", name=op.f("uq_projector_application_timeline_source_event_id")
        ),
    )
    op.create_index(
        "ix_projector_application_timeline_application_at",
        "projector_application_timeline",
        ["application_id", "at"],
        unique=False,
    )

    op.create_table(
        "projector_organization_dashboard",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("active_applications", sa.Integer(), nullable=False),
        sa.Column("action_required_count", sa.Integer(), nullable=False),
        sa.Column("pre_approved_max_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("pre_approved_rate_from", sa.Numeric(7, 4), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "organization_id", name=op.f("pk_projector_organization_dashboard")
        ),
    )

    op.create_table(
        "projector_backoffice_metrics",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("submitted", sa.Integer(), nullable=False),
        sa.Column("approved", sa.Integer(), nullable=False),
        sa.Column("counter_offers", sa.Integer(), nullable=False),
        sa.Column("rejected", sa.Integer(), nullable=False),
        sa.Column("manual_reviews", sa.Integer(), nullable=False),
        sa.Column("auto_decisions", sa.Integer(), nullable=False),
        sa.Column("decision_time_total_sec", sa.BigInteger(), nullable=False),
        sa.Column("decision_time_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "day", "product_code", name=op.f("pk_projector_backoffice_metrics")
        ),
    )


def downgrade() -> None:
    op.drop_table("projector_backoffice_metrics")
    op.drop_table("projector_organization_dashboard")
    op.drop_index(
        "ix_projector_application_timeline_application_at",
        table_name="projector_application_timeline",
    )
    op.drop_table("projector_application_timeline")
    op.drop_index(
        "ix_projector_underwriting_queue_role_created_at",
        table_name="projector_underwriting_queue",
    )
    op.drop_index(
        "ix_projector_underwriting_queue_role_score", table_name="projector_underwriting_queue"
    )
    op.drop_index(
        "ix_projector_underwriting_queue_role_amount", table_name="projector_underwriting_queue"
    )
    op.drop_index(
        "ix_projector_underwriting_queue_role_due_at", table_name="projector_underwriting_queue"
    )
    op.drop_index(
        op.f("ix_projector_underwriting_queue_application_id"),
        table_name="projector_underwriting_queue",
    )
    op.drop_table("projector_underwriting_queue")
    op.drop_index(
        "ix_projector_application_overview_org_status",
        table_name="projector_application_overview",
    )
    op.drop_index(
        "ix_projector_application_overview_org_updated_at",
        table_name="projector_application_overview",
    )
    op.drop_index(
        op.f("ix_projector_application_overview_manual_review_at"),
        table_name="projector_application_overview",
    )
    op.drop_index(
        op.f("ix_projector_application_overview_decided_at"),
        table_name="projector_application_overview",
    )
    op.drop_index(
        op.f("ix_projector_application_overview_submitted_at"),
        table_name="projector_application_overview",
    )
    op.drop_index(
        op.f("ix_projector_application_overview_organization_id"),
        table_name="projector_application_overview",
    )
    op.drop_table("projector_application_overview")
