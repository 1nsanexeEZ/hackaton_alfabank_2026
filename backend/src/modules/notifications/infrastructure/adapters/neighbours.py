"""Reads of other modules through their facades, for texts and recipients.

The feed is a by-product: a module that is not wired yet or an entity that is
gone degrades the text ("Заявка отправлена" without a number) instead of
failing the event and sending it to the dead letter queue."""

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError
from src.modules.applications.facade import ApplicationCardDTO, ApplicationsFacade
from src.modules.clients.facade import ClientsFacade, OrganizationSnapshotDTO
from src.modules.decision.facade import DecisionDTO, DecisionFacade, PreApprovedOfferDTO
from src.modules.identity.facade import IdentityFacade
from src.modules.notifications.application.interfaces.neighbours import FacadeLookup, Neighbours
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade, ScoringResultDTO

logger = logging.getLogger(__name__)

F = TypeVar("F")
R = TypeVar("R")


class FacadeNeighbours(Neighbours):
    def __init__(self, facades: FacadeLookup) -> None:
        self._get = facades
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
                ApplicationsFacade,  # type: ignore[type-abstract]
                lambda f: f.get_card(application_id),
            )
        return self._cards[application_id]

    async def organization(self, organization_id: UUID) -> OrganizationSnapshotDTO | None:
        if organization_id not in self._organizations:
            self._organizations[organization_id] = await self._safe(
                ClientsFacade,  # type: ignore[type-abstract]
                lambda f: f.get_snapshot(organization_id),
            )
        return self._organizations[organization_id]

    async def members(self, organization_id: UUID) -> list[UUID]:
        members = await self._safe(
            ClientsFacade,  # type: ignore[type-abstract]
            lambda f: f.list_members(organization_id),
        )
        return members or []

    async def product_name(self, code: str) -> str | None:
        if code not in self._product_names:
            product = await self._safe(
                ProductsFacade,  # type: ignore[type-abstract]
                lambda f: f.get_product(code),
            )
            self._product_names[code] = product.name if product else None
        return self._product_names[code]

    async def scoring(self, application_id: UUID) -> ScoringResultDTO | None:
        return await self._safe(
            ScoringFacade,  # type: ignore[type-abstract]
            lambda f: f.get_result(application_id),
        )

    async def decision(self, application_id: UUID) -> DecisionDTO | None:
        return await self._safe(
            DecisionFacade,  # type: ignore[type-abstract]
            lambda f: f.get_decision(application_id),
        )

    async def pre_approved(self, organization_id: UUID) -> list[PreApprovedOfferDTO]:
        offers = await self._safe(
            DecisionFacade,  # type: ignore[type-abstract]
            lambda f: f.get_pre_approved(organization_id),
        )
        return offers or []

    async def application_products(self, organization_id: UUID) -> list[str]:
        applications = await self._safe(
            ApplicationsFacade,  # type: ignore[type-abstract]
            lambda f: f.list_for_organization(organization_id),
        )
        return [a.product_code for a in applications or []]

    async def account_role(self, account_id: UUID) -> str | None:
        account = await self._safe(
            IdentityFacade,  # type: ignore[type-abstract]
            lambda f: f.get_account(account_id),
        )
        return account.role_name if account else None
