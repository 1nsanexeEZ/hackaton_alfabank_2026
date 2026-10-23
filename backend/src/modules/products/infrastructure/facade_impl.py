from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain import Money
from src.core.facades import FacadeRegistry
from src.modules.clients.facade import ClientsFacade
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.products.application import mappers
from src.modules.products.application.borrowers import BorrowerProfiles
from src.modules.products.application.services import ProductService
from src.modules.products.domain.value_objects import LoanNeed
from src.modules.products.facade import (
    EligibilityCheckDTO,
    PaymentScheduleDTO,
    ProductDTO,
    ProductTermsDTO,
    Purpose,
    RecommendationDTO,
    Repayment,
)
from src.modules.products.infrastructure.repository import SqlAlchemyProductRepository


def borrower_profiles(facades: FacadeRegistry, session: AsyncSession) -> BorrowerProfiles:
    """Enrichment is optional: without it the cash gap forecast is unknown."""
    enrichment = facades.get(EnrichmentFacade, session) if facades.has(EnrichmentFacade) else None
    return BorrowerProfiles(facades.get(ClientsFacade, session), enrichment)


class ProductsFacadeImpl:
    """Access to the organization is checked by the caller."""

    def __init__(self, session: AsyncSession, facades: FacadeRegistry) -> None:
        self._session = session
        self._facades = facades
        self._service = ProductService(SqlAlchemyProductRepository(session))

    async def get_product(self, code: str) -> ProductDTO:
        return mappers.product_dto(await self._service.get(code))

    async def list_active(self) -> list[ProductDTO]:
        return [mappers.product_dto(p) for p in await self._service.list_active()]

    async def get_terms_snapshot(self, code: str) -> ProductTermsDTO:
        return mappers.terms_dto(await self._service.terms_snapshot(code))

    async def check_eligibility(self, code: str, organization_id: UUID) -> EligibilityCheckDTO:
        product = await self._service.get_selectable(code)
        borrower = await borrower_profiles(self._facades, self._session).get(organization_id)
        return mappers.check_dto(product.check_eligibility(borrower), organization_id)

    async def recommend(
        self,
        purpose: Purpose,
        amount: Decimal,
        term_months: int,
        organization_id: UUID | None = None,
    ) -> list[RecommendationDTO]:
        need = LoanNeed(purpose, Money(amount), term_months)
        borrower = None
        if organization_id is not None:
            borrowers = borrower_profiles(self._facades, self._session)
            borrower = await borrowers.get(organization_id)
        return [
            mappers.recommendation_dto(r) for r in await self._service.recommend(need, borrower)
        ]

    def calculate_payment(
        self, amount: Decimal, term_months: int, rate: Decimal, repayment: Repayment
    ) -> PaymentScheduleDTO:
        schedule = self._service.calculate_payment(Money(amount), term_months, rate, repayment)
        return mappers.schedule_dto(schedule)
