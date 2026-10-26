"""Catalog and calculator are public (the showcase before login); everything
about a particular company needs a token and membership in that company.
Keeping the catalog needs `credits.create|update|delete`."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.access.dependencies import require_permissions
from src.core.access.permissions import Permissions
from src.core.domain import Money
from src.core.facades import use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.clients.facade import ClientsFacade
from src.modules.products.api.dependencies import (
    BorrowerProfilesDep,
    ProductCatalogDep,
    ProductServiceDep,
    ensure_can_view,
)
from src.modules.products.api.schemas import (
    CalculateBody,
    CatalogProductRead,
    EligibilityRead,
    NeedBody,
    PaymentScheduleRead,
    ProductBody,
    ProductCreate,
    ProductRead,
    RecommendationRead,
    RecommendationsRead,
)
from src.modules.products.domain.value_objects import LoanNeed
from src.modules.products.facade import Purpose

router = APIRouter(prefix="/products", tags=["products"])

CreditsReader = Annotated[OpenSubTokenDTO, Depends(require_permissions(Permissions.CREDITS_READ))]
Clients = Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))]
CanCreate = [Depends(require_permissions(Permissions.CREDITS_CREATE))]
CanUpdate = [Depends(require_permissions(Permissions.CREDITS_UPDATE))]
CanDelete = [Depends(require_permissions(Permissions.CREDITS_DELETE))]


@router.get("", response_model=list[ProductRead])
async def list_products(
    service: ProductServiceDep, purpose: Annotated[Purpose | None, Query()] = None
) -> list[ProductRead]:
    """Active products in catalog order, optionally for one purpose."""
    return [ProductRead.of(p) for p in await service.list_active(purpose)]


@router.get("/all", response_model=list[CatalogProductRead], dependencies=CanUpdate)
async def list_all_products(
    catalog: ProductCatalogDep, service: ProductServiceDep
) -> list[CatalogProductRead]:
    """For keeping the catalog: every product in its latest version, drafts and archived
    ones too, in catalog order. The rates are the stored ones, set at the catalog key rate
    (they are what PUT takes); `market_rate` — the same moved to the key rate in force, as
    clients see them now."""
    shift = await service.key_rate_shift()
    return [CatalogProductRead.at(p, shift) for p in await catalog.list_all()]


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=CanCreate,
)
async def create_product(
    data: ProductCreate, catalog: ProductCatalogDep, session: DbSession
) -> ProductRead:
    """Version 1 at the end of the catalog, a draft unless `status: active`. 409 — the code
    is taken; 422 `workflow_code` `unknown` — no such route (GET /workflows), `frontend_id`
    `taken` — another product has this card."""
    product = await catalog.create(data.product(data.code), publish=data.status == "active")
    await session.commit()
    return ProductRead.of(product)


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
    borrower = await borrowers.get(organization_id)
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


@router.put("/{code}", response_model=ProductRead, dependencies=CanUpdate)
async def update_product(
    code: str, data: ProductBody, catalog: ProductCatalogDep, session: DbSession
) -> ProductRead:
    """New terms. A draft changes in place; a published product gets a new active version
    and the previous one goes to the archive, so an archived product comes back this way.
    Applications keep the terms they were opened with."""
    product = await catalog.update(data.product(code))
    await session.commit()
    return ProductRead.of(product)


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT, dependencies=CanDelete)
async def delete_product(code: str, catalog: ProductCatalogDep, session: DbSession) -> None:
    """Off sale: a published product goes to the archive (old applications refer to it),
    a draft is deleted. Already archived — 409 `invalid_transition`."""
    await catalog.remove(code)
    await session.commit()


@router.post("/{code}/activate", response_model=ProductRead, dependencies=CanUpdate)
async def activate_product(
    code: str, catalog: ProductCatalogDep, session: DbSession
) -> ProductRead:
    """A draft goes to the catalog; anything else — 409 `invalid_transition`."""
    product = await catalog.activate(code)
    await session.commit()
    return ProductRead.of(product)


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
