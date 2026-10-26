"""notifications: the record «Доступ к компании закрыт» is no longer bound to the company —
its link led the former member to a company page they can no longer open, and the feed
now hides the records of the companies the reader has left

Revision ID: notifications_0002
Revises: process_0003
Create Date: 2026-11-14 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "notifications_0002"
down_revision: str | None = "process_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE notifications_feed_items SET organization_id = NULL, link = NULL "
        "WHERE source_type = 'MemberRemoved'"
    )


def downgrade() -> None:
    """The records stay unbound: it is what the code writes now."""
