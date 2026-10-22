"""A route is checked when it is loaded: a broken BPMN file must stop the
start of the application, not a client's application in the middle."""

from collections.abc import Mapping

from src.process.domain.steps import StepKind, StepSpec
from src.process.domain.workflow import NodeType, WorkflowDefinition


class WorkflowValidationError(ValueError):
    def __init__(self, code: str, problems: list[str]) -> None:
        self.code = code
        self.problems = problems
        super().__init__(f"Workflow {code} is invalid: " + "; ".join(problems))


def validate(definition: WorkflowDefinition, steps: Mapping[str, StepSpec]) -> None:
    problems = _problems(definition, steps)
    if problems:
        raise WorkflowValidationError(definition.code, problems)


def _problems(definition: WorkflowDefinition, steps: Mapping[str, StepSpec]) -> list[str]:
    problems: list[str] = []
    nodes = definition.nodes
    starts = [n for n in nodes.values() if n.type is NodeType.START]
    ends = [n for n in nodes.values() if n.type is NodeType.END]
    if len(starts) != 1:
        problems.append(f"exactly one start event expected, found {len(starts)}")
    if not ends:
        problems.append("no end event")

    for edge in definition.edges:
        for end in (edge.source, edge.target):
            if end not in nodes:
                problems.append(f"flow {edge.id} refers to unknown node {end}")
    if problems:
        return problems

    for node in nodes.values():
        outgoing = definition.outgoing(node.id)
        if node.type is NodeType.END:
            if outgoing:
                problems.append(f"end {node.id} has outgoing flows")
            continue
        if node.type is NodeType.GATEWAY:
            defaults = [e for e in outgoing if e.is_default]
            if len(outgoing) < 2:
                problems.append(f"gateway {node.id} needs at least two outgoing flows")
            if len(defaults) != 1:
                problems.append(f"gateway {node.id} needs exactly one default flow")
            problems += [
                f"flow {e.id} out of gateway {node.id} has no condition"
                for e in outgoing
                if not e.is_default and e.condition is None
            ]
            continue
        if len(outgoing) != 1:
            problems.append(f"{node.type.value} {node.id} needs exactly one outgoing flow")
        if node.type in (NodeType.TASK, NodeType.USER_TASK):
            spec = steps.get(node.step_code or "")
            if spec is None:
                problems.append(f"{node.id}: unknown step {node.step_code!r}")
            elif (node.type is NodeType.USER_TASK) != (spec.kind is StepKind.STOPPABLE):
                problems.append(
                    f"{node.id}: step {spec.code} is {spec.kind.value}, "
                    f"it cannot be a {node.type.value}"
                )

    if len(starts) == 1:
        reachable = _reachable(definition, starts[0].id)
        problems += [f"node {n} is not reachable from start" for n in nodes if n not in reachable]
    finishing = _can_finish(definition)
    problems += [f"node {n} never reaches an end" for n in nodes if n not in finishing]

    for component in _cycles(definition):
        limited = [
            n
            for n in component
            if nodes[n].type in (NodeType.TASK, NodeType.USER_TASK)
            and nodes[n].config.max_iterations
        ]
        if not limited:
            problems.append(
                "loop " + " -> ".join(sorted(component)) + " has no node with max_iterations"
            )
    return problems


def _reachable(definition: WorkflowDefinition, start: str) -> set[str]:
    seen, stack = {start}, [start]
    while stack:
        for edge in definition.outgoing(stack.pop()):
            if edge.target not in seen:
                seen.add(edge.target)
                stack.append(edge.target)
    return seen


def _can_finish(definition: WorkflowDefinition) -> set[str]:
    finishing = {n.id for n in definition.nodes.values() if n.type is NodeType.END}
    changed = True
    while changed:
        changed = False
        for edge in definition.edges:
            if edge.target in finishing and edge.source not in finishing:
                finishing.add(edge.source)
                changed = True
    return finishing


def _cycles(definition: WorkflowDefinition) -> list[set[str]]:
    """Strongly connected components with a loop (Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[set[str]] = []
    counter = 0

    def visit(node: str) -> None:
        nonlocal counter
        index[node] = low[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for edge in definition.outgoing(node):
            if edge.target not in index:
                visit(edge.target)
                low[node] = min(low[node], low[edge.target])
            elif edge.target in on_stack:
                low[node] = min(low[node], index[edge.target])
        if low[node] == index[node]:
            component = set()
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.add(member)
                if member == node:
                    break
            self_loop = any(e.target == node for e in definition.outgoing(node))
            if len(component) > 1 or self_loop:
                components.append(component)

    for node_id in definition.nodes:
        if node_id not in index:
            visit(node_id)
    return components
