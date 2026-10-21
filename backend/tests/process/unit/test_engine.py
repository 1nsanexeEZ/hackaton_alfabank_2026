"""The engine on the express-like route with fake facts: success, duplicates,
late replies of an earlier iteration, loop limits, the underwriter, failures,
cancellation."""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from src.process.domain.events import (
    ProcessCompleted,
    ProcessFailed,
    ProcessStarted,
    StepCompleted,
    UserTaskCreated,
)
from src.process.domain.process import OutgoingCommand, ProcessInstance, ProcessStatus, WaitKind
from src.process.domain.steps import CollateralFact, CompletenessFact, Trigger
from src.process.domain.tasks import UserTask
from src.process.domain.workflow import OnFailure, WorkflowDefinition
from tests.process.unit.routes import NOW, FakeFacts, context, express, ids, offer, secured


class Driver:
    def __init__(self, workflow: WorkflowDefinition | None = None) -> None:
        self.facts = FakeFacts()
        self.ids = ids()
        self.now = NOW
        self.process = ProcessInstance.start(
            id=uuid4(), workflow=workflow or express(), context=context(), now=NOW
        )
        self.commands: list[OutgoingCommand] = []
        self.events: list[Any] = []
        self.tasks: list[UserTask] = []

    def _collect(self) -> None:
        self.commands += self.process.pull_commands()
        self.events += self.process.pull_events()
        self.tasks += self.process.pull_new_tasks()

    def new_id(self) -> UUID:
        return next(self.ids)

    async def run(self) -> "Driver":
        await self.process.run(self.facts, self.now, self.new_id)
        self._collect()
        return self

    async def send(self, trigger: Trigger) -> bool:
        handled = await self.process.handle(trigger, self.facts, self.now, self.new_id)
        self._collect()
        return handled

    def last_command(self, command_type: str) -> OutgoingCommand:
        return [c for c in self.commands if c.request.type == command_type][-1]

    async def reply(self, reply_type: str, to: str, **payload: Any) -> bool:
        command = self.last_command(to)
        return await self.send(Trigger(reply_type, payload, causation_id=command.command_id))

    async def enrichment_ok(self) -> bool:
        return await self.reply(
            "EnrichmentCompleted",
            "FetchEnrichment",
            snapshot_id=uuid4(),
            sources_failed=["bki"],
            cash_gap_detected=True,
        )

    async def score(self, grade: str = "A") -> bool:
        return await self.reply(
            "ScoreCalculated", "CalculateScore", result_id=uuid4(), risk_grade=grade, flags=[]
        )

    async def decide(self, outcome: str, to: str = "MakeDecision", **extra: Any) -> bool:
        payload = {
            "decision_id": uuid4(),
            "outcome": outcome,
            "decided_by": "auto",
            "client_explanation": "Пояснение",
            "improvement_hints": [],
            **extra,
        }
        return await self.reply("DecisionMade", to, **payload)

    def command_types(self) -> list[str]:
        return [c.request.type for c in self.commands]

    def stages(self) -> list[str]:
        return [
            e.client_stage for e in self.events if isinstance(e, StepCompleted) and e.client_stage
        ]


async def test_happy_path_to_disbursement() -> None:
    d = await Driver().run()
    assert d.command_types() == ["StartReview", "FetchEnrichment"]
    assert d.process.status is ProcessStatus.WAITING
    assert d.process.waiting.kind is WaitKind.COMMAND_REPLY  # type: ignore[union-attr]
    assert d.last_command("FetchEnrichment").request.payload["inn"] == "7701158817"

    assert await d.enrichment_ok()
    assert d.process.context.sources_failed == ("bki",) and d.process.context.cash_gap_flag
    assert await d.score("B")
    assert await d.decide("APPROVE", offer=offer())
    assert d.command_types()[-1] == "PresentOffer"
    assert d.last_command("PresentOffer").request.payload["offer"]["amount"] == Decimal("3000000")
    assert d.process.waiting.kind is WaitKind.CLIENT_EVENT  # type: ignore[union-attr]

    assert await d.send(Trigger("OfferAccepted"))
    assert await d.send(Trigger("ApplicationSigned"))
    assert d.process.status is ProcessStatus.COMPLETED
    assert d.command_types() == [
        "StartReview",
        "FetchEnrichment",
        "CalculateScore",
        "MakeDecision",
        "PresentOffer",
        "MarkDisbursed",
    ]
    assert isinstance(d.events[0], ProcessStarted)
    assert isinstance(d.events[-1], ProcessCompleted) and d.events[-1].outcome == "disbursed"
    assert d.stages() == [
        "Проверяем данные о компании",
        "Оцениваем заявку",
        "Подбираем условия",
        "Решение готово",
        "Подписание (смоделировано)",
        "Деньги отправлены (смоделировано, АБС — мок)",
    ]
    assert [s.step_code for s in d.process.steps if s.outcome == "completed"][:3] == [
        "start_review",
        "check_completeness",
        "fetch_enrichment",
    ]


async def test_duplicate_and_foreign_replies_are_ignored() -> None:
    d = await Driver().run()
    assert await d.enrichment_ok()
    # the same reply again (Kafka redelivery with a new event id) — not waited for anymore
    assert not await d.reply("EnrichmentCompleted", "FetchEnrichment", snapshot_id=uuid4())
    # a reply to a command we never sent
    assert not await d.send(Trigger("ScoreCalculated", {}, causation_id=uuid4()))
    # a client event the process does not wait for
    assert not await d.send(Trigger("OfferAccepted"))
    assert d.command_types()[-1] == "CalculateScore"


async def test_late_reply_of_an_earlier_iteration_is_ignored() -> None:
    d = await Driver().run()
    first_fetch = d.last_command("FetchEnrichment")
    await d.enrichment_ok()
    await d.score()
    await d.decide(
        "REQUEST_INFO",
        requested_info={"fields": [], "documents": ["bank_statement"], "comment": "Выписка"},
    )
    assert d.command_types()[-1] == "RequestInfo"
    assert d.last_command("RequestInfo").request.payload["requested_documents"] == [
        "bank_statement"
    ]
    assert d.process.context.info_requests_count == 1
    assert await d.send(Trigger("ApplicationInfoProvided"))
    second_fetch = d.last_command("FetchEnrichment")
    assert second_fetch.command_id != first_fetch.command_id

    stale = Trigger("EnrichmentCompleted", {"snapshot_id": uuid4()}, first_fetch.command_id)
    assert not await d.send(stale)
    assert await d.enrichment_ok()
    assert d.process.iterations["fetch_enrichment"] == 2


async def test_loop_limit_hands_over_to_the_underwriter() -> None:
    d = await Driver().run()
    for _ in range(2):
        await d.enrichment_ok()
        await d.score()
        await d.decide(
            "REQUEST_INFO", requested_info={"documents": ["bank_statement"], "comment": "Ещё"}
        )
        await d.send(Trigger("ApplicationInfoProvided"))
    await d.enrichment_ok()
    await d.score()
    await d.decide("REQUEST_INFO", requested_info={"documents": ["bank_statement"], "comment": "!"})

    # request_info may run twice only: the third time goes to a person
    assert d.process.current_node_id == "underwriter_review"
    assert "request_info repeated more than 2 times" in d.process.context.manual_review_reason  # type: ignore[operator]
    assert any(isinstance(e, UserTaskCreated) for e in d.events)


async def test_manual_review_round_trip() -> None:
    d = await Driver().run()
    await d.enrichment_ok()
    await d.score("D")
    await d.decide("MANUAL_REVIEW")
    [task] = d.tasks
    assert task.candidate_role == "underwriter" and task.due_at == NOW + timedelta(hours=8)
    assert d.process.waiting.task_id == task.id  # type: ignore[union-attr]
    assert d.stages()[-1] == "Заявка у специалиста"

    result = {
        "decision": "counter_offer",
        "amount": 2_000_000,
        "term_months": 24,
        "rate": 25,
        "comment": "Снижаем сумму по долговой нагрузке",
        "completed_by": str(uuid4()),
    }
    assert not await d.send(Trigger("UserTaskCompleted", result, task_id=uuid4()))
    assert await d.send(Trigger("UserTaskCompleted", result, task_id=task.id))
    command = d.last_command("RecordManualDecision").request.payload
    assert command["task_id"] == task.id
    assert command["outcome"] == "COUNTER_OFFER"
    assert command["terms"]["amount"] == 2_000_000

    await d.decide("COUNTER_OFFER", offer=offer(), to="RecordManualDecision")
    assert d.command_types()[-1] == "PresentOffer"


async def test_rejected_manual_decision_goes_back_to_review() -> None:
    d = await Driver().run()
    await d.enrichment_ok()
    await d.score()
    await d.decide("MANUAL_REVIEW")
    result = {
        "decision": "approve",
        "amount": 9e7,
        "term_months": 24,
        "rate": 20,
        "comment": "ok",
        "completed_by": "x",
    }
    await d.send(Trigger("UserTaskCompleted", result, task_id=d.tasks[-1].id))
    assert await d.reply("ManualDecisionRejected", "RecordManualDecision", reason="limit 50 mln")
    assert len(d.tasks) == 2
    assert d.process.context.manual_review_reason == "manual decision rejected: limit 50 mln"


async def test_rejection() -> None:
    d = await Driver().run()
    await d.enrichment_ok()
    await d.score("E")
    await d.decide("REJECT", client_explanation="Компания ликвидируется")
    assert d.command_types()[-1] == "RejectApplication"
    assert d.last_command("RejectApplication").request.payload["client_explanation"] == (
        "Компания ликвидируется"
    )
    assert d.process.status is ProcessStatus.COMPLETED
    assert d.events[-1].outcome == "rejected"


async def test_declined_offer_closes_the_process() -> None:
    d = await Driver().run()
    await d.enrichment_ok()
    await d.score()
    await d.decide("APPROVE", offer=offer())
    await d.send(Trigger("OfferExpired"))
    assert d.process.status is ProcessStatus.COMPLETED
    assert d.events[-1].outcome == "closed"
    assert "MarkDisbursed" not in d.command_types()


async def test_failed_enrichment_goes_to_manual_review() -> None:
    d = await Driver().run()
    assert await d.reply("EnrichmentFailed", "FetchEnrichment", reason="all sources down")
    assert d.process.current_node_id == "underwriter_review"
    assert d.process.context.manual_review_reason == "enrichment: all sources down"
    failed = [s for s in d.process.steps if s.outcome == "failed"]
    assert [s.step_code for s in failed] == ["fetch_enrichment"]


async def test_failed_enrichment_can_fail_the_process() -> None:
    d = await Driver(express(enrichment_failure=OnFailure.FAIL)).run()
    await d.reply("EnrichmentFailed", "FetchEnrichment", reason="down")
    assert d.process.status is ProcessStatus.FAILED
    assert isinstance(d.events[-1], ProcessFailed) and d.events[-1].reason == "enrichment: down"
    assert not await d.send(Trigger("ScoreCalculated", {}, causation_id=uuid4()))


async def test_incomplete_application_asks_for_data() -> None:
    d = Driver()
    d.facts.completeness_fact = CompletenessFact(False, ("request.amount",), ("bank_statement",))
    await d.run()
    request = d.last_command("RequestInfo").request.payload
    assert request["requested_fields"] == ["request.amount"]
    assert request["requested_documents"] == ["bank_statement"]
    assert request["due_at"] == NOW + timedelta(hours=1)  # node timeout
    assert d.process.current_node_id == "wait_client_info"


async def test_cancel_while_waiting() -> None:
    d = await Driver().run()
    assert d.process.cancel(NOW)
    assert d.process.status is ProcessStatus.CANCELLED
    [cancelled] = d.process.pull_events()
    assert isinstance(cancelled, ProcessCompleted) and cancelled.outcome == "CANCELLED"
    assert d.process.steps[-1].outcome == "cancelled"
    assert not await d.enrichment_ok()
    assert not d.process.cancel(NOW)


async def test_collateral_is_discounted() -> None:
    d = Driver(secured())
    d.facts.collateral_fact = CollateralFact("equipment", Decimal("1000000"))
    await d.run()
    assert d.process.context.collateral_value == Decimal("400000.00")
    no_collateral = await Driver(secured()).run()
    assert no_collateral.process.context.collateral_value == Decimal("0")
