"""projector: the kind of manual review in the underwriting queue, to filter by it

Revision ID: projector_0002
Revises: decision_0006
Create Date: 2026-11-11 10:00:00
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "projector_0002"
down_revision: str | None = "decision_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QUEUE = "projector_underwriting_queue"
# decision DISPUTE_REASON_CODES at the time of the migration: the rest is a check.
DISPUTE = {
    "ROUTE_AML_INCOMPLETE",
    "ROUTE_MASS_ADDRESS",
    "ROUTE_ML_UNAVAILABLE",
    "ROUTE_MODELS_DISAGREE",
    "ROUTE_REVENUE_MISMATCH",
    "ROUTE_SOURCES_FAILED",
    "ROUTE_THIRD_PARTIES_UNKNOWN",
    "ROUTE_VERIFICATION_MISMATCH",
}


def upgrade() -> None:
    op.add_column(QUEUE, sa.Column("review", sa.String(16), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text(f"SELECT task_id, routing_reasons FROM {QUEUE}")).all()
    for task_id, reasons in rows:
        codes = json.loads(reasons) if isinstance(reasons, str) else (reasons or [])
        if not codes:
            continue
        review = "dispute" if DISPUTE.intersection(codes) else "check"
        connection.execute(
            sa.text(f"UPDATE {QUEUE} SET review = :review WHERE task_id = :task_id"),
            {"review": review, "task_id": task_id},
        )


def downgrade() -> None:
    op.drop_column(QUEUE, "review")
