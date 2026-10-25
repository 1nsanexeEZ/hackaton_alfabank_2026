"""The closed registry of steps a route may use (no imports by string).

A step has no business logic of its own: it says which command to send,
what to wait for and what to remember from the answer. Saving, the outbox
and moving along the graph are the engine's job.

- immediate — done right away (maybe sending a command without waiting);
- async     — sends a command and waits for the reply to exactly that command;
- stoppable — waits for a person: the client (an event) or a bank employee (a task).
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

from src.modules.process.domain.context import ProcessContext
from src.modules.process.domain.enums import StepKind
from src.modules.process.domain.workflow import Node


@dataclass(frozen=True, slots=True)
class CommandRequest:
    """A command to another module; the application layer turns it into a contract."""

    type: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_type: str
    candidate_role: str
    form_schema: Mapping[str, Any]
    due_at: datetime | None
    # Why the task is opened beyond the decision's own reasons, for the employee.
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Trigger:
    """Something the process may be waiting for: a reply to its command, a
    client event or a closed task."""

    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    causation_id: UUID | None = None
    task_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class StepResult:
    status: Literal["completed", "waiting", "failed"]
    updates: Mapping[str, Any] = field(default_factory=dict)
    commands: tuple[CommandRequest, ...] = ()
    expects: frozenset[str] = frozenset()
    task: TaskSpec | None = None
    error: str | None = None

    @classmethod
    def done(
        cls, updates: Mapping[str, Any] | None = None, *commands: CommandRequest
    ) -> "StepResult":
        return cls("completed", updates or {}, tuple(commands))

    @classmethod
    def send_and_wait(cls, command: CommandRequest, expects: set[str]) -> "StepResult":
        return cls("waiting", commands=(command,), expects=frozenset(expects))

    @classmethod
    def wait_for(cls, expects: set[str]) -> "StepResult":
        return cls("waiting", expects=frozenset(expects))

    @classmethod
    def create_task(cls, task: TaskSpec, updates: Mapping[str, Any] | None = None) -> "StepResult":
        return cls("waiting", updates or {}, task=task, expects=frozenset({"UserTaskCompleted"}))

    @classmethod
    def failed(cls, error: str) -> "StepResult":
        return cls("failed", error=error)


# --- facts the steps need from other modules (port) ----------------------------


@dataclass(frozen=True, slots=True)
class CompletenessFact:
    complete: bool
    missing_fields: tuple[str, ...]
    missing_documents: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PersonFact:
    account_id: UUID
    last_name: str
    first_name: str
    middle_name: str | None = None


@dataclass(frozen=True, slots=True)
class ThirdPartyFact:
    """The beneficiary or the pledgor from the application, screened under 115-FZ."""

    role: str  # beneficiary | pledgor
    kind: str  # person | organization
    name: str
    inn: str | None = None
    country: str | None = None  # ISO 3166-1 alpha-2, when not Russia


@dataclass(frozen=True, slots=True)
class DeclaredOwnerFact:
    """A beneficial owner as named by the client (115-FZ art. 6.1)."""

    name: str
    basis: str  # ownership | control
    country: str | None = None


@dataclass(frozen=True, slots=True)
class EnrichmentRequestFact:
    inn: str
    bki_consent_at: datetime | None
    statement_document_ids: tuple[UUID, ...]
    # The head by the registry and their own consent to request their credit history.
    head: PersonFact | None = None
    head_bki_consent_at: datetime | None = None
    # Who submitted the application, when not the head: a representative for the 115-FZ check.
    representative: PersonFact | None = None
    third_parties: tuple[ThirdPartyFact, ...] = ()
    # None — the client has not named its beneficial owners.
    declared_owners: tuple[DeclaredOwnerFact, ...] | None = None


@dataclass(frozen=True, slots=True)
class CollateralFact:
    type: str
    declared_value: Decimal


class ProcessFacts(Protocol):
    async def completeness(self, application_id: UUID) -> CompletenessFact: ...

    async def enrichment_request(self, application_id: UUID) -> EnrichmentRequestFact: ...

    async def collateral(self, application_id: UUID) -> CollateralFact | None: ...


@dataclass(frozen=True)
class StepInput:
    context: ProcessContext
    node: Node
    now: datetime
    facts: ProcessFacts


Run = Callable[[StepInput], Awaitable[StepResult]]
OnReply = Callable[[StepInput, Trigger], StepResult]


@dataclass(frozen=True)
class StepSpec:
    code: str
    kind: StepKind
    client_stage: str
    run: Run
    on_reply: OnReply | None = None


# What enrichment is asked for: registry, tax, company bureau, the bank statement forecast,
# accounting reports (GIR BO), courts and bailiffs (Kontur), the head's own bureau report and
# the 115-FZ check (beneficial owners, lists, PEP, KYC platform) — on every application, a
# repeat borrower included — and the bank's own stop list.
ENRICHMENT_SOURCES = (
    "egrul",
    "fns",
    "bki",
    "statement",
    "gir_bo",
    "kontur",
    "bki_head",
    "aml",
    "bank_stop_list",
    "bank_turnover",
)


def _ids(ctx: ProcessContext) -> dict[str, Any]:
    return {"application_id": ctx.application_id}


def _due(step: StepInput, default: timedelta) -> datetime:
    seconds = step.node.config.timeout_seconds
    return step.now + (timedelta(seconds=seconds) if seconds else default)


# --- steps ------------------------------------------------------------------------


async def _start_review(step: StepInput) -> StepResult:
    stage = step.node.config.client_stage or STEPS["start_review"].client_stage
    return StepResult.done(
        None, CommandRequest("StartReview", {**_ids(step.context), "client_stage": stage})
    )


async def _check_completeness(step: StepInput) -> StepResult:
    fact = await step.facts.completeness(step.context.application_id)
    return StepResult.done(
        {
            "complete": fact.complete,
            "missing_fields": fact.missing_fields,
            "missing_documents": fact.missing_documents,
        }
    )


async def _fetch_enrichment(step: StepInput) -> StepResult:
    fact = await step.facts.enrichment_request(step.context.application_id)
    return StepResult.send_and_wait(
        CommandRequest(
            "FetchEnrichment",
            {
                **_ids(step.context),
                "organization_id": step.context.organization_id,
                "inn": fact.inn,
                "sources": list(ENRICHMENT_SOURCES),
                "bki_consent_at": fact.bki_consent_at,
                "statement_document_ids": list(fact.statement_document_ids),
                "head": _person(fact.head),
                "head_bki_consent_at": fact.head_bki_consent_at,
                "representative": _person(fact.representative),
                "third_parties": [
                    {
                        "role": p.role,
                        "kind": p.kind,
                        "name": p.name,
                        "inn": p.inn,
                        "country": p.country,
                    }
                    for p in fact.third_parties
                ],
                "declared_owners": None
                if fact.declared_owners is None
                else [
                    {"name": o.name, "basis": o.basis, "country": o.country}
                    for o in fact.declared_owners
                ],
            },
        ),
        {"EnrichmentCompleted", "EnrichmentFailed"},
    )


def _person(person: PersonFact | None) -> dict[str, Any] | None:
    if person is None:
        return None
    return {
        "account_id": person.account_id,
        "last_name": person.last_name,
        "first_name": person.first_name,
        "middle_name": person.middle_name,
    }


def _enrichment_reply(step: StepInput, trigger: Trigger) -> StepResult:
    if trigger.type == "EnrichmentFailed":
        return StepResult.failed(f"enrichment: {trigger.payload.get('reason')}")
    return StepResult.done(
        {
            "enrichment_snapshot_id": trigger.payload["snapshot_id"],
            "sources_failed": tuple(trigger.payload.get("sources_failed", ())),
            "cash_gap_flag": trigger.payload.get("cash_gap_detected"),
        }
    )


# Share of the declared value the bank counts on (liquidity discount).
COLLATERAL_DISCOUNT: dict[str, Decimal] = {
    "real_estate": Decimal("0.5"),
    "vehicle": Decimal("0.5"),
    "equipment": Decimal("0.4"),
    "goods": Decimal("0.3"),
}


async def _assess_collateral(step: StepInput) -> StepResult:
    fact = await step.facts.collateral(step.context.application_id)
    if fact is None:
        return StepResult.done({"collateral_value": Decimal("0")})
    discount = COLLATERAL_DISCOUNT.get(fact.type, Decimal("0"))
    value = (fact.declared_value * discount).quantize(Decimal("0.01"))
    return StepResult.done({"collateral_value": value})


async def _check_stop_factors(step: StepInput) -> StepResult:
    return StepResult.send_and_wait(
        CommandRequest("CheckStopFactors", _ids(step.context)),
        {"StopFactorsPassed", "DecisionMade"},
    )


def _stop_reply(step: StepInput, trigger: Trigger) -> StepResult:
    """No stop factor — on to scoring; a stop factor — the decision is already made and the
    route goes to the outcome gateway without the scoring model."""
    if trigger.type == "StopFactorsPassed":
        return StepResult.done({"stopped": False})
    decided = _decision_reply(step, trigger)
    return StepResult.done({**decided.updates, "stopped": True})


async def _calculate_score(step: StepInput) -> StepResult:
    return StepResult.send_and_wait(
        CommandRequest("CalculateScore", _ids(step.context)),
        {"ScoreCalculated", "ScoringFailed"},
    )


def _score_reply(step: StepInput, trigger: Trigger) -> StepResult:
    if trigger.type == "ScoringFailed":
        return StepResult.failed(f"scoring: {trigger.payload.get('reason')}")
    return StepResult.done(
        {
            "scoring_result_id": trigger.payload["result_id"],
            "risk_grade": trigger.payload["risk_grade"],
            "score_flags": tuple(trigger.payload.get("flags", ())),
        }
    )


async def _make_decision(step: StepInput) -> StepResult:
    return StepResult.send_and_wait(
        CommandRequest("MakeDecision", _ids(step.context)), {"DecisionMade"}
    )


def _decision_reply(step: StepInput, trigger: Trigger) -> StepResult:
    if trigger.type == "ManualDecisionRejected":
        # The underwriter went beyond their authority or the product: back to review. The
        # reason is decision's text for the underwriter, the new task carries it.
        reason = trigger.payload.get("reason")
        return StepResult.done(
            {
                "outcome": "MANUAL_REVIEW",
                "manual_review_reason": f"Ручное решение не принято: {reason}",
            }
        )
    payload = trigger.payload
    return StepResult.done(
        {
            "decision_id": payload["decision_id"],
            "outcome": payload["outcome"],
            "decided_by": payload.get("decided_by"),
            "decision": {
                "decision_id": payload["decision_id"],
                "offer": payload.get("offer"),
                "requested_info": payload.get("requested_info"),
                "client_explanation": payload.get("client_explanation", ""),
                "improvement_hints": list(payload.get("improvement_hints", [])),
                "alternative_product_code": payload.get("alternative_product_code"),
            },
        }
    )


async def _request_info(step: StepInput) -> StepResult:
    ctx = step.context
    if ctx.complete is False:
        fields, documents = list(ctx.missing_fields), list(ctx.missing_documents)
        comment = "Заполните недостающие данные заявки"
    else:
        requested = (ctx.decision or {}).get("requested_info") or {}
        fields = list(requested.get("fields", []))
        documents = list(requested.get("documents", []))
        comment = requested.get("comment") or "Банку нужны дополнительные данные"
    if not fields and not documents:
        return StepResult.failed("request_info: nothing to ask for")
    return StepResult.done(
        {"info_requests_count": ctx.info_requests_count + 1, "info_provided": False},
        CommandRequest(
            "RequestInfo",
            {
                **_ids(ctx),
                "requested_fields": fields,
                "requested_documents": documents,
                "comment": comment,
                "due_at": _due(step, timedelta(days=5)),
            },
        ),
    )


async def _wait_client_info(step: StepInput) -> StepResult:
    return StepResult.wait_for({"ApplicationInfoProvided"})


def _info_reply(step: StepInput, trigger: Trigger) -> StepResult:
    # New data: whatever was learned before may be outdated.
    return StepResult.done({"info_provided": True, "complete": None})


UNDERWRITER_FORM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["approve", "counter_offer", "reject", "request_info"],
        },
        "amount": {"type": "number", "minimum": 1},
        "term_months": {"type": "integer", "minimum": 1},
        "rate": {"type": "number", "minimum": 0},
        "conditions": {"type": "array", "items": {"type": "string"}},
        "requested_documents": {"type": "array", "items": {"type": "string"}},
        "comment": {"type": "string", "minLength": 1, "maxLength": 2000},
    },
    "required": ["decision", "comment"],
}
# Project assessment of a startup (startup_v1): the decision fields plus the
# business plan, collateral and the state support program.
PROJECT_ASSESSMENT_FORM: dict[str, Any] = {
    "type": "object",
    "properties": {
        **UNDERWRITER_FORM["properties"],
        "business_plan": {
            "type": "string",
            "title": "Оценка бизнес-плана и финмодели",
            "enum": ["strong", "acceptable", "weak"],
        },
        "collateral": {"type": "string", "title": "Обеспечение", "maxLength": 500},
        "support_program": {"type": "boolean", "title": "Подходит под программу господдержки"},
    },
    "required": ["decision", "comment", "business_plan"],
}
_FORMS: dict[str, dict[str, Any]] = {
    "underwriter_review": UNDERWRITER_FORM,
    "project_assessment": PROJECT_ASSESSMENT_FORM,
}


async def _underwriter_review(step: StepInput) -> StepResult:
    form = step.node.config.form or "underwriter_review"
    return StepResult.create_task(
        TaskSpec(
            task_type=form,
            candidate_role=step.node.config.candidate_role or "underwriter",
            form_schema=_FORMS[form],
            due_at=_due(step, timedelta(hours=8)),
            reason=step.context.manual_review_reason,
        )
    )


def _review_reply(step: StepInput, trigger: Trigger) -> StepResult:
    return StepResult.done({"manual_result": dict(trigger.payload), "manual_review_reason": None})


_MANUAL_OUTCOMES = {
    "approve": "APPROVE",
    "counter_offer": "COUNTER_OFFER",
    "reject": "REJECT",
    "request_info": "REQUEST_INFO",
}


async def _record_manual_decision(step: StepInput) -> StepResult:
    ctx = step.context
    result = ctx.manual_result or {}
    if ctx.last_task_id is None or "decision" not in result:
        return StepResult.failed("record_manual_decision: no closed review task")
    terms = None
    if result.get("amount") is not None:
        terms = {
            "amount": result["amount"],
            "term_months": result["term_months"],
            "rate": result["rate"],
            "conditions": list(result.get("conditions", [])),
        }
    requested_info = None
    if result["decision"] == "request_info":
        requested_info = {
            "documents": list(result.get("requested_documents", [])),
            "comment": result["comment"],
        }
    return StepResult.send_and_wait(
        CommandRequest(
            "RecordManualDecision",
            {
                **_ids(ctx),
                "task_id": ctx.last_task_id,
                "underwriter_id": result["completed_by"],
                "outcome": _MANUAL_OUTCOMES[result["decision"]],
                "terms": terms,
                "requested_info": requested_info,
                "comment": result["comment"],
            },
        ),
        {"DecisionMade", "ManualDecisionRejected"},
    )


async def _present_offer(step: StepInput) -> StepResult:
    decision = step.context.decision or {}
    if not decision.get("offer"):
        return StepResult.failed("present_offer: the decision has no offer")
    return StepResult.done(
        None,
        CommandRequest(
            "PresentOffer",
            {
                **_ids(step.context),
                "decision_id": decision["decision_id"],
                "offer": decision["offer"],
                "client_explanation": decision["client_explanation"],
                "improvement_hints": decision["improvement_hints"],
                "alternative_product_code": decision["alternative_product_code"],
                "decided_by": step.context.decided_by,
            },
        ),
    )


async def _wait_offer_answer(step: StepInput) -> StepResult:
    return StepResult.wait_for({"OfferAccepted", "OfferDeclined", "OfferExpired"})


def _offer_reply(step: StepInput, trigger: Trigger) -> StepResult:
    answer = {"OfferAccepted": "accepted", "OfferDeclined": "declined", "OfferExpired": "expired"}
    return StepResult.done({"offer_answer": answer[trigger.type]})


async def _wait_signature(step: StepInput) -> StepResult:
    return StepResult.wait_for({"ApplicationSigned"})


def _signature_reply(step: StepInput, trigger: Trigger) -> StepResult:
    return StepResult.done({"signed": True})


async def _disburse(step: StepInput) -> StepResult:
    return StepResult.done(None, CommandRequest("MarkDisbursed", _ids(step.context)))


async def _reject(step: StepInput) -> StepResult:
    decision = step.context.decision or {}
    return StepResult.done(
        None,
        CommandRequest(
            "RejectApplication",
            {
                **_ids(step.context),
                "decision_id": decision.get("decision_id"),
                "client_explanation": decision.get("client_explanation")
                or "К сожалению, банк не может одобрить заявку",
                "improvement_hints": decision.get("improvement_hints", []),
                "alternative_product_code": decision.get("alternative_product_code"),
                "decided_by": step.context.decided_by,
            },
        ),
    )


_SPECS = [
    StepSpec("start_review", StepKind.IMMEDIATE, "Заявка принята", _start_review),
    StepSpec("check_completeness", StepKind.IMMEDIATE, "Проверяем заявку", _check_completeness),
    StepSpec(
        "fetch_enrichment",
        StepKind.ASYNC,
        "Проверяем данные о компании",
        _fetch_enrichment,
        _enrichment_reply,
    ),
    StepSpec(
        "check_stop_factors",
        StepKind.ASYNC,
        "Проверяем данные о компании",
        _check_stop_factors,
        _stop_reply,
    ),
    StepSpec("assess_collateral", StepKind.IMMEDIATE, "Оцениваем залог", _assess_collateral),
    StepSpec("calculate_score", StepKind.ASYNC, "Оцениваем заявку", _calculate_score, _score_reply),
    StepSpec("make_decision", StepKind.ASYNC, "Подбираем условия", _make_decision, _decision_reply),
    StepSpec("request_info", StepKind.IMMEDIATE, "Нужна информация от вас", _request_info),
    StepSpec(
        "wait_client_info",
        StepKind.STOPPABLE,
        "Нужна информация от вас",
        _wait_client_info,
        _info_reply,
    ),
    StepSpec(
        "underwriter_review",
        StepKind.STOPPABLE,
        "Заявка у специалиста",
        _underwriter_review,
        _review_reply,
    ),
    StepSpec(
        "record_manual_decision",
        StepKind.ASYNC,
        "Заявка у специалиста",
        _record_manual_decision,
        _decision_reply,
    ),
    StepSpec("present_offer", StepKind.IMMEDIATE, "Решение готово", _present_offer),
    StepSpec(
        "wait_offer_answer", StepKind.STOPPABLE, "Решение готово", _wait_offer_answer, _offer_reply
    ),
    StepSpec(
        "wait_signature",
        StepKind.STOPPABLE,
        "Подписание (смоделировано)",
        _wait_signature,
        _signature_reply,
    ),
    StepSpec(
        "disburse", StepKind.IMMEDIATE, "Деньги отправлены (смоделировано, АБС — мок)", _disburse
    ),
    StepSpec("reject", StepKind.IMMEDIATE, "Решение готово", _reject),
]

STEPS: dict[str, StepSpec] = {spec.code: spec for spec in _SPECS}
