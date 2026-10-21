"""BPMN 2.0 (as saved by Camunda Modeler) -> WorkflowDefinition.

Supported subset: startEvent, endEvent, serviceTask, userTask
(`camunda:candidateGroups`), exclusiveGateway with a default flow,
sequenceFlow with `conditionExpression`. Node parameters are
`camunda:properties`: step, client_stage, max_iterations, timeout
(ISO 8601 duration or seconds), on_failure. Anything else is an error —
better a clear message at startup than a silently skipped node.

The file is untrusted input: no DTD, no entities, no network (XXE).
"""

import hashlib
import re

from lxml import etree

from src.process.domain.conditions import Condition, ConditionError
from src.process.domain.context import CONDITION_FIELDS
from src.process.domain.steps import STEPS
from src.process.domain.validation import validate
from src.process.domain.workflow import (
    Edge,
    Node,
    NodeConfig,
    NodeType,
    OnFailure,
    WorkflowDefinition,
)

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CAMUNDA = "http://camunda.org/schema/1.0/bpmn"
NS = {"bpmn": BPMN, "camunda": CAMUNDA}

_NODE_TYPES = {
    "startEvent": NodeType.START,
    "endEvent": NodeType.END,
    "serviceTask": NodeType.TASK,
    "userTask": NodeType.USER_TASK,
    "exclusiveGateway": NodeType.GATEWAY,
}
# Allowed inside a process but meaningless for execution.
_IGNORED = {"sequenceFlow", "textAnnotation", "association", "documentation", "extensionElements"}
_PROPERTIES = {"step", "client_stage", "max_iterations", "timeout", "on_failure"}
_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


class BpmnError(ValueError):
    pass


def _parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )


def parse_duration(value: str) -> int:
    """Seconds from `PT8H` / `P5D` / `P1DT2H30M` or a plain number of seconds."""
    if value.isdigit():
        return int(value)
    match = _DURATION.match(value)
    if match is None or value in ("P", "PT"):
        raise BpmnError(f"Invalid duration {value!r}")
    parts = {k: int(v or 0) for k, v in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def parse_bpmn(content: bytes) -> WorkflowDefinition:
    if b"<!DOCTYPE" in content.upper().replace(b"<!doctype", b"<!DOCTYPE"):
        raise BpmnError("DOCTYPE is not allowed in a route file")
    try:
        root = etree.fromstring(content, _parser())
    except etree.XMLSyntaxError as exc:
        raise BpmnError(f"Not a valid XML: {exc}") from None
    if root.tag != f"{{{BPMN}}}definitions":
        raise BpmnError("Root element must be bpmn:definitions")

    processes = root.findall("bpmn:process", NS)
    if len(processes) != 1:
        raise BpmnError(f"Exactly one bpmn:process expected, found {len(processes)}")
    process = processes[0]
    code = process.get("id") or ""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", code):
        raise BpmnError(f"Process id {code!r} must be a code like express_v1")
    version_tag = process.get(f"{{{CAMUNDA}}}versionTag", "1")
    if not version_tag.isdigit():
        raise BpmnError(f"camunda:versionTag must be a number, got {version_tag!r}")

    nodes: dict[str, Node] = {}
    defaults: dict[str, str] = {}
    for element in process:
        if not isinstance(element.tag, str):
            continue
        local = etree.QName(element).localname
        if local in _IGNORED:
            continue
        if local not in _NODE_TYPES:
            raise BpmnError(f"Unsupported element bpmn:{local} ({element.get('id')})")
        node = _node(element, _NODE_TYPES[local])
        if node.id in nodes:
            raise BpmnError(f"Duplicate id {node.id}")
        nodes[node.id] = node
        if local == "exclusiveGateway" and element.get("default"):
            defaults[node.id] = element.get("default") or ""

    edges = tuple(_edge(flow, defaults) for flow in process.findall("bpmn:sequenceFlow", NS))
    definition = WorkflowDefinition(
        code=code,
        version=int(version_tag),
        nodes=nodes,
        edges=edges,
        source_hash=hashlib.sha256(content).hexdigest(),
    )
    validate(definition, STEPS)
    return definition


def _node(element: etree._Element, node_type: NodeType) -> Node:
    node_id = element.get("id")
    if not node_id:
        raise BpmnError(f"{etree.QName(element).localname} without id")
    properties = _properties(element)
    step = properties.get("step")
    if node_type in (NodeType.TASK, NodeType.USER_TASK) and not step:
        raise BpmnError(f"{node_id}: camunda:property 'step' is required on a task")
    try:
        config = NodeConfig(
            client_stage=properties.get("client_stage"),
            candidate_role=element.get(f"{{{CAMUNDA}}}candidateGroups"),
            max_iterations=int(properties["max_iterations"])
            if "max_iterations" in properties
            else None,
            timeout_seconds=parse_duration(properties["timeout"])
            if "timeout" in properties
            else None,
            on_failure=OnFailure(properties.get("on_failure", OnFailure.FAIL.value)),
        )
    except ValueError as exc:
        raise BpmnError(f"{node_id}: {exc}") from None
    return Node(node_id, node_type, element.get("name") or "", step, config)


def _properties(element: etree._Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for prop in element.findall("bpmn:extensionElements/camunda:properties/camunda:property", NS):
        name, value = prop.get("name") or "", prop.get("value") or ""
        if name not in _PROPERTIES:
            raise BpmnError(f"{element.get('id')}: unknown property {name!r}")
        values[name] = value
    return values


def _edge(flow: etree._Element, defaults: dict[str, str]) -> Edge:
    flow_id = flow.get("id") or ""
    source, target = flow.get("sourceRef") or "", flow.get("targetRef") or ""
    expression = flow.find("bpmn:conditionExpression", NS)
    condition = None
    if expression is not None and (expression.text or "").strip():
        try:
            condition = Condition(expression.text.strip(), CONDITION_FIELDS)  # type: ignore[union-attr]
        except ConditionError as exc:
            raise BpmnError(f"flow {flow_id}: {exc}") from None
    return Edge(flow_id, source, target, condition, defaults.get(source) == flow_id)
