"""A route of application processing as a graph (loaded from BPMN)."""

from dataclasses import dataclass, field
from enum import StrEnum

from src.modules.process.domain.conditions import Condition


class NodeType(StrEnum):
    START = "start"
    END = "end"
    TASK = "task"  # service task: immediate or async step
    USER_TASK = "user_task"  # stoppable step: waits for a person
    GATEWAY = "gateway"


class OnFailure(StrEnum):
    FAIL = "fail"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True, slots=True)
class NodeConfig:
    client_stage: str | None = None
    candidate_role: str | None = None
    # A node inside a loop must say how many times it may run.
    max_iterations: int | None = None
    # Seconds to wait (info request due date, task SLA).
    timeout_seconds: int | None = None
    on_failure: OnFailure = OnFailure.FAIL
    # The underwriter's form when the step has several (project_assessment for a startup).
    form: str | None = None


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    type: NodeType
    name: str = ""
    step_code: str | None = None
    config: NodeConfig = field(default_factory=NodeConfig)


@dataclass(frozen=True, slots=True)
class Edge:
    id: str
    source: str
    target: str
    condition: Condition | None = None
    is_default: bool = False


@dataclass(frozen=True)
class WorkflowDefinition:
    code: str
    version: int
    nodes: dict[str, Node]
    edges: tuple[Edge, ...]
    source_hash: str = ""

    @property
    def start_node(self) -> Node:
        starts = [n for n in self.nodes.values() if n.type is NodeType.START]
        if len(starts) != 1:
            raise ValueError(f"Workflow {self.code} must have exactly one start")
        return starts[0]

    def node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def outgoing(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source == node_id]

    def first_node_with_step(self, step_code: str) -> Node | None:
        return next((n for n in self.nodes.values() if n.step_code == step_code), None)
