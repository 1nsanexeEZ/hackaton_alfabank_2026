"""A task for a bank employee (underwriter review)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from src.core.exceptions.exceptions import (
    ConflictError,
    InvalidStatusTransitionError,
    PermissionDeniedError,
    ValidationError,
)
from src.modules.process.domain.enums import TaskStatus
from src.modules.process.domain.events import UserTaskCompleted

DECISIONS = frozenset({"approve", "counter_offer", "reject", "request_info"})


@dataclass
class UserTask:
    id: UUID
    process_id: UUID
    application_id: UUID
    node_id: str
    type: str
    candidate_role: str
    form_schema: dict[str, Any]
    created_at: datetime
    due_at: datetime | None
    status: TaskStatus = TaskStatus.OPEN
    assignee_id: UUID | None = None
    result: dict[str, Any] | None = None
    completed_by: UUID | None = None
    completed_at: datetime | None = None
    version: int = 1
    _events: list[UserTaskCompleted] = field(default_factory=list, repr=False)

    @property
    def is_active(self) -> bool:
        return self.status in (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)

    def is_overdue(self, now: datetime) -> bool:
        return self.is_active and self.due_at is not None and now > self.due_at

    def claim(self, account_id: UUID) -> None:
        """Take the task; claiming one's own task again is a no-op."""
        if self.status is TaskStatus.IN_PROGRESS and self.assignee_id == account_id:
            return
        if self.status is TaskStatus.IN_PROGRESS:
            raise ConflictError("The task is taken by another employee", details={"code": "taken"})
        if self.status is not TaskStatus.OPEN:
            raise InvalidStatusTransitionError("The task is already closed")
        self.status = TaskStatus.IN_PROGRESS
        self.assignee_id = account_id

    def complete(self, account_id: UUID, result: dict[str, Any], now: datetime) -> None:
        """Only the assignee closes the task, the comment is mandatory: the
        bank must be able to explain a manual decision."""
        if self.status is not TaskStatus.IN_PROGRESS:
            raise InvalidStatusTransitionError("Take the task before closing it")
        if self.assignee_id != account_id:
            raise PermissionDeniedError("Only the assignee closes the task")
        _validate_result(result)
        self.status = TaskStatus.DONE
        self.result = {**result, "completed_by": str(account_id)}
        self.completed_by = account_id
        self.completed_at = now
        self._events.append(
            UserTaskCompleted(
                occurred_at=now,
                process_id=self.process_id,
                application_id=self.application_id,
                task_id=self.id,
                completed_by=account_id,
                result=dict(self.result),
            )
        )

    def cancel(self) -> bool:
        if not self.is_active:
            return False
        self.status = TaskStatus.CANCELLED
        return True

    def pull_events(self) -> list[UserTaskCompleted]:
        events, self._events = self._events, []
        return events


def _validate_result(result: dict[str, Any]) -> None:
    problems: list[str] = []
    decision = result.get("decision")
    if decision not in DECISIONS:
        problems.append("decision")
    comment = result.get("comment")
    if not isinstance(comment, str) or not comment.strip():
        problems.append("comment")
    if decision in ("approve", "counter_offer"):
        for name in ("amount", "term_months", "rate"):
            if result.get(name) is None:
                problems.append(name)
    if decision == "request_info" and not result.get("requested_documents"):
        problems.append("requested_documents")
    if problems:
        raise ValidationError(
            "The decision is incomplete", details={"code": "invalid_result", "fields": problems}
        )
