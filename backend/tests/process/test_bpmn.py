"""Route files: every one loads, passes the validator and can be walked to the
end; broken or hostile files are rejected with a clear message."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from seed.products import catalog as product_catalog
from src.modules.process.domain.enums import ProcessStatus
from src.modules.process.domain.process import ProcessInstance
from src.modules.process.domain.steps import CollateralFact, Trigger
from src.modules.process.infrastructure.adapters.workflow_catalog import (
    WORKFLOWS_DIR,
    WorkflowLoadError,
    load_workflows,
)
from src.modules.process.infrastructure.bpmn import BpmnError, parse_bpmn, parse_duration
from tests.process.unit.routes import NOW, FakeFacts, context, ids, offer

ROUTES = ("express", "mortgage", "secured", "standard", "startup")
CODES = [f"{route}_v{version}" for route in ROUTES for version in (1, 2)]
# v2: стоп-факторы отдельным шагом после обогащения, до скоринга.
CODES_V2 = [code for code in CODES if code.endswith("_v2")]


def test_all_routes_load() -> None:
    catalog = load_workflows()
    assert catalog.codes() == CODES
    for workflow in catalog.all():
        assert workflow.file_name == f"{workflow.definition.code}.bpmn"
        assert len(workflow.definition.source_hash) == 64
        assert workflow.source.startswith(b"<?xml")
        assert b"BPMNDiagram" in workflow.source  # drawable by bpmn-js


def test_every_product_has_its_route() -> None:
    routes = set(load_workflows().codes())
    used = {product.processing.workflow_code for product in product_catalog()}
    assert used <= routes, used - routes


def test_routes_are_loaded_on_startup(client: TestClient) -> None:
    assert client.app.state.workflows.codes() == CODES  # type: ignore[attr-defined]


async def walk(
    code: str, outcome: str, stop: str | None = None
) -> tuple[ProcessInstance, list[str]]:
    """Walk a route with automatic replies; returns the process and its commands.
    `stop` — the outcome of a stop factor (v2 routes): the decision comes before scoring."""
    facts = FakeFacts()
    facts.collateral_fact = CollateralFact("real_estate", 50_000_000)  # type: ignore[arg-type]
    new_ids = ids()
    process = ProcessInstance.start(
        id=uuid4(), workflow=load_workflows().get(code), context=context(), now=NOW
    )
    sent: list = []

    async def step(trigger: Trigger | None = None) -> None:
        if trigger is None:
            await process.run(facts, NOW, lambda: next(new_ids))
        else:
            assert await process.handle(trigger, facts, NOW, lambda: next(new_ids)), trigger
        sent.extend(process.pull_commands())

    def last(command_type: str):  # type: ignore[no-untyped-def]
        return [c for c in sent if c.request.type == command_type][-1].command_id

    decision = {
        "decision_id": uuid4(),
        "outcome": outcome,
        "offer": offer(),
        "client_explanation": "ok",
        "improvement_hints": [],
    }
    await step()
    await step(Trigger("EnrichmentCompleted", {"snapshot_id": uuid4()}, last("FetchEnrichment")))
    if any(c.request.type == "CheckStopFactors" for c in sent):
        reply = (
            Trigger("StopFactorsPassed", {}, last("CheckStopFactors"))
            if stop is None
            else Trigger("DecisionMade", {**decision, "outcome": stop}, last("CheckStopFactors"))
        )
        await step(reply)
    if stop is None:
        await step(
            Trigger(
                "ScoreCalculated",
                {"result_id": uuid4(), "risk_grade": "A"},
                last("CalculateScore"),
            )
        )
        await step(Trigger("DecisionMade", decision, last("MakeDecision")))
    if process.waiting is not None and process.waiting.task_id is not None:
        task_id = process.waiting.task_id
        result = {
            "decision": "approve",
            "amount": 30_000_000,
            "term_months": 120,
            "rate": 18,
            "comment": "Залог покрывает сумму",
            "completed_by": str(uuid4()),
        }
        await step(Trigger("UserTaskCompleted", result, task_id=task_id))
        await step(
            Trigger(
                "DecisionMade",
                {**decision, "decided_by": "underwriter"},
                last("RecordManualDecision"),
            )
        )
    if process.status is ProcessStatus.WAITING:
        await step(Trigger("OfferAccepted"))
        await step(Trigger("ApplicationSigned"))
    return process, [c.request.type for c in sent]


@pytest.mark.parametrize("code", CODES)
async def test_route_reaches_disbursement(code: str) -> None:
    process, commands = await walk(code, "APPROVE")
    assert process.status is ProcessStatus.COMPLETED, process.current_node_id
    assert commands[0] == "StartReview" and commands[-1] == "MarkDisbursed"
    has_collateral_step = "assess_collateral" in process.iterations
    assert has_collateral_step == code.startswith(("secured", "mortgage"))
    if code.startswith("secured"):
        assert process.context.collateral_value == 25_000_000
    stop_step = "check_stop_factors" in process.iterations
    assert stop_step == (code in CODES_V2)
    if stop_step:
        assert process.context.stopped is False
        assert commands.index("CheckStopFactors") < commands.index("CalculateScore")


async def test_mortgage_always_goes_to_the_underwriter() -> None:
    _, commands = await walk("mortgage_v1", "APPROVE")
    assert "RecordManualDecision" in commands
    _, express_commands = await walk("express_v1", "APPROVE")
    assert "RecordManualDecision" not in express_commands


@pytest.mark.parametrize("code", CODES)
async def test_route_rejects(code: str) -> None:
    process, commands = await walk(code, "REJECT")
    assert commands[-1] == "RejectApplication"
    assert process.status is ProcessStatus.COMPLETED


@pytest.mark.parametrize("code", CODES_V2)
async def test_stop_factor_rejects_without_scoring(code: str) -> None:
    process, commands = await walk(code, "APPROVE", stop="REJECT")
    assert "CalculateScore" not in commands and "MakeDecision" not in commands
    assert commands[-1] == "RejectApplication"
    assert process.status is ProcessStatus.COMPLETED
    assert process.context.stopped is True and process.context.outcome == "REJECT"
    assert "assess_collateral" not in process.iterations


@pytest.mark.parametrize("code", CODES_V2)
async def test_stop_factor_without_consent_goes_to_a_person(code: str) -> None:
    """ст. 16 152-ФЗ: отказ ИП без согласия на автоматизированное решение готовит человек."""
    process, commands = await walk(code, "APPROVE", stop="MANUAL_REVIEW")
    assert "CalculateScore" not in commands
    assert "RecordManualDecision" in commands and commands[-1] == "MarkDisbursed"
    assert process.status is ProcessStatus.COMPLETED


# --- hostile and broken files -----------------------------------------------------

EXPRESS = (WORKFLOWS_DIR / "express_v1.bpmn").read_bytes()


def mutate(old: bytes, new: bytes) -> bytes:
    assert old in EXPRESS
    return EXPRESS.replace(old, new, 1)


@pytest.mark.parametrize(
    "content",
    [
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]><d>&x;</d>',
        b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><l>&b;</l>',
        b"<?xml version='1.0'?><!doctype x SYSTEM 'http://evil.test/x.dtd'><x/>",
    ],
    ids=["xxe-file", "billion-laughs", "external-dtd"],
)
def test_doctype_is_rejected(content: bytes) -> None:
    with pytest.raises(BpmnError, match="DOCTYPE"):
        parse_bpmn(content)


@pytest.mark.parametrize(
    "content,message",
    [
        (b"<not xml", "Not a valid XML"),
        (b"<root/>", "bpmn:definitions"),
        (
            mutate(b"</bpmn:process>", b'<bpmn:parallelGateway id="fork"/></bpmn:process>'),
            "Unsupported element bpmn:parallelGateway",
        ),
        (
            mutate(b'name="step" value="disburse"', b'name="script" value="rm -rf /"'),
            "unknown property",
        ),
        (
            mutate(b'name="step" value="disburse"', b'name="step" value="launch_rockets"'),
            "unknown step",
        ),
        (
            mutate(b"complete == false", b"__import__(&quot;os&quot;).system(&quot;id&quot;)"),
            "flow Flow_gw_complete_request_info",
        ),
        (mutate(b'value="P5D"', b'value="five days"'), "Invalid duration"),
        (mutate(b'id="express_v1"', b'id="Express V1"'), "Process id"),
    ],
    ids=[
        "garbage",
        "not-bpmn",
        "unsupported-element",
        "unknown-property",
        "unknown-step",
        "condition-injection",
        "bad-duration",
        "bad-id",
    ],
)
def test_broken_files_are_rejected(content: bytes, message: str) -> None:
    with pytest.raises((BpmnError, ValueError), match=message):
        parse_bpmn(content)


def test_validation_problems_name_the_file(tmp_path: Path) -> None:
    broken = EXPRESS.replace(b' default="Flow_gw_answer_end_closed"', b"", 1)
    (tmp_path / "express_v1.bpmn").write_bytes(broken)
    (tmp_path / "other.bpmn").write_bytes(EXPRESS)
    with pytest.raises(WorkflowLoadError) as error:
        load_workflows(tmp_path)
    text = str(error.value)
    assert "express_v1.bpmn" in text and "gateway gw_answer needs exactly one default flow" in text
    assert "other.bpmn: process id 'express_v1' must match the file name" in text


def test_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(WorkflowLoadError, match="No .bpmn"):
        load_workflows(tmp_path)


@pytest.mark.parametrize(
    "value,seconds",
    [("3600", 3600), ("PT8H", 28800), ("P5D", 432000), ("P1DT2H30M", 95400), ("PT45S", 45)],
)
def test_durations(value: str, seconds: int) -> None:
    assert parse_duration(value) == seconds


@pytest.mark.parametrize("value", ["P", "PT", "5 days", "P-1D", "PT1.5H"])
def test_bad_durations(value: str) -> None:
    with pytest.raises(BpmnError):
        parse_duration(value)
