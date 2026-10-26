import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from seed.products import seed
from seed.run import SeedContext
from src.core.access.organizations import MemberOrganizationsResolver
from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.core.domain import FrozenClock
from src.core.facades import FacadeRegistry
from src.main import create_app
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO
from src.modules.products.domain.product import CreditProduct, ProductStatus
from src.modules.products.infrastructure.repository import SqlAlchemyProductRepository
from tests.fakes import builders, install
from tests.fakes.clients_facade import FakeClientsFacade
from tests.helpers import bearer, create_schema, token_for

CLIENT_PERMISSIONS = [Permissions.CREDITS_READ, Permissions.ORGANIZATIONS_READ]
CLIENT_POLICIES = {Permissions.ORGANIZATIONS_READ: ["org_member"]}


async def _seed(settings: Settings, archive: tuple[str, ...] = ()) -> None:
    engine = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await seed(SeedContext(settings, sessions, FacadeRegistry(), FrozenClock()))
    async with sessions() as session:
        repository = SqlAlchemyProductRepository(session)
        for code in archive:
            product = await repository.get_current(code)
            assert product is not None
            product.archive()
            await repository.save(product)
        await session.commit()
    await engine.dispose()


@pytest.fixture
def clients() -> FakeClientsFacade:
    return FakeClientsFacade()


@pytest.fixture
def app(settings: Settings, clients: FakeClientsFacade) -> FastAPI:
    create_schema(settings.database_url)
    asyncio.run(_seed(settings, archive=("REFINANCE",)))
    app = create_app(settings)
    install(app, ClientsFacade, clients)
    install(app, MemberOrganizationsResolver, clients)
    return app


@pytest.fixture
def api(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def company(clients: FakeClientsFacade, code: str) -> OrganizationSnapshotDTO:
    return clients.add_organization(builders.organization_snapshot(code))


def client_token(app: FastAPI, account_id: UUID) -> dict[str, str]:
    return bearer(token_for(app, CLIENT_PERMISSIONS, CLIENT_POLICIES, subject=account_id))


# --- showcase: no token -------------------------------------------------------------------


def test_catalog_is_public(api: TestClient) -> None:
    response = api.get("/products")
    assert response.status_code == 200
    items = response.json()
    # REFINANCE is archived in this setup.
    assert [p["code"] for p in items] == [
        "UNSECURED",
        "SECURED",
        "CREDIT_LINE",
        "OVERDRAFT",
        "AUTO",
        "MORTGAGE",
        "GOV_SUPPORT",
        "STARTUP",
    ]
    assert [p["startup_only"] for p in items] == [False] * 7 + [True]
    unsecured = items[0]
    assert unsecured["frontend_id"] == "unsecured" and unsecured["name"] == "Кредит без залога"
    assert Decimal(unsecured["rate_base"]) == Decimal("23.5")
    assert Decimal(unsecured["amount_max"]) == Decimal("30000000")
    assert unsecured["purposes"] == [
        "working_capital",
        "contract_execution",
        "refinancing",
        "expansion",
    ]
    assert unsecured["required_documents"][0]["type"] == "financial_report"
    assert items[-2]["support_program"]["code"] == "MSP_PRIORITY"
    assert items[-1]["support_program"]["code"] == "MSP_START"


def test_catalog_by_purpose(api: TestClient) -> None:
    codes = [p["code"] for p in api.get("/products", params={"purpose": "cash_gap"}).json()]
    assert codes == ["CREDIT_LINE", "OVERDRAFT"]
    assert api.get("/products", params={"purpose": "yacht"}).status_code == 422


def test_product_card(api: TestClient) -> None:
    response = api.get("/products/AUTO")
    assert response.status_code == 200
    assert response.json()["application_fields_schema"]["required"] == [
        "vehicle_type",
        "vehicle_description",
        "price",
    ]
    missing = api.get("/products/NOPE")
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"
    # Archived products stay readable for old applications.
    assert api.get("/products/REFINANCE").json()["status"] == "archived"


def test_calculator_is_public(api: TestClient) -> None:
    response = api.post(
        "/products/UNSECURED/calculate", json={"amount": "3000000", "term_months": 24}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["repayment"] == "annuity" and Decimal(body["rate"]) == Decimal("23.5")
    assert body["monthly_payment"] == "157865.62"
    assert len(body["payments"]) == 24
    assert sum(Decimal(p["principal"]) for p in body["payments"]) == Decimal("3000000")

    explicit = api.post(
        "/products/UNSECURED/calculate",
        json={"amount": 3000000, "term_months": 24, "rate": "24", "repayment": "differentiated"},
    ).json()
    assert explicit["repayment"] == "differentiated"
    assert explicit["monthly_payment"] == "185000.00"  # 125 000 + 60 000 of interest


@pytest.mark.parametrize(
    "body,field,code",
    [
        ({"amount": 40_000_000, "term_months": 24}, "amount", "out_of_range"),
        ({"amount": 3_000_000, "term_months": 6}, "term_months", "out_of_range"),
        ({"amount": 3_000_000, "term_months": 24, "rate": "12"}, "rate", "out_of_range"),
        (
            {"amount": 3_000_000, "term_months": 24, "repayment": "interest_only"},
            "repayment",
            "not_offered",
        ),
    ],
)
def test_calculator_keeps_to_the_product_frames(
    api: TestClient, body: dict, field: str, code: str
) -> None:
    response = api.post("/products/UNSECURED/calculate", json=body)
    assert response.status_code == 422
    assert response.json()["details"]["field"] == field
    assert response.json()["details"]["code"] == code


def test_archived_product_can_not_be_calculated(api: TestClient) -> None:
    response = api.post(
        "/products/REFINANCE/calculate", json={"amount": 3000000, "term_months": 24}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "product_not_available"


def test_recommend_without_a_company(api: TestClient) -> None:
    response = api.post(
        "/products/recommend",
        json={"purpose": "working_capital", "amount": 40000000, "term_months": 24},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization_id"] is None and body["cash_gap_expected"] is None
    items = body["items"]
    assert [i["product"]["code"] for i in items] == [
        "GOV_SUPPORT",
        "SECURED",
        "CREDIT_LINE",
        "UNSECURED",
        "STARTUP",
    ]
    assert all(i["eligible"] is None for i in items)
    assert items[3]["status"] == "needs_adjustment"
    assert items[3]["adjustments"][0].startswith("Максимум 30 млн ₽ — запросите 30 млн ₽")
    assert all(i["reasons"] for i in items)


def test_public_recommend_takes_no_company(api: TestClient) -> None:
    response = api.post(
        "/products/recommend",
        json={
            "purpose": "working_capital",
            "amount": 1000000,
            "term_months": 24,
            "organization_id": str(uuid4()),
        },
    )
    assert response.status_code == 422


# --- a particular company: token and membership -------------------------------------------


def test_recommend_for_a_company_needs_a_token(api: TestClient, clients: FakeClientsFacade) -> None:
    org = company(clients, "ivanov")
    response = api.post(
        f"/products/recommend/{org.id}",
        json={"purpose": "working_capital", "amount": 3000000, "term_months": 24},
    )
    assert response.status_code == 401


def test_recommend_for_my_company(
    app: FastAPI, api: TestClient, clients: FakeClientsFacade
) -> None:
    org = company(clients, "ivanov")
    owner = uuid4()
    clients.add_member(owner, org.id, "owner")
    response = api.post(
        f"/products/recommend/{org.id}",
        json={"purpose": "working_capital", "amount": 3000000, "term_months": 24},
        headers=client_token(app, owner),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization_id"] == str(org.id)
    items = body["items"]
    assert [(i["product"]["code"], i["status"]) for i in items] == [
        ("UNSECURED", "available"),
        ("GOV_SUPPORT", "unavailable"),
        ("SECURED", "unavailable"),
        ("CREDIT_LINE", "unavailable"),
        ("STARTUP", "unavailable"),
    ]
    gov = items[1]
    assert {
        "code": "business_age",
        "passed": False,
        "message": "Нужно от 12 месяцев работы, у вас 8",
    } in gov["reasons"]
    assert any(r["code"] == "okved" and r["passed"] for r in gov["reasons"])


def test_recommend_for_a_stranger_company_is_404(
    app: FastAPI, api: TestClient, clients: FakeClientsFacade
) -> None:
    org = company(clients, "romashka")
    response = api.post(
        f"/products/recommend/{org.id}",
        json={"purpose": "working_capital", "amount": 3000000, "term_months": 24},
        headers=client_token(app, uuid4()),
    )
    assert response.status_code == 404


def test_eligibility_of_my_company(
    app: FastAPI, api: TestClient, clients: FakeClientsFacade
) -> None:
    org = company(clients, "ivanov")
    accountant = uuid4()
    clients.add_member(accountant, org.id, "accountant")
    headers = client_token(app, accountant)

    def check(code: str) -> dict:
        response = api.get(
            f"/products/{code}/eligibility",
            params={"organization_id": str(org.id)},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert check("UNSECURED")["eligible"] and check("OVERDRAFT")["eligible"]
    line = check("CREDIT_LINE")
    assert not line["eligible"] and line["organization_id"] == str(org.id)
    gov = check("GOV_SUPPORT")
    assert not gov["eligible"]
    assert any(r["code"] == "okved" and r["passed"] for r in gov["reasons"])


def test_eligibility_of_a_stranger_company_is_404(
    app: FastAPI, api: TestClient, clients: FakeClientsFacade
) -> None:
    org = company(clients, "romashka")
    response = api.get(
        "/products/UNSECURED/eligibility",
        params={"organization_id": str(org.id)},
        headers=client_token(app, uuid4()),
    )
    assert response.status_code == 404
    unknown = api.get(
        "/products/UNSECURED/eligibility",
        params={"organization_id": str(uuid4())},
        headers=client_token(app, uuid4()),
    )
    assert unknown.status_code == 404


def test_eligibility_needs_a_token_with_credits_read(
    app: FastAPI, api: TestClient, clients: FakeClientsFacade
) -> None:
    org = company(clients, "romashka")
    params = {"organization_id": str(org.id)}
    assert api.get("/products/UNSECURED/eligibility", params=params).status_code == 401
    member = uuid4()
    clients.add_member(member, org.id, "director")
    no_credits = bearer(token_for(app, [Permissions.ORGANIZATIONS_READ], subject=member))
    response = api.get("/products/UNSECURED/eligibility", params=params, headers=no_credits)
    assert response.status_code == 403


def test_bank_staff_see_any_company(
    app: FastAPI, api: TestClient, clients: FakeClientsFacade
) -> None:
    org = company(clients, "zakat")
    underwriter = bearer(token_for(app, CLIENT_PERMISSIONS))
    response = api.get(
        "/products/UNSECURED/eligibility",
        params={"organization_id": str(org.id)},
        headers=underwriter,
    )
    assert response.status_code == 200
    reasons = {r["code"]: r for r in response.json()["reasons"]}
    assert reasons["registry_status"]["passed"] is True


def test_archived_product_has_no_eligibility(
    app: FastAPI, api: TestClient, clients: FakeClientsFacade
) -> None:
    org = company(clients, "romashka")
    response = api.get(
        "/products/REFINANCE/eligibility",
        params={"organization_id": str(org.id)},
        headers=bearer(token_for(app, CLIENT_PERMISSIONS)),
    )
    assert response.status_code == 409


# --- keeping the catalog: credits.create|update|delete ------------------------------------

MANAGER_PERMISSIONS = [
    Permissions.CREDITS_CREATE,
    Permissions.CREDITS_UPDATE,
    Permissions.CREDITS_DELETE,
]


def manager(app: FastAPI) -> dict[str, str]:
    return bearer(token_for(app, MANAGER_PERMISSIONS))


def new_product(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": "FACTORING",
        "frontend_id": "factoring",
        "name": "Факторинг",
        "short_description": "Деньги под отсрочку платежа покупателей",
        "purposes": ["working_capital", "cash_gap"],
        "facility": "credit_line_revolving",
        "repayment_options": ["interest_only", "annuity"],
        "amount_min": "500000",
        "amount_max": "20000000",
        "term_min_months": 3,
        "term_max_months": 12,
        "rate_base": "21",
        "rate_max": "27",
        "min_business_age_months": 6,
        "min_annual_revenue": "5000000",
        "required_documents": [
            {"type": "receivables_register", "title": "Реестр дебиторской задолженности"}
        ],
        "workflow_code": "standard_v2",
        "auto_decision_limit": "5000000",
    }
    body.update(overrides)
    return body


def as_body(card: dict[str, Any]) -> dict[str, Any]:
    """A product card read back is the body of new terms."""
    return {k: v for k, v in card.items() if k not in ("code", "version", "status")}


def stored(settings: Settings, code: str, version: int) -> CreditProduct | None:
    async def read() -> CreditProduct | None:
        engine = create_async_engine(settings.database_url)
        async with async_sessionmaker(engine)() as session:
            product = await SqlAlchemyProductRepository(session).get_version(code, version)
        await engine.dispose()
        return product

    return asyncio.run(read())


def test_keeping_the_catalog_needs_rights(app: FastAPI, api: TestClient) -> None:
    calls = [
        ("GET", "/products/all", None),
        ("POST", "/products", new_product()),
        ("PUT", "/products/UNSECURED", as_body(api.get("/products/UNSECURED").json())),
        ("POST", "/products/UNSECURED/activate", None),
        ("DELETE", "/products/UNSECURED", None),
    ]
    client = client_token(app, uuid4())
    for method, path, body in calls:
        assert api.request(method, path, json=body).status_code == 401, path
        assert api.request(method, path, json=body, headers=client).status_code == 403, path
    admin = bearer(token_for(app, [Permissions.ADMIN]))
    assert api.get("/products/all", headers=admin).status_code == 200


def test_a_draft_is_hidden_until_activated(app: FastAPI, api: TestClient) -> None:
    headers = manager(app)
    response = api.post("/products", json=new_product(), headers=headers)
    assert response.status_code == 201, response.text
    draft = response.json()
    assert (draft["code"], draft["version"], draft["status"]) == ("FACTORING", 1, "draft")
    assert draft["required_documents"][0]["legal_forms"] == []
    assert draft["allowed_legal_forms"] == ["LLC", "IE", "JSC"]
    assert api.get("/products/FACTORING").status_code == 404
    assert "FACTORING" not in [p["code"] for p in api.get("/products").json()]
    everything = api.get("/products/all", headers=headers).json()
    assert [(p["code"], p["status"]) for p in everything][-2:] == [
        ("STARTUP", "active"),
        ("FACTORING", "draft"),
    ]
    assert ("REFINANCE", "archived") in [(p["code"], p["status"]) for p in everything]

    activated = api.post("/products/FACTORING/activate", headers=headers)
    assert activated.status_code == 200 and activated.json()["status"] == "active"
    assert [p["code"] for p in api.get("/products").json()][-1] == "FACTORING"
    schedule = api.post(
        "/products/FACTORING/calculate", json={"amount": "1000000", "term_months": 6}
    ).json()
    assert schedule["repayment"] == "interest_only" and Decimal(schedule["rate"]) == 21
    again = api.post("/products/FACTORING/activate", headers=headers)
    assert again.status_code == 409 and again.json()["code"] == "invalid_transition"


def test_a_product_may_be_published_right_away(app: FastAPI, api: TestClient) -> None:
    response = api.post("/products", json=new_product(status="active"), headers=manager(app))
    assert response.status_code == 201 and response.json()["status"] == "active"
    assert api.get("/products/FACTORING").json()["version"] == 1


def test_a_taken_code_is_a_conflict(app: FastAPI, api: TestClient) -> None:
    response = api.post(
        "/products", json=new_product(code="UNSECURED", frontend_id="x"), headers=manager(app)
    )
    assert response.status_code == 409 and response.json()["code"] == "conflict"


@pytest.mark.parametrize(
    "overrides,field,code",
    [
        ({"code": "factoring"}, "code", "bad_format"),
        ({"workflow_code": "nope_v1"}, "workflow_code", "unknown"),
        ({"frontend_id": "unsecured"}, "frontend_id", "taken"),
        ({"amount_max": "100000"}, "amount_max", "less_than_min"),
        ({"auto_decision_limit": "30000000"}, "auto_decision_limit", "above_max"),
        ({"collateral_types": ["vehicle"]}, "collateral_types", "not_expected"),
    ],
)
def test_a_new_product_keeps_the_rules(
    app: FastAPI, api: TestClient, overrides: dict[str, Any], field: str, code: str
) -> None:
    response = api.post("/products", json=new_product(**overrides), headers=manager(app))
    assert response.status_code == 422, response.text
    assert response.json()["details"] == {"field": field, "code": code}
    assert "FACTORING" not in [
        p["code"] for p in api.get("/products/all", headers=manager(app)).json()
    ]


def test_new_terms_of_a_published_product_are_a_new_version(
    app: FastAPI, api: TestClient, settings: Settings
) -> None:
    body = as_body(api.get("/products/UNSECURED").json()) | {"rate_base": "22"}
    response = api.put("/products/UNSECURED", json=body, headers=manager(app))
    assert response.status_code == 200, response.text
    revised = response.json()
    assert (revised["version"], revised["status"]) == (2, "active")
    assert as_body(revised) == as_body(api.get("/products/UNSECURED").json())
    assert Decimal(revised["rate_base"]) == 22
    catalog = api.get("/products").json()
    assert (catalog[0]["code"], catalog[0]["version"]) == ("UNSECURED", 2)
    assert [p["code"] for p in catalog].count("UNSECURED") == 1
    # Applications opened with version 1 keep pointing to it.
    first = stored(settings, "UNSECURED", 1)
    assert first is not None and first.status == ProductStatus.ARCHIVED


def test_a_draft_changes_in_place(app: FastAPI, api: TestClient) -> None:
    headers = manager(app)
    api.post("/products", json=new_product(), headers=headers)
    body = as_body(new_product(name="Факторинг без регресса"))
    response = api.put("/products/FACTORING", json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert (response.json()["version"], response.json()["status"]) == (1, "draft")
    assert response.json()["name"] == "Факторинг без регресса"


def test_an_archived_product_comes_back_with_new_terms(app: FastAPI, api: TestClient) -> None:
    body = as_body(api.get("/products/REFINANCE").json())
    response = api.put("/products/REFINANCE", json=body, headers=manager(app))
    assert response.status_code == 200, response.text
    assert (response.json()["version"], response.json()["status"]) == (2, "active")
    assert "REFINANCE" in [p["code"] for p in api.get("/products").json()]


def test_unknown_product_can_not_be_changed(app: FastAPI, api: TestClient) -> None:
    headers = manager(app)
    body = as_body(new_product())
    assert api.put("/products/NOPE", json=body, headers=headers).status_code == 404
    assert api.post("/products/NOPE/activate", headers=headers).status_code == 404
    assert api.delete("/products/NOPE", headers=headers).status_code == 404


def test_off_sale_a_published_product_is_archived_and_a_draft_deleted(
    app: FastAPI, api: TestClient
) -> None:
    headers = manager(app)
    assert api.delete("/products/OVERDRAFT", headers=headers).status_code == 204
    assert api.get("/products/OVERDRAFT").json()["status"] == "archived"
    assert "OVERDRAFT" not in [p["code"] for p in api.get("/products").json()]
    again = api.delete("/products/OVERDRAFT", headers=headers)
    assert again.status_code == 409 and again.json()["code"] == "invalid_transition"

    api.post("/products", json=new_product(), headers=headers)
    assert api.delete("/products/FACTORING", headers=headers).status_code == 204
    assert "FACTORING" not in [p["code"] for p in api.get("/products/all", headers=headers).json()]
    # The code is free again.
    assert api.post("/products", json=new_product(), headers=headers).status_code == 201


# --- rates follow the key rate ------------------------------------------------------------


def test_clients_get_rates_at_the_key_rate(settings: Settings) -> None:
    """Key rate 14 against the catalog's 16.5: clients get every rate 2.5 points lower, the
    catalog is kept with the rates it was set at."""
    settings = settings.model_copy(update={"key_rate": Decimal("14.00")})
    create_schema(settings.database_url)
    asyncio.run(_seed(settings))
    app = create_app(settings)
    with TestClient(app) as api:
        unsecured = api.get("/products/UNSECURED").json()
        rates = (Decimal(unsecured["rate_base"]), Decimal(unsecured["rate_max"]))
        assert rates == (Decimal(21), Decimal("27.5"))
        gov = next(p for p in api.get("/products").json() if p["code"] == "GOV_SUPPORT")
        assert Decimal(gov["rate_base"]) == Decimal("9.5")
        assert Decimal(gov["support_program"]["rate_cap"]) == Decimal("12.5")
        schedule = api.post(
            "/products/UNSECURED/calculate", json={"amount": "1000000", "term_months": 12}
        ).json()
        assert Decimal(schedule["rate"]) == 21
        kept = api.get("/products/all", headers=manager(app)).json()
        stored_rate = next(p for p in kept if p["code"] == "UNSECURED")["rate_base"]
        assert Decimal(stored_rate) == Decimal("23.5")


def test_showcase_card_is_kept_with_the_product(app: FastAPI, api: TestClient) -> None:
    unsecured = api.get("/products/UNSECURED").json()
    assert unsecured["keywords"] == ["Без залога", "Быстро", "На любые цели"]
    assert (unsecured["tag"], unsecured["decision_time"]) == ("Популярный", "5 минут")
    assert api.get("/products/SECURED").json()["tag"] is None

    card = {"keywords": ["Факторинг", "Отсрочка"], "tag": "Новинка", "decision_time": "1 день"}
    response = api.post("/products", json=new_product(**card), headers=manager(app))
    assert response.status_code == 201, response.text
    assert {k: response.json()[k] for k in card} == card
    plain = api.post(
        "/products", json=new_product(code="PLAIN", frontend_id="plain"), headers=manager(app)
    ).json()
    assert (plain["keywords"], plain["tag"], plain["decision_time"]) == ([], None, None)


@pytest.mark.parametrize(
    "card",
    [
        {"keywords": ["а", "б", "в", "г", "д", "е"]},
        {"keywords": [""]},
        {"tag": "х" * 41},
        {"decision_time": ""},
    ],
)
def test_showcase_card_has_limits(app: FastAPI, api: TestClient, card: dict[str, Any]) -> None:
    response = api.post("/products", json=new_product(**card), headers=manager(app))
    assert response.status_code == 422, response.text
