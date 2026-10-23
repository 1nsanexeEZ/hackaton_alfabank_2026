"""Routes for engine tests, built in code (the BPMN files come in #25)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from itertools import count
from typing import Any
from uuid import UUID

from src.modules.process.domain.conditions import Condition
from src.modules.process.domain.context import CONDITION_FIELDS, ProcessContext
from src.modules.process.domain.steps import (
    CollateralFact,
    CompletenessFact,
    EnrichmentRequestFact,
)
from src.modules.process.domain.workflow import (
    Edge,
    Node,
    NodeConfig,
    NodeType,
    OnFailure,
    WorkflowDefinition,
)

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
APPLICATION_ID = UUID("00000000-0000-0000-0000-0000000000a1")
ORGANIZATION_ID = UUID("00000000-0000-0000-0000-0000000000b1")


class RouteBuilder:
    def __init__(self, code: str = "test_v1") -> None:
        self.code = code
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []

    def node(
        self, node_id: str, kind: NodeType, step: str | None = None, **config: Any
    ) -> "RouteBuilder":
        self.nodes[node_id] = Node(node_id, kind, node_id, step, NodeConfig(**config))
        return self

    def start(self, node_id: str = "start") -> "RouteBuilder":
        return self.node(node_id, NodeType.START)

    def end(self, node_id: str) -> "RouteBuilder":
        return self.node(node_id, NodeType.END)

    def task(self, node_id: str, step: str | None = None, **config: Any) -> "RouteBuilder":
        return self.node(node_id, NodeType.TASK, step or node_id, **config)

    def user(self, node_id: str, step: str | None = None, **config: Any) -> "RouteBuilder":
        return self.node(node_id, NodeType.USER_TASK, step or node_id, **config)

    def gateway(self, node_id: str) -> "RouteBuilder":
        return self.node(node_id, NodeType.GATEWAY)

    def flow(
        self, source: str, target: str, when: str | None = None, default: bool = False
    ) -> "RouteBuilder":
        condition = Condition(when, CONDITION_FIELDS) if when else None
        self.edges.append(Edge(f"f{len(self.edges) + 1}", source, target, condition, default))
        return self

    def chain(self, *node_ids: str) -> "RouteBuilder":
        for source, target in zip(node_ids, node_ids[1:], strict=False):
            self.flow(source, target)
        return self

    def build(self) -> WorkflowDefinition:
        return WorkflowDefinition(self.code, 1, dict(self.nodes), tuple(self.edges))


def express(enrichment_failure: OnFailure = OnFailure.MANUAL_REVIEW) -> WorkflowDefinition:
    """Like express_v1: automatic decision, info requests, underwriter on demand."""
    b = RouteBuilder("express_v1")
    b.start().task("start_review").task("check_completeness").gateway("gw_complete")
    b.task("fetch_enrichment", max_iterations=3, on_failure=enrichment_failure)
    b.task("calculate_score", max_iterations=3, on_failure=OnFailure.MANUAL_REVIEW)
    b.task("make_decision", max_iterations=3).gateway("gw_outcome")
    b.task("request_info", max_iterations=2, timeout_seconds=3600)
    b.user("wait_client_info", max_iterations=2)
    b.user("underwriter_review", max_iterations=3, candidate_role="underwriter")
    b.task("record_manual_decision", max_iterations=3)
    b.task("present_offer").user("wait_offer_answer").gateway("gw_answer")
    b.user("wait_signature").task("disburse").task("reject")
    b.end("disbursed").end("rejected").end("closed")

    b.chain("start", "start_review", "check_completeness", "gw_complete")
    b.flow("gw_complete", "request_info", when="complete == false")
    b.flow("gw_complete", "fetch_enrichment", default=True)
    b.chain("fetch_enrichment", "calculate_score", "make_decision", "gw_outcome")
    b.flow("gw_outcome", "present_offer", when='outcome in ["APPROVE", "COUNTER_OFFER"]')
    b.flow("gw_outcome", "request_info", when='outcome == "REQUEST_INFO"')
    b.flow("gw_outcome", "underwriter_review", when='outcome == "MANUAL_REVIEW"')
    b.flow("gw_outcome", "reject", default=True)
    b.chain("request_info", "wait_client_info", "fetch_enrichment")
    b.chain("underwriter_review", "record_manual_decision", "gw_outcome")
    b.chain("present_offer", "wait_offer_answer", "gw_answer")
    b.flow("gw_answer", "wait_signature", when='offer_answer == "accepted"')
    b.flow("gw_answer", "closed", default=True)
    b.chain("wait_signature", "disburse", "disbursed")
    b.chain("reject", "rejected")
    return b.build()


def secured() -> WorkflowDefinition:
    """start -> assess_collateral -> end: for the collateral step alone."""
    b = RouteBuilder("secured_part")
    b.start().task("assess_collateral").end("done").chain("start", "assess_collateral", "done")
    return b.build()


class FakeFacts:
    def __init__(self) -> None:
        self.completeness_fact = CompletenessFact(True, (), ())
        self.collateral_fact: CollateralFact | None = None

    async def completeness(self, application_id: UUID) -> CompletenessFact:
        return self.completeness_fact

    async def enrichment_request(self, application_id: UUID) -> EnrichmentRequestFact:
        return EnrichmentRequestFact("7701158817", NOW, (UUID(int=7),))

    async def collateral(self, application_id: UUID) -> CollateralFact | None:
        return self.collateral_fact


def context() -> ProcessContext:
    return ProcessContext(
        application_id=APPLICATION_ID, organization_id=ORGANIZATION_ID, product_code="UNSECURED"
    )


def ids() -> Iterator[UUID]:
    return (UUID(int=n) for n in count(1000))


def offer() -> dict[str, Any]:
    return {
        "kind": "as_requested",
        "amount": Decimal("3000000"),
        "term_months": 24,
        "rate": Decimal("23.5"),
        "monthly_payment": Decimal("158000"),
        "schedule_type": "annuity",
        "conditions": [],
        "expires_at": NOW,
    }
