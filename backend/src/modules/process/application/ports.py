from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.modules.process.domain.process import ProcessInstance
from src.modules.process.domain.tasks import UserTask
from src.modules.process.domain.workflow import WorkflowDefinition


class WorkflowSource(Protocol):
    """Routes known to the application (loaded from BPMN at startup)."""

    def get(self, code: str) -> WorkflowDefinition: ...

    def source(self, code: str) -> bytes: ...


class ProcessRepository(Protocol):
    async def get_by_application(
        self, application_id: UUID, for_update: bool = False
    ) -> ProcessInstance | None: ...

    async def add(self, process: ProcessInstance, source: bytes, now: datetime) -> None:
        """`source` — the BPMN the process runs on, kept as its graph snapshot."""
        ...

    async def save(self, process: ProcessInstance, now: datetime) -> None: ...

    async def waiting_for_replies_since(self, moment: datetime, limit: int) -> list[UUID]:
        """Applications whose process waits for a command reply since before `moment`."""
        ...


class TaskRepository(Protocol):
    async def add(self, task: UserTask) -> None: ...

    async def get(self, task_id: UUID) -> UserTask | None: ...

    async def save(self, task: UserTask) -> None: ...

    async def search(
        self, role: str | None, statuses: Sequence[str], limit: int, offset: int
    ) -> list[UserTask]: ...

    async def active_of_process(self, process_id: UUID) -> list[UserTask]: ...
