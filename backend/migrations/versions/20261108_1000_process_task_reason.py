"""process: why an underwriter task is opened (a manual decision was not accepted, a step
failed or repeated too often)

Revision ID: process_0002
Revises: assistant_0001
Create Date: 2026-11-08 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "process_0002"
down_revision: str | None = "assistant_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TASKS = "process_user_tasks"


def upgrade() -> None:
    op.add_column(TASKS, sa.Column("reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column(TASKS, "reason")
