"""Applications go through the route via the message bus."""

from datetime import timedelta

from src.modules.process.presentation.timeouts import time_out_stuck_steps
from tests.applications.api.conftest import PASSWORD
from tests.process.api.conftest import Pipeline


def test_application_goes_from_submission_to_payout(pipeline: Pipeline) -> None:
    p, world = pipeline, pipeline.world
    p.responders.decisions.append("APPROVE")
    application_id = p.submit()

    card = p.card(application_id)
    assert card["status"] == "offer_ready"
    assert card["offer"]["amount"] == "3000000.00"
    assert card["client_stage"] == "Решение готово"
    assert p.responders.received == ["FetchEnrichment", "CalculateScore", "MakeDecision"]
    process = p.process(application_id)
    assert process["status"] == "waiting" and process["current_node_id"] == "wait_offer_answer"

    headers = world.headers(world.director)
    world.client.post(f"/applications/{application_id}/offer/accept", headers=headers)
    p.drain()
    assert p.process(application_id)["current_node_id"] == "wait_signature"

    contract = world.client.get(f"/applications/{application_id}/contract", headers=headers)
    signed = world.client.post(
        f"/applications/{application_id}/sign",
        json={"password": PASSWORD, "offer_hash": contract.json()["offer_hash"]},
        headers=headers,
    )
    assert signed.status_code == 200
    p.drain()

    card = p.card(application_id)
    assert card["status"] == "disbursed"
    assert card["disbursement"]["simulated"] is True
    process = p.process(application_id)
    assert process["status"] == "completed" and process["current_node_id"] is None
    assert process["visited_node_ids"][:3] == [
        "start_review",
        "check_completeness",
        "fetch_enrichment",
    ]
    assert process["visited_node_ids"][-1] == "disburse"
    assert p.dead_letters == []


def test_underwriter_decides(pipeline: Pipeline) -> None:
    p, client = pipeline, pipeline.world.client
    p.responders.decisions.append("MANUAL_REVIEW")
    application_id = p.submit()
    assert p.card(application_id)["status"] == "in_review"
    assert p.card(application_id)["client_stage"] == "Заявка у специалиста"

    queue = client.get("/tasks", headers=p.underwriter()).json()
    [task] = queue
    assert task["application_id"] == application_id
    assert task["status"] == "open" and task["overdue"] is False
    assert task["form_schema"]["required"] == ["decision", "comment"]

    detail = client.get(f"/tasks/{task['id']}", headers=p.underwriter()).json()
    assert detail["process"]["current_node_id"] == "underwriter_review"

    no_claim = client.post(
        f"/tasks/{task['id']}/complete",
        json={"decision": "reject", "comment": "нет"},
        headers=p.underwriter(),
    )
    assert no_claim.status_code == 409  # take the task first

    claimed = client.post(f"/tasks/{task['id']}/claim", headers=p.underwriter())
    assert claimed.json()["status"] == "in_progress"

    no_comment = client.post(
        f"/tasks/{task['id']}/complete",
        json={"decision": "counter_offer", "amount": "2000000", "term_months": 24, "rate": "25"},
        headers=p.underwriter(),
    )
    assert no_comment.status_code == 422

    done = client.post(
        f"/tasks/{task['id']}/complete",
        json={
            "decision": "counter_offer",
            "amount": "2000000",
            "term_months": 24,
            "rate": "25",
            "comment": "Снижаем сумму: высокая долговая нагрузка",
        },
        headers=p.underwriter(),
    )
    assert done.status_code == 200, done.text
    p.drain()

    card = p.card(application_id)
    assert card["status"] == "offer_ready"
    assert card["offer"]["kind"] == "counter" and card["offer"]["amount"] == "2000000.00"
    assert "RecordManualDecision" in p.responders.received
    assert client.get("/tasks", headers=p.underwriter()).json() == []


def test_information_request_and_second_round(pipeline: Pipeline) -> None:
    p, world = pipeline, pipeline.world
    p.responders.decisions.extend(["REQUEST_INFO", "APPROVE"])
    application_id = p.submit()

    card = p.card(application_id)
    assert card["status"] == "info_requested"
    [request] = card["info_requests"]
    assert request["requested_documents"] == ["financial_statement"]

    world.upload(card, "financial_statement", content=b"%PDF-1.7", content_type="application/pdf")
    answered = world.client.post(
        f"/applications/{application_id}/info-requests/{request['id']}/answer",
        headers=world.headers(world.director),
    )
    assert answered.status_code == 200
    p.drain()

    assert p.card(application_id)["status"] == "offer_ready"
    assert p.responders.received.count("FetchEnrichment") == 2
    process = p.process(application_id)
    iterations = [s for s in process["steps"] if s["step_code"] == "fetch_enrichment"]
    assert [s["iteration"] for s in iterations] == [1, 2]


def test_cancel_stops_the_process(pipeline: Pipeline) -> None:
    p, world = pipeline, pipeline.world
    application = world.submit(world.ready())
    # cancelled before the bank picked it up
    world.client.post(
        f"/applications/{application['id']}/cancel", headers=world.headers(world.director)
    )
    p.drain()
    assert p.card(application["id"])["status"] == "cancelled"
    assert p.process(application["id"])["status"] == "cancelled"
    assert p.dead_letters == []


def test_repeated_delivery_changes_nothing(pipeline: Pipeline) -> None:
    p = pipeline
    p.responders.decisions.append("APPROVE")
    application_id = p.submit()
    before = p.process(application_id)
    p.drain()
    p.drain()
    assert p.process(application_id) == before


def test_silent_module_hands_over_to_the_underwriter(pipeline: Pipeline) -> None:
    p, world = pipeline, pipeline.world
    p.responders.hold.add("enrichment")
    application_id = p.submit()
    assert p.process(application_id)["current_node_id"] == "fetch_enrichment"

    app = world.client.app
    args = (app.state.session_factory, app.state.facades, world.clock)  # type: ignore[attr-defined]
    assert world.run(time_out_stuck_steps, *args) == 0  # not yet
    world.clock.advance(timedelta(minutes=6))
    assert world.run(time_out_stuck_steps, *args) == 1
    p.drain()

    process = p.process(application_id)
    assert process["current_node_id"] == "underwriter_review"
    failed = [s for s in process["steps"] if s["outcome"] == "failed"]
    assert failed[0]["error"] == "fetch_enrichment: no reply in 300 s"
    assert len(world.client.get("/tasks", headers=p.underwriter()).json()) == 1


def test_workflows_api(pipeline: Pipeline) -> None:
    client = pipeline.world.client
    workflows = client.get("/workflows", headers=pipeline.underwriter()).json()
    assert [w["code"] for w in workflows] == [
        "express_v1",
        "mortgage_v1",
        "secured_v1",
        "standard_v1",
        "startup_v1",
    ]
    diagram = client.get("/workflows/express_v1/diagram", headers=pipeline.underwriter())
    assert diagram.headers["content-type"].startswith("application/xml")
    assert b"bpmndi:BPMNDiagram" in diagram.content
    assert client.get("/workflows/nope/diagram", headers=pipeline.underwriter()).status_code == 404
    client_token = pipeline.world.headers(pipeline.world.director)
    assert client.get("/workflows", headers=client_token).status_code == 403


def test_facade_and_competing_underwriters(pipeline: Pipeline) -> None:
    from uuid import UUID, uuid4

    from src.core.access.permissions import Permissions
    from src.modules.process.facade import ProcessFacade
    from tests.helpers import bearer, token_for

    p, client = pipeline, pipeline.world.client
    p.responders.decisions.append("MANUAL_REVIEW")
    application_id = p.submit()
    app = client.app

    async def read() -> tuple:
        async with app.state.session_factory() as session:  # type: ignore[attr-defined]
            facade = app.state.facades.get(ProcessFacade, session)  # type: ignore[attr-defined]
            view = await facade.get_process_view(UUID(application_id))
            tasks = await facade.list_open_tasks("underwriter")
            return view, tasks

    view, tasks = p.world.run(read)
    assert view.workflow_code == "express_v1" and view.status == "waiting"
    assert view.client_stage == "Заявка у специалиста"
    [task] = tasks
    assert task.application_id == UUID(application_id)

    client.post(f"/tasks/{task.id}/claim", headers=p.underwriter())
    other = bearer(
        token_for(app, [Permissions.TASKS_READ, Permissions.TASKS_UPDATE], {}, uuid4())  # type: ignore[arg-type]
    )
    assert client.post(f"/tasks/{task.id}/claim", headers=other).status_code == 409
    result = {"decision": "reject", "comment": "Не моя задача"}
    assert client.post(f"/tasks/{task.id}/complete", json=result, headers=other).status_code == 403


def test_product_without_a_route_is_logged_not_retried(pipeline: Pipeline) -> None:
    from dataclasses import replace

    products = pipeline.world.products.products
    products["UNSECURED"] = replace(products["UNSECURED"], workflow_code="unknown_v9")
    application_id = pipeline.submit()
    assert pipeline.card(application_id)["status"] == "submitted"
    missing = pipeline.world.client.get(
        f"/processes/{application_id}", headers=pipeline.underwriter()
    )
    assert missing.status_code == 404
    assert pipeline.dead_letters == []
