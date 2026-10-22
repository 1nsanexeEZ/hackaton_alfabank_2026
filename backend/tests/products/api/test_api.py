import asyncio
from collections.abc import Iterator
from decimal import Decimal
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
    ]
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
    assert items[-1]["support_program"]["code"] == "MSP_PRIORITY"


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
    ]
    assert all(i["eligible"] is None for i in items)
    assert items[-1]["status"] == "needs_adjustment"
    assert items[-1]["adjustments"][0].startswith("Максимум 30 млн ₽ — запросите 30 млн ₽")
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
