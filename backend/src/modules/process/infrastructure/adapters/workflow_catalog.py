"""Routes loaded once at startup from `src/modules/process/workflows/*.bpmn`.

A broken file stops the application with a list of problems: a route that
fails in the middle of a client's application is much worse."""

from dataclasses import dataclass
from pathlib import Path

from src.modules.process.application.interfaces.workflows import WorkflowSource
from src.modules.process.domain.exceptions import WorkflowValidationError
from src.modules.process.domain.workflow import WorkflowDefinition
from src.modules.process.infrastructure.bpmn import BpmnError, parse_bpmn

# The BPMN files are data of the module, not code: they stay in its root.
WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / "workflows"


class WorkflowLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadedWorkflow:
    definition: WorkflowDefinition
    # The BPMN as is: the frontend draws it with bpmn-js and highlights the path.
    source: bytes
    file_name: str


class WorkflowCatalog(WorkflowSource):
    def __init__(self, workflows: dict[str, LoadedWorkflow]) -> None:
        self._workflows = workflows

    def get(self, code: str) -> WorkflowDefinition:
        try:
            return self._workflows[code].definition
        except KeyError:
            raise LookupError(f"Unknown workflow {code!r}") from None

    def source(self, code: str) -> bytes:
        return self._workflows[code].source

    def codes(self) -> list[str]:
        return sorted(self._workflows)

    def all(self) -> list[LoadedWorkflow]:
        return [self._workflows[code] for code in self.codes()]


def load_workflows(directory: Path = WORKFLOWS_DIR) -> WorkflowCatalog:
    workflows: dict[str, LoadedWorkflow] = {}
    problems: list[str] = []
    files = sorted(directory.glob("*.bpmn"))
    if not files:
        raise WorkflowLoadError(f"No .bpmn routes in {directory}")
    for path in files:
        try:
            definition = parse_bpmn(path.read_bytes())
        except (BpmnError, WorkflowValidationError) as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        if path.stem != definition.code:
            problems.append(f"{path.name}: process id {definition.code!r} must match the file name")
        elif definition.code in workflows:
            problems.append(f"{path.name}: duplicate route {definition.code}")
        else:
            workflows[definition.code] = LoadedWorkflow(definition, path.read_bytes(), path.name)
    if problems:
        raise WorkflowLoadError("Broken routes:\n" + "\n".join(problems))
    return WorkflowCatalog(workflows)
