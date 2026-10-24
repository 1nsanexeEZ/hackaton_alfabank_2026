from decimal import Decimal
from uuid import uuid4

from src.modules.products.facade import EligibilityCheckDTO, EligibilityReasonDTO
from tests.applications.api.conftest import World


def test_draft_is_prefilled_with_company_data(world: World) -> None:
    application = world.create()

    assert application["status"] == "draft"
    assert application["number"] == "КР-2026-000001"
    assert application["version"] == 1
    organization = application["organization"]
    assert (organization["inn"], organization["kpp"]) == ("7701158817", "770101001")
    assert organization["legal_form"] == "LLC"
    terms = application["product_terms"]
    assert terms["code"] == "UNSECURED"
    assert [d["type"] for d in terms["required_documents"]] == ["bank_statement"]
    assert application["available_actions"] == ["edit", "upload_document", "submit", "cancel"]
    assert [h["to_status"] for h in application["history"]] == ["draft"]


def test_numbers_grow(world: World) -> None:
    world.create()
    second = world.create(product_code="OVERDRAFT")
    assert second["number"] == "КР-2026-000002"


def test_foreign_company_is_not_found(world: World) -> None:
    response = world.client.post(
        "/applications",
        json={"organization_id": str(world.vector), "product_code": "UNSECURED"},
        headers=world.headers(world.director),
    )
    assert response.status_code == 404


def test_one_active_application_per_product(world: World) -> None:
    first = world.create()
    response = world.client.post(
        "/applications",
        json={"organization_id": str(world.romashka), "product_code": "UNSECURED"},
        headers=world.headers(world.accountant),
    )
    assert response.status_code == 409
    assert response.json()["details"] == {
        "code": "duplicate_active",
        "application_id": first["id"],
    }


def test_company_must_fit_the_product(world: World) -> None:
    world.products.set_eligibility(
        EligibilityCheckDTO(
            "UNSECURED",
            world.romashka,
            eligible=False,
            reasons=(EligibilityReasonDTO("business_age", False, "Бизнесу меньше 6 месяцев"),),
        )
    )
    response = world.client.post(
        "/applications",
        json={"organization_id": str(world.romashka), "product_code": "UNSECURED"},
        headers=world.headers(world.director),
    )
    assert response.status_code == 422
    assert response.json()["details"]["reasons"] == [
        {"code": "business_age", "message": "Бизнесу меньше 6 месяцев"}
    ]


def test_employee_without_rights_cannot_start(world: World) -> None:
    response = world.client.post(
        "/applications",
        json={"organization_id": str(world.romashka), "product_code": "UNSECURED"},
        headers=world.headers(world.employee),
    )
    assert response.status_code == 403


def test_underwriter_does_not_write(world: World) -> None:
    response = world.client.post(
        "/applications",
        json={"organization_id": str(world.romashka), "product_code": "UNSECURED"},
        headers=world.underwriter(),
    )
    assert response.status_code == 403


def test_autosave_with_optimistic_lock(world: World) -> None:
    application = world.create()
    url = f"/applications/{application['id']}"
    headers = world.headers(world.director)

    saved = world.client.patch(
        url,
        json={"version": 1, "request": {"amount": "1500000.50", "purpose": "equipment"}},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["version"] == 2
    assert body["request"] == {
        "amount": "1500000.50",
        "term_months": None,
        "purpose": "equipment",
        "purpose_comment": None,
    }

    stale = world.client.patch(url, json={"version": 1, "request": {}}, headers=headers)
    assert stale.status_code == 409
    assert stale.json()["details"]["code"] == "version_conflict"


def test_collateral_and_consents(world: World) -> None:
    application = world.create()
    url = f"/applications/{application['id']}"
    headers = world.headers(world.director)
    body = world.client.patch(
        url,
        json={
            "version": 1,
            "collateral": {
                "type": "equipment",
                "description": "<b>Станок</b> ЧПУ",
                "declared_value": "2000000",
            },
            "consents": {"personal_data": True, "credit_bureau": True},
        },
        headers=headers,
    ).json()
    assert body["collateral"]["description"] == "Станок ЧПУ"  # markup stripped
    assert Decimal(body["collateral"]["declared_value"]) == Decimal("2000000")
    assert body["consents"]["credit_bureau_at"] is not None
    assert body["consents"]["automated_decision_at"] is None  # по желанию, ст. 16 152-ФЗ

    removed = world.client.patch(url, json={"version": 2, "collateral": None}, headers=headers)
    assert removed.json()["collateral"] is None


def test_invalid_input_is_rejected(world: World) -> None:
    application = world.create()
    url = f"/applications/{application['id']}"
    headers = world.headers(world.director)
    for request in ({"amount": "-1"}, {"amount": "1.001"}, {"term_months": 0}):
        response = world.client.patch(url, json={"version": 1, "request": request}, headers=headers)
        assert response.status_code == 422, request
    unknown_purpose = world.client.patch(
        url, json={"version": 1, "request": {"purpose": "yacht"}}, headers=headers
    )
    assert unknown_purpose.status_code == 422
    assert unknown_purpose.json()["details"]["field"] == "request.purpose"


def test_completeness_tells_what_is_left(world: World) -> None:
    application = world.create()
    url = f"/applications/{application['id']}/completeness"
    body = world.client.get(url, headers=world.headers(world.director)).json()
    assert body["complete"] is False
    assert {v["field"] for v in body["violations"]} == {
        "request.amount",
        "request.term_months",
        "request.purpose",
        "documents.bank_statement",
        "consents.personal_data",
        "consents.credit_bureau",
    }
    world.client.post(
        f"/applications/{application['id']}/cancel", headers=world.headers(world.director)
    )
    ready = world.ready(world.accountant)
    body = world.client.get(
        f"/applications/{ready['id']}/completeness", headers=world.headers(world.director)
    ).json()
    assert body == {"complete": True, "violations": []}


def test_lists_and_reads_are_limited_to_own_companies(world: World) -> None:
    application = world.create()
    world.clients.add_member(world.petrov, world.vector, "director")

    own = world.client.get("/applications", headers=world.headers(world.director)).json()
    assert [a["id"] for a in own] == [application["id"]]
    foreign = world.client.get("/applications", headers=world.headers(world.petrov)).json()
    assert foreign == []
    response = world.client.get(
        f"/applications/{application['id']}", headers=world.headers(world.petrov)
    )
    assert response.status_code == 404
    missing = world.client.get(f"/applications/{uuid4()}", headers=world.headers(world.director))
    assert missing.status_code == 404


def test_underwriter_reads_any_application(world: World) -> None:
    application = world.create()
    response = world.client.get(f"/applications/{application['id']}", headers=world.underwriter())
    assert response.status_code == 200
    assert response.json()["available_actions"] == []


def test_cancel_draft(world: World) -> None:
    application = world.create()
    response = world.client.post(
        f"/applications/{application['id']}/cancel",
        json={"reason": "Передумали"},
        headers=world.headers(world.director),
    )
    body = response.json()
    assert body["status"] == "cancelled" and body["closed_at"] is not None
    assert body["history"][-1]["reason"] == "Передумали"
    # the product slot is free again
    assert world.create()["status"] == "draft"


def test_consent_to_an_automated_decision(world: World) -> None:
    application = world.create()
    url = f"/applications/{application['id']}"
    body = world.client.patch(
        url,
        json={
            "version": 1,
            "consents": {
                "personal_data": True,
                "credit_bureau": True,
                "automated_decision": True,
            },
        },
        headers=world.headers(world.director),
    ).json()
    assert body["consents"]["automated_decision_at"] is not None


def test_beneficiary_answer(world: World) -> None:
    """115-ФЗ: действует ли клиент к выгоде третьего лица; ответ хранится, null его снимает."""
    application = world.create()
    url = f"/applications/{application['id']}"
    headers = world.headers(world.director)
    assert application["beneficiary"] is None

    body = world.client.patch(
        url,
        json={
            "version": 1,
            "beneficiary": {
                "acts_for_third_party": True,
                "beneficiary": {
                    "kind": "organization",
                    "name": "ООО «Транзитный агент»",
                    "inn": "7707115094",
                },
                "basis": "agency",
            },
            "collateral": {
                "type": "equipment",
                "description": "Станок",
                "declared_value": "2000000",
                "owner": "third_party",
                "owner_party": {"kind": "person", "name": "Залогов Иван Иванович"},
            },
        },
        headers=headers,
    ).json()
    assert body["beneficiary"]["acts_for_third_party"] is True
    assert body["beneficiary"]["beneficiary"]["inn"] == "7707115094"
    assert body["beneficiary"]["basis"] == "agency"
    assert body["collateral"]["owner_party"]["name"] == "Залогов Иван Иванович"

    stored = world.client.get(url, headers=headers).json()
    assert stored["beneficiary"] == body["beneficiary"]

    withdrawn = world.client.patch(url, json={"version": 2, "beneficiary": None}, headers=headers)
    assert withdrawn.json()["beneficiary"] is None


def test_beneficiary_without_the_basis_is_rejected(world: World) -> None:
    application = world.create()
    response = world.client.patch(
        f"/applications/{application['id']}",
        json={
            "version": 1,
            "beneficiary": {
                "acts_for_third_party": True,
                "beneficiary": {"kind": "person", "name": "Посредников Павел Павлович"},
            },
        },
        headers=world.headers(world.director),
    )
    assert response.status_code == 422


def test_beneficial_owners_answer(world: World) -> None:
    """115-ФЗ, ст. 6.1: бенефициары со слов клиента; пустой список — ответ, null — снять."""
    application = world.create()
    url = f"/applications/{application['id']}"
    headers = world.headers(world.director)
    assert application["beneficial_owners"] is None

    body = world.client.patch(
        url,
        json={
            "version": 1,
            "beneficial_owners": {
                "owners": [
                    {"name": "Смирнова Анна Сергеевна", "basis": "ownership"},
                    {"name": "Теневой Тимур", "basis": "control", "country": "AE"},
                ]
            },
            "beneficiary": {
                "acts_for_third_party": True,
                "beneficiary": {"kind": "person", "name": "Хоссейни Али Реза", "country": "IR"},
                "basis": "agency",
            },
        },
        headers=headers,
    ).json()
    assert body["beneficial_owners"]["owners"] == [
        {"name": "Смирнова Анна Сергеевна", "basis": "ownership", "country": None},
        {"name": "Теневой Тимур", "basis": "control", "country": "AE"},
    ]
    assert body["beneficiary"]["beneficiary"]["country"] == "IR"
    assert (
        world.client.get(url, headers=headers).json()["beneficial_owners"]
        == body["beneficial_owners"]
    )

    nobody = world.client.patch(
        url, json={"version": 2, "beneficial_owners": {"owners": []}}, headers=headers
    ).json()
    assert nobody["beneficial_owners"]["owners"] == []
    withdrawn = world.client.patch(
        url, json={"version": 3, "beneficial_owners": None}, headers=headers
    ).json()
    assert withdrawn["beneficial_owners"] is None


def test_country_must_be_an_iso_code(world: World) -> None:
    application = world.create()
    response = world.client.patch(
        f"/applications/{application['id']}",
        json={
            "version": 1,
            "beneficial_owners": {
                "owners": [{"name": "Теневой Тимур", "basis": "control", "country": "Эмираты"}]
            },
        },
        headers=world.headers(world.director),
    )
    assert response.status_code == 422
