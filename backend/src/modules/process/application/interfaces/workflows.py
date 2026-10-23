from typing import Protocol

from src.modules.process.domain.workflow import WorkflowDefinition


class WorkflowSource(Protocol):
    """Routes known to the application (loaded from BPMN at startup)."""

    def get(self, code: str) -> WorkflowDefinition:
        """LookupError for an unknown route."""
        ...

    def source(self, code: str) -> bytes: ...

    def codes(self) -> list[str]:
        """Codes of every route, sorted."""
        ...
