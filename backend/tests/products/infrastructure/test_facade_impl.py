from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.exceptions.exceptions import NotFoundError
from src.core.facades import FacadeRegistry
from src.modules.clients.facade import ClientsFacade
from src.modules.products.domain.errors import ProductNotAvailableError
from src.modules.products.infrastructure.facade_impl import ProductsFacadeImpl
from src.modules.products.infrastructure.repository import SqlAlchemyProductRepository
from src.modules.scoring.facade import EstimateDTO, ScoringFacade
from tests.fakes import builders
from tests.fakes.clients_facade import FakeClientsFacade
from tests.fakes.products_facade import FakeProductsFacade
from tests.fakes.scoring_facade import FakeScoringFacade
from tests.products.infrastructure.test_repository import run_seed


@pytest.fixture
def clients() -> FakeClientsFacade:
    return FakeClientsFacade()


@pytest.fixture
def registry(clients: FakeClientsFacade) -> FacadeRegistry:
    registry = FacadeRegistry()
    registry.register(ClientsFacade, lambda _session: clients)
    return registry


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    await run_seed(session_factory)
    async with session_factory() as session:
        yield session


@pytest.fixture
def facade(session: AsyncSession, registry: FacadeRegistry) -> ProductsFacadeImpl:
    return ProductsFacadeImpl(session, registry)


async def test_catalog(facade: ProductsFacadeImpl) -> None:
    products = await facade.list_active()
    assert [p.code for p in products][:4] == ["UNSECURED", "SECURED", "CREDIT_LINE", "OVERDRAFT"]
    gov = await facade.get_product("GOV_SUPPORT")
    assert gov.frontend_id == "gov-support" and gov.status == "active"
    assert gov.support_program is not None and gov.support_program.rate_cap == Decimal("15")
    assert "62" in gov.support_program.okved_whitelist
    unsecured = await facade.get_product("UNSECURED")
    assert unsecured.purposes == (
        "working_capital",
        "contract_execution",
        "refinancing",
        "expansion",
    )
    assert [
        (d.type, d.required_from_amount, d.legal_forms) for d in unsecured.required_documents
    ] == [
        ("financial_report", Decimal("5000000.00"), ("LLC", "JSC")),
        ("tax_return", Decimal("5000000.00"), ("IE",)),
    ]
    with pytest.raises(NotFoundError):
        await facade.get_product("NOPE")


async def test_terms_snapshot(facade: ProductsFacadeImpl) -> None:
    terms = await facade.get_terms_snapshot("GOV_SUPPORT")
    assert (terms.code, terms.version, terms.workflow_code) == ("GOV_SUPPORT", 1, "standard_v1")
    assert (terms.rate_base, terms.rate_max) == (Decimal("12"), Decimal("15"))
    secured = await facade.get_terms_snapshot("SECURED")
    assert secured.collateral_required and secured.collateral_required_from is None
    line = await facade.get_terms_snapshot("CREDIT_LINE")
    assert not line.collateral_required and line.collateral_required_from == Decimal("30000000")
    assert (await facade.get_terms_snapshot("AUTO")).application_fields_schema["required"] == [
        "vehicle_type",
        "vehicle_description",
        "price",
    ]


async def test_archived_product_is_not_selectable(
    facade: ProductsFacadeImpl, session: AsyncSession
) -> None:
    repository = SqlAlchemyProductRepository(session)
    overdraft = await repository.get_current("OVERDRAFT")
    assert overdraft is not None
    overdraft.archive()
    await repository.save(overdraft)

    assert (await facade.get_product("OVERDRAFT")).status == "archived"
    assert "OVERDRAFT" not in [p.code for p in await facade.list_active()]
    with pytest.raises(ProductNotAvailableError):
        await facade.get_terms_snapshot("OVERDRAFT")
    with pytest.raises(ProductNotAvailableError):
        await facade.check_eligibility("OVERDRAFT", uuid4())


async def test_eligibility_of_ivanov(
    facade: ProductsFacadeImpl, clients: FakeClientsFacade
) -> None:
    ivanov = clients.add_organization(builders.organization_snapshot("ivanov"))
    unsecured = await facade.check_eligibility("UNSECURED", ivanov.id)
    assert unsecured.eligible and unsecured.organization_id == ivanov.id
    line = await facade.check_eligibility("CREDIT_LINE", ivanov.id)
    assert not line.eligible
    assert any(
        r.code == "business_age" and r.message == "Нужно от 12 месяцев работы, у вас 8"
        for r in line.reasons
    )
    with pytest.raises(NotFoundError):
        await facade.check_eligibility("UNSECURED", uuid4())


async def test_recommend(
    facade: ProductsFacadeImpl, clients: FakeClientsFacade, registry: FacadeRegistry
) -> None:
    anonymous = await facade.recommend("cash_gap", Decimal("1000000"), 12)
    assert [r.product.code for r in anonymous] == ["CREDIT_LINE", "OVERDRAFT"]
    assert all(r.eligible is None and r.reasons for r in anonymous)
    assert anonymous[0].estimated_monthly_payment == Decimal("18333.33")  # interest at 22 %

    romashka = clients.add_organization(builders.organization_snapshot("romashka"))
    plain = await facade.recommend("working_capital", Decimal("3000000"), 24, romashka.id)
    assert plain[0].product.code == "GOV_SUPPORT" and plain[0].eligible is True

    gap = EstimateDTO(score=640, grade="C", flags=("cash_gap",), factors=())
    registry.register(ScoringFacade, lambda _session: FakeScoringFacade(gap))
    lifted = await facade.recommend("working_capital", Decimal("3000000"), 24, romashka.id)
    assert [r.product.code for r in lifted][0] == "CREDIT_LINE"
    assert "OVERDRAFT" in [r.product.code for r in lifted]
    assert [r.rank for r in lifted] == list(range(1, len(lifted) + 1))


@pytest.mark.parametrize(
    "amount,term,rate,repayment",
    [
        ("3000000", 24, "24", "annuity"),
        ("1200000", 12, "0", "annuity"),
        ("750000", 18, "23.5", "differentiated"),
        ("500000", 6, "30", "interest_only"),
    ],
)
def test_payment_formula_is_the_one_the_fake_uses(
    facade: ProductsFacadeImpl, amount: str, term: int, rate: str, repayment: str
) -> None:
    args = (Decimal(amount), term, Decimal(rate), repayment)
    real = facade.calculate_payment(*args)  # type: ignore[arg-type]
    fake = FakeProductsFacade().calculate_payment(*args)  # type: ignore[arg-type]
    assert real == fake
