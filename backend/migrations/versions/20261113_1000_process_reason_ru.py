"""process: reasons for the underwriter in Russian — the old English prefix of a rejected
manual decision is rewritten in tasks and process contexts

Revision ID: process_0003
Revises: products_0003
Create Date: 2026-11-13 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "process_0003"
down_revision: str | None = "products_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "manual decision rejected: "
NEW = "Ручное решение не принято: "


def upgrade() -> None:
    start = len(OLD) + 1
    op.execute(
        f"UPDATE process_user_tasks SET reason = '{NEW}' || substr(reason, {start}) "
        f"WHERE reason LIKE '{OLD}%'"
    )
    op.execute(
        "UPDATE process_instances SET context = jsonb_set(context, '{manual_review_reason}', "
        f"to_jsonb('{NEW}' || substr(context->>'manual_review_reason', {start}))) "
        f"WHERE context->>'manual_review_reason' LIKE '{OLD}%'"
    )


def downgrade() -> None:
    """The Russian text stays: it is what the code writes now."""
