"""applications: contract PDFs, their signing log, what the client signed

Revision ID: applications_0006
Revises: scoring_0006
Create Date: 2026-11-03 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "applications_0006"
down_revision: str | None = "scoring_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENTS = "applications_contract_documents"
EVENTS = "applications_contract_events"
SIGNATURES = "applications_signatures"


def upgrade() -> None:
    op.add_column(SIGNATURES, sa.Column("document_hash", sa.String(64), nullable=True))
    op.add_column(SIGNATURES, sa.Column("rules_version", sa.String(32), nullable=True))

    op.create_table(
        DOCUMENTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("offer_hash", sa.String(64), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seal", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications_applications.id"],
            name=op.f(
                "fk_applications_contract_documents_application_id_applications_applications"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications_contract_documents")),
        sa.UniqueConstraint(
            "application_id",
            "kind",
            "offer_hash",
            name=op.f("uq_applications_contract_documents_application_id"),
        ),
        sa.UniqueConstraint("sha256", name=op.f("uq_applications_contract_documents_sha256")),
    )
    op.create_index(
        op.f("ix_applications_contract_documents_application_id"), DOCUMENTS, ["application_id"]
    )

    op.create_table(
        EVENTS,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications_applications.id"],
            name=op.f("fk_applications_contract_events_application_id_applications_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications_contract_events")),
        sa.UniqueConstraint(
            "application_id", "seq", name=op.f("uq_applications_contract_events_application_id")
        ),
    )


def downgrade() -> None:
    op.drop_table(EVENTS)
    op.drop_index(op.f("ix_applications_contract_documents_application_id"), table_name=DOCUMENTS)
    op.drop_table(DOCUMENTS)
    op.drop_column(SIGNATURES, "rules_version")
    op.drop_column(SIGNATURES, "document_hash")
