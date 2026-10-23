"""Catalog and calculator are public (the showcase before login); everything
about a particular company needs a token and membership in that company."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.core.domain import Money
from src.core.facades import use_facade
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.clients.facade import ClientsFacade
from src.modules.products.api.dependencies import (
    BorrowerProfilesDep,
    ProductServiceDep,
    ensure_can_view,
)
from src.modules.products.api.schemas import (
    CalculateBody,
    EligibilityRead,
    NeedBody,
    PaymentScheduleRead,
    ProductRead,
    RecommendationRead,
    RecommendationsRead,
)
from src.modules.products.domain.value_objects import LoanNeed
from src.modules.products.facade import Purpose

router = APIRouter(prefix="/products", tags=["products"])

CreditsReader = Annotated[OpenSubTokenDTO, Depends(require_permissions(Permissions.CREDITS_READ))]
Clients = Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))]


@router.get("", response_model=list[ProductRead])
async def list_products(
    service: ProductServiceDep, purpose: Annotated[Purpose | None, Query()] = None
) -> list[ProductRead]:
    """Active products in catalog order, optionally for one purpose."""
    return [ProductRead.of(p) for p in await service.list_active(purpose)]


@router.post("/recommend", response_model=RecommendationsRead)
async def recommend(data: NeedBody, service: ProductServiceDep) -> RecommendationsRead:
    """Matching by the need only: eligibility of a company is not checked."""
    need = LoanNeed(data.purpose, Money(data.amount), data.term_months)
    items = await service.recommend(need)
    return RecommendationsRead(
        purpose=data.purpose,
        amount=data.amount,
        term_months=data.term_months,
        items=[RecommendationRead.of(r) for r in items],
    )


@router.post("/recommend/{organization_id}", response_model=RecommendationsRead)
async def recommend_for_organization(
    organization_id: UUID,
    data: NeedBody,
    token: CreditsReader,
    clients: Clients,
    borrowers: BorrowerProfilesDep,
    service: ProductServiceDep,
) -> RecommendationsRead:
    """Matching for a company: eligibility reasons and the cash gap forecast."""
    await ensure_can_view(token, organization_id, clients)
    borrower = await borrowers.get(organization_id, data.amount)
    need = LoanNeed(data.purpose, Money(data.amount), data.term_months)
    items = await service.recommend(need, borrower)
    return RecommendationsRead(
        purpose=data.purpose,
        amount=data.amount,
        term_months=data.term_months,
        organization_id=organization_id,
        cash_gap_expected=borrower.cash_gap_expected,
        items=[RecommendationRead.of(r) for r in items],
    )


@router.get("/{code}", response_model=ProductRead)
async def get_product(code: str, service: ProductServiceDep) -> ProductRead:
    """Archived products are readable too (status `archived`)."""
    return ProductRead.of(await service.get(code))


@router.post("/{code}/calculate", response_model=PaymentScheduleRead)
async def calculate(
    code: str, data: CalculateBody, service: ProductServiceDep
) -> PaymentScheduleRead:
    schedule = await service.calculate(
        code, Money(data.amount), data.term_months, data.rate, data.repayment
    )
    return PaymentScheduleRead.of(schedule)


@router.get("/{code}/eligibility", response_model=EligibilityRead)
async def check_eligibility(
    code: str,
    organization_id: Annotated[UUID, Query()],
    token: CreditsReader,
    clients: Clients,
    borrowers: BorrowerProfilesDep,
    service: ProductServiceDep,
) -> EligibilityRead:
    product = await service.get_selectable(code)
    await ensure_can_view(token, organization_id, clients)
    borrower = await borrowers.get(organization_id)
    return EligibilityRead.of(product.check_eligibility(borrower), organization_id)
