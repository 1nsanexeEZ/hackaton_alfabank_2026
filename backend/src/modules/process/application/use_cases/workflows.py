"""Routes loaded at startup: the list and the BPMN for bpmn-js."""

from src.core.exceptions.exceptions import NotFoundError
from src.modules.process.application.dto.workflows import WorkflowDTO
from src.modules.process.application.interfaces.workflows import WorkflowSource


class ListWorkflowsUseCase:
    def __init__(self, workflows: WorkflowSource) -> None:
        self._workflows = workflows

    def execute(self) -> list[WorkflowDTO]:
        return [
            WorkflowDTO(
                code=definition.code,
                version=definition.version,
                source_hash=definition.source_hash,
                nodes=len(definition.nodes),
                flows=len(definition.edges),
            )
            for definition in map(self._workflows.get, self._workflows.codes())
        ]


class GetWorkflowDiagramUseCase:
    def __init__(self, workflows: WorkflowSource) -> None:
        self._workflows = workflows

    def execute(self, code: str) -> bytes:
        if code not in self._workflows.codes():
            raise NotFoundError("Workflow not found")
        return self._workflows.source(code)
