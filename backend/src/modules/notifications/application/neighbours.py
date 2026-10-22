"""Reads of other modules through their facades, for texts and recipients.

The feed is a by-product: a module that is not wired yet or an entity that is
gone degrades the text ("Заявка отправлена" without a number) instead of
failing the event and sending it to the dead letter queue."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError
from src.modules.applications.facade import ApplicationCardDTO, ApplicationsFacade
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO
from src.modules.decision.facade import DecisionDTO, DecisionFacade, PreApprovedOfferDTO
from src.modules.identity.facade import IdentityFacade
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade, ScoringResultDTO

logger = logging.getLogger(__name__)

F = TypeVar("F")
R = TypeVar("R")

FacadeGetter = Callable[[type[Any]], Any]


class Neighbours:
    def __init__(self, get_facade: FacadeGetter) -> None:
        self._get = get_facade
        self._cards: dict[UUID, ApplicationCardDTO | None] = {}
        self._organizations: dict[UUID, OrganizationSnapshotDTO | None] = {}
        self._product_names: dict[str, str | None] = {}

    async def _safe(self, key: type[F], call: Callable[[F], Awaitable[R]]) -> R | None:
        try:
            facade = self._get(key)
        except LookupError:  # FacadeNotRegisteredError: the owner has not wired it yet
            logger.info("%s is not registered, the feed goes without it", key.__name__)
            return None
        try:
            return await call(facade)
        except NotFoundError:
            return None

    async def card(self, application_id: UUID) -> ApplicationCardDTO | None:
        if application_id not in self._cards:
            self._cards[application_id] = await self._safe(
                ApplicationsFacade, lambda f: f.get_card(application_id)
            )
        return self._cards[application_id]

    async def organization(self, organization_id: UUID) -> OrganizationSnapshotDTO | None:
        if organization_id not in self._organizations:
            self._organizations[organization_id] = await self._safe(
                ClientsFacade, lambda f: f.get_snapshot(organization_id)
            )
        return self._organizations[organization_id]

    async def organization_name(
        self, organization_id: UUID | None, card: ApplicationCardDTO | None = None
    ) -> str | None:
        if card is not None and card.org_snapshot is not None:
            return card.org_snapshot.name
        if organization_id is None:
            return None
        snapshot = await self.organization(organization_id)
        return snapshot.name if snapshot else None

    async def members(self, organization_id: UUID) -> list[UUID]:
        return await self._safe(ClientsFacade, lambda f: f.list_members(organization_id)) or []

    async def product_name(self, code: str) -> str | None:
        if code not in self._product_names:
            product = await self._safe(ProductsFacade, lambda f: f.get_product(code))
            self._product_names[code] = product.name if product else None
        return self._product_names[code]

    async def scoring(self, application_id: UUID) -> ScoringResultDTO | None:
        return await self._safe(ScoringFacade, lambda f: f.get_result(application_id))

    async def decision(self, application_id: UUID) -> DecisionDTO | None:
        return await self._safe(DecisionFacade, lambda f: f.get_decision(application_id))

    async def pre_approved(self, organization_id: UUID) -> list[PreApprovedOfferDTO]:
        return await self._safe(DecisionFacade, lambda f: f.get_pre_approved(organization_id)) or []

    async def application_products(self, organization_id: UUID) -> list[str]:
        applications = await self._safe(
            ApplicationsFacade, lambda f: f.list_for_organization(organization_id)
        )
        return [a.product_code for a in applications or []]

    async def account_role(self, account_id: UUID) -> str | None:
        account = await self._safe(IdentityFacade, lambda f: f.get_account(account_id))
        return account.role_name if account else None
