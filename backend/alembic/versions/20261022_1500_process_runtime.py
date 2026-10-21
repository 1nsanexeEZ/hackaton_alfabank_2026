"""process: route snapshots, process instances, step history, user tasks

Revision ID: process_0001
Revises: applications_0002
Create Date: 2026-10-22 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "process_0001"
down_revision: str | None = "applications_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "process_workflow_definitions",
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_hash", name=op.f("pk_process_workflow_definitions")),
    )
    op.create_index(
        op.f("ix_process_workflow_definitions_code"),
        "process_workflow_definitions",
        ["code"],
        unique=False,
    )
    op.create_table(
        "process_instances",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_code", sa.String(length=64), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("workflow_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_node_id", sa.String(length=128), nullable=False),
        sa.Column("waiting", postgresql.JSONB(), nullable=True),
        sa.Column("waiting_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column("iterations", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_hash"],
            ["process_workflow_definitions.source_hash"],
            name=op.f("fk_process_instances_workflow_hash_process_workflow_definitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_process_instances")),
        sa.UniqueConstraint("application_id", name=op.f("uq_process_instances_application_id")),
    )
    op.create_index(
        op.f("ix_process_instances_status"), "process_instances", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_process_instances_waiting_since"),
        "process_instances",
        ["waiting_since"],
        unique=False,
    )
    op.create_table(
        "process_step_executions",
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("step_code", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("command_event_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_instances.id"],
            name=op.f("fk_process_step_executions_process_id_process_instances"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_process_step_executions")),
    )
    op.create_index(
        op.f("ix_process_step_executions_process_id"),
        "process_step_executions",
        ["process_id"],
        unique=False,
    )
    op.create_table(
        "process_user_tasks",
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("candidate_role", sa.String(length=64), nullable=False),
        sa.Column("form_schema", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("completed_by", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["process_id"],
            ["process_instances.id"],
            name=op.f("fk_process_user_tasks_process_id_process_instances"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_process_user_tasks")),
    )
    op.create_index(
        op.f("ix_process_user_tasks_application_id"),
        "process_user_tasks",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_process_user_tasks_process_id"), "process_user_tasks", ["process_id"], unique=False
    )
    op.create_index(
        "ix_process_user_tasks_queue",
        "process_user_tasks",
        ["candidate_role", "status", "due_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_process_user_tasks_queue", table_name="process_user_tasks")
    op.drop_index(op.f("ix_process_user_tasks_process_id"), table_name="process_user_tasks")
    op.drop_index(op.f("ix_process_user_tasks_application_id"), table_name="process_user_tasks")
    op.drop_table("process_user_tasks")
    op.drop_index(
        op.f("ix_process_step_executions_process_id"), table_name="process_step_executions"
    )
    op.drop_table("process_step_executions")
    op.drop_index(op.f("ix_process_instances_waiting_since"), table_name="process_instances")
    op.drop_index(op.f("ix_process_instances_status"), table_name="process_instances")
    op.drop_table("process_instances")
    op.drop_index(
        op.f("ix_process_workflow_definitions_code"), table_name="process_workflow_definitions"
    )
    op.drop_table("process_workflow_definitions")
