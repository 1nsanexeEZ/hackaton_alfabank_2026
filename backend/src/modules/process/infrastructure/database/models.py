"""SQLAlchemy models of process. Tables are prefixed with `process_`."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from src.core.infrastructure.database.base import Base, JSONType
from src.core.infrastructure.database.mixins import UUIDPrimaryKeyMixin, VersionMixin


class WorkflowDefinitionRecord(Base):
    """Every route version a process ever ran on: a running process keeps its
    graph even after the BPMN file changes."""

    __tablename__ = "process_workflow_definitions"

    source_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProcessRecord(UUIDPrimaryKeyMixin, VersionMixin, Base):
    __tablename__ = "process_instances"

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.__table__.c.version}

    application_id: Mapped[UUID] = mapped_column(unique=True)
    workflow_code: Mapped[str] = mapped_column(String(64))
    workflow_version: Mapped[int] = mapped_column(Integer)
    workflow_hash: Mapped[str] = mapped_column(
        ForeignKey("process_workflow_definitions.source_hash")
    )
    status: Mapped[str] = mapped_column(String(16), index=True)
    current_node_id: Mapped[str] = mapped_column(String(128))
    waiting: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    # Copy of waiting.since for the timeout job.
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSONType)
    iterations: Mapped[dict[str, int]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list["StepExecutionRecord"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="StepExecutionRecord.started_at"
    )


class StepExecutionRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "process_step_executions"

    process_id: Mapped[UUID] = mapped_column(
        ForeignKey("process_instances.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(128))
    step_code: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    iteration: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(16))
    command_event_id: Mapped[UUID | None]
    error: Mapped[str | None] = mapped_column(Text)


class UserTaskRecord(UUIDPrimaryKeyMixin, VersionMixin, Base):
    __tablename__ = "process_user_tasks"
    __table_args__ = (Index("ix_process_user_tasks_queue", "candidate_role", "status", "due_at"),)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        # Two underwriters claiming the same task: the second gets 409.
        return {"version_id_col": cls.__table__.c.version}

    process_id: Mapped[UUID] = mapped_column(
        ForeignKey("process_instances.id", ondelete="CASCADE"), index=True
    )
    application_id: Mapped[UUID] = mapped_column(index=True)
    node_id: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(64))
    candidate_role: Mapped[str] = mapped_column(String(64))
    form_schema: Mapped[dict[str, Any]] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(16))
    assignee_id: Mapped[UUID | None]
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    completed_by: Mapped[UUID | None]
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
