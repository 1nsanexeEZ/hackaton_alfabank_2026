from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

from src.core.access.permissions import Permissions
from src.modules.products.facade import EligibilityCheckDTO, EligibilityReasonDTO
from src.modules.projector.facade import AmountBucketDTO, ApplicationGroupDTO, ApplicationStatsDTO
from src.modules.scoring.facade import MlScoreDTO
from tests.bff import factories
from tests.bff.conftest import World

# --- queue --------------------------------------------------------------------


def test_queue_in_one_call(world: World) -> None:
    card = world.add_application(status="in_review")
    world.projector.add_queue_item(factories.queue_item(card))
    world.projector.add_queue_item(factories.queue_item(card, status="done"))

    response = world.get("/bff/backoffice/queue", world.as_underwriter())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    [item] = body["items"]
    assert item["application_id"] == str(card.id)
    assert item["company_name"] == world.romashka.name
    assert item["score"] == 612
    assert item["cash_gap"] is True
    assert item["routing_reasons"] == ["Сумма выше лимита автоматического решения"]


def test_queue_by_status(world: World) -> None:
    card = world.add_application(status="in_review")
    world.projector.add_queue_item(factories.queue_item(card, status="done"))

    body = world.get("/bff/backoffice/queue", world.as_underwriter(), status="done").json()

    assert body["total"] == 1


def test_queue_by_review_kind(world: World) -> None:
    card = world.add_application(status="in_review")
    other = world.add_application(status="in_review")
    world.projector.add_queue_item(factories.queue_item(card, review="dispute"))
    world.projector.add_queue_item(factories.queue_item(other, review="check"))

    disputes = world.get("/bff/backoffice/queue", world.as_underwriter(), review="dispute").json()
    everything = world.get("/bff/backoffice/queue", world.as_underwriter()).json()
    wrong = world.get("/bff/backoffice/queue", world.as_underwriter(), review="other")

    assert disputes["total"] == 1 and disputes["items"][0]["review"] == "dispute"
    assert everything["total"] == 2
    assert wrong.status_code == 422


def test_queue_is_for_bank_staff(world: World) -> None:
    client = world.get("/bff/backoffice/queue", world.as_client(world.director))
    no_tasks = world.get(
        "/bff/backoffice/queue", world.as_underwriter(without=(Permissions.TASKS_READ,))
    )
    no_backoffice = world.get(
        "/bff/backoffice/queue", world.as_underwriter(without=(Permissions.BACKOFFICE_READ,))
    )

    assert client.status_code == 403
    assert no_tasks.status_code == 403
    assert no_backoffice.status_code == 403


# --- underwriter card -----------------------------------------------------------


def test_underwriter_card_has_everything(world: World) -> None:
    card = world.add_application(status="in_review", client_stage="Заявка у специалиста")
    world.enrichment.add_snapshot(factories.enrichment_snapshot(card.id, card.organization_id))
    world.scoring.add_result(factories.scoring_result(card.id))
    world.decision.add_decision(factories.decision(card.id, "MANUAL_REVIEW"))
    world.products.set_eligibility(
        EligibilityCheckDTO(
            "UNSECURED",
            card.organization_id,
            eligible=True,
            reasons=(EligibilityReasonDTO("business_age", True, "Бизнесу 3 года"),),
        )
    )
    world.projector.add_timeline_entry(factories.timeline_entry(card.id, "Заявка принята"))
    world.projector.add_timeline_entry(
        factories.timeline_entry(
            card.id, factories.BANK_TIMELINE_TITLE, "bank", "decision", 1, {"score": 612}
        )
    )
    world.process.add_view(factories.process_view(card.id))
    task = world.process.add_task(factories.user_task(card.id))
    world.process.add_task(factories.user_task(uuid4()))

    response = world.get(f"/bff/backoffice/applications/{card.id}", world.as_underwriter())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded"] == []
    assert body["application"]["id"] == str(card.id)
    assert body["application"]["org_snapshot"]["inn"] == world.romashka.inn
    assert body["client_status"] == "scoring"
    cashflow = body["enrichment"]["cashflow"]
    assert cashflow["gap_detected"] is True
    assert cashflow["forecast"] == [{"month": "2026-12", "projected_balance": "-80000"}]
    assert body["enrichment"]["bki"]["obligations"][0]["creditor"] == factories.BKI_CREDITOR
    assert body["scoring"]["score"] == 612
    assert body["scoring"]["factors"][0]["code"] == factories.FACTOR_CODE
    assert body["decision"]["reason_codes"] == [factories.REASON_CODE]
    assert body["decision"]["rule_trace"][0]["rule"] == factories.RULE_NAME
    assert body["product_fit"]["reasons"][0]["message"] == "Бизнесу 3 года"
    assert [e["audience"] for e in body["timeline"]] == ["client", "bank"]
    assert body["process"]["current_node_id"] == "underwriter_review"
    assert body["task"]["id"] == str(task.id)
    assert body["task"]["form_schema"]["required"] == ["outcome", "comment"]


def test_underwriter_card_of_an_unknown_application_is_404(world: World) -> None:
    response = world.get(f"/bff/backoffice/applications/{uuid4()}", world.as_underwriter())

    assert response.status_code == 404


def test_underwriter_card_is_for_bank_staff(world: World) -> None:
    card = world.add_application(status="in_review")
    path = f"/bff/backoffice/applications/{card.id}"

    client = world.get(path, world.as_client(world.director))
    no_decisions = world.get(path, world.as_underwriter(without=(Permissions.DECISIONS_READ,)))

    assert client.status_code == 403
    assert no_decisions.status_code == 403


# --- metrics --------------------------------------------------------------------


def test_metrics_for_a_period(world: World) -> None:
    world.projector.metrics = factories.metrics(date(2026, 10, 1), date(2026, 10, 21))

    response = world.get(
        "/bff/backoffice/metrics",
        world.as_underwriter(),
        date_from="2026-10-01",
        date_to="2026-10-21",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["auto_decision_share"] == 0.9
    assert body["rows"][0]["approved"] == 6


def test_metrics_default_to_the_last_30_days(world: World) -> None:
    body = world.get("/bff/backoffice/metrics", world.as_underwriter()).json()

    assert (body["date_from"], body["date_to"]) == ("2026-09-22", "2026-10-21")


def test_metrics_reject_a_reversed_or_huge_period(world: World) -> None:
    reversed_period = world.get(
        "/bff/backoffice/metrics",
        world.as_underwriter(),
        date_from="2026-10-21",
        date_to="2026-10-01",
    )
    huge = world.get(
        "/bff/backoffice/metrics",
        world.as_underwriter(),
        date_from="2020-01-01",
        date_to="2026-10-01",
    )

    assert reversed_period.status_code == 422
    assert huge.status_code == 422


def test_metrics_are_for_bank_staff(world: World) -> None:
    response = world.get("/bff/backoffice/metrics", world.as_client(world.director))

    assert response.status_code == 403


# --- scoring overview ------------------------------------------------------------------


def test_scoring_overview_in_one_call(world: World) -> None:
    agree = world.add_application(status="offer_ready")
    disagree = world.add_application(status="in_review")
    stopped = world.add_application(status="rejected")
    world.add_application(status="draft")
    ml = MlScoreDTO("ml-1", Decimal("0.02"), 700, "B", (), ())
    world.scoring.add_result(replace(factories.scoring_result(agree.id), ml=ml))
    world.scoring.add_result(
        replace(factories.scoring_result(disagree.id), grade="H", ml=ml, quality="degraded")
    )
    world.decision.add_decision(factories.decision(agree.id, "APPROVE"))
    world.decision.add_decision(factories.decision(disagree.id, "MANUAL_REVIEW"))
    world.decision.add_decision(
        factories.decision(stopped.id, "REJECT", reason_codes=("STOP_TAX_ARREARS",))
    )

    response = world.get("/bff/backoffice/scoring-overview", world.as_underwriter(), limit=2)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["considered"], body["scored"], body["with_ml"]) == (3, 2, 2)
    assert (body["stopped_before_models"], body["models_agree"], body["degraded"]) == (1, 1, 1)
    assert (body["manual_review"], body["decided"], body["decided_auto"]) == (1, 2, 2)
    grades = {g["grade"]: (g["pd"], g["ml"]) for g in body["by_grade"]}
    assert grades["C"] == (1, 0) and grades["H"] == (1, 0) and grades["B"] == (0, 2)
    zones = {(z["pd_zone"], z["ml_zone"]): z["count"] for z in body["zones"]}
    assert zones[("green", "green")] == 1 and zones[("red", "green")] == 1
    assert {(v["kind"], v["version"], v["count"]) for v in body["versions"]} >= {
        ("pd", "scorecard-1", 2),
        ("ml", "ml-1", 2),
    }
    assert len(body["items"]) == 2
    by_id = {i["application_id"]: i for i in body["items"]}
    if str(disagree.id) in by_id:
        assert by_id[str(disagree.id)]["models_disagree"] is True


def test_scoring_overview_needs_scoring_read(world: World) -> None:
    response = world.get(
        "/bff/backoffice/scoring-overview",
        world.as_underwriter(without=(Permissions.SCORING_READ,)),
    )
    assert response.status_code == 403


# --- applications overview -------------------------------------------------------------


def test_applications_overview_in_one_call(world: World) -> None:
    world.projector.application_stats = ApplicationStatsDTO(
        groups=(
            ApplicationGroupDTO("draft", "UNSECURED", "Без залога", 2, Decimal(0)),
            ApplicationGroupDTO("in_review", "UNSECURED", "Без залога", 3, Decimal("9000000")),
            ApplicationGroupDTO("rejected", "SECURED", "Под залог", 1, Decimal("5000000")),
            ApplicationGroupDTO("offer_declined", "SECURED", "Под залог", 1, Decimal("2000000")),
            ApplicationGroupDTO("disbursed", "UNSECURED", "Без залога", 2, Decimal("6000000")),
        ),
        amount_buckets=(AmountBucketDTO(Decimal(0), None, 8),),
        latest=(),
    )

    response = world.get("/bff/backoffice/applications-overview", world.as_underwriter())

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total"], body["submitted"], body["decided"], body["approved"]) == (9, 7, 4, 3)
    assert Decimal(body["requested_amount"]) == Decimal("22000000")
    assert [(f["key"], f["count"]) for f in body["funnel"]] == [
        ("started", 9),
        ("submitted", 7),
        ("decided", 4),
        ("approved", 3),
        ("signed", 2),
        ("disbursed", 2),
    ]
    assert [(p["product_code"], p["count"]) for p in body["products"]] == [
        ("UNSECURED", 7),
        ("SECURED", 2),
    ]
    assert {s["key"]: s["count"] for s in body["statuses"]}["in_review"] == 3
    assert body["amount_buckets"] == [{"min": "0", "max": None, "count": 8}]
