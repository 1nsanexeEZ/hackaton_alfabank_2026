"""Порты decision: хранилища решений и предодобрений. Соседние модули (applications,
enrichment, scoring, products, clients) decision читает через их фасады прямо в use case."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from src.modules.decision.domain.result import DecisionResult

PreApprovalBasis = Literal["estimate", "full"]


@dataclass(frozen=True, slots=True)
class PreApprovedOffer:
    """Предодобренное предложение компании по продукту; одно на пару (компания, продукт)."""

    organization_id: UUID
    product_code: str
    max_amount: Decimal
    rate_from: Decimal
    term_max_months: int
    basis: PreApprovalBasis
    factors_summary: tuple[str, ...]
    valid_until: date
    computed_at: datetime


class DecisionRepository(Protocol):
    async def add(self, result: DecisionResult) -> None:
        """Новое решение становится последним по заявке."""
        ...

    async def get_by_command(self, command_event_id: UUID) -> DecisionResult | None: ...

    async def latest_for_application(self, application_id: UUID) -> DecisionResult | None: ...

    async def latest_automatic(self, application_id: UUID) -> DecisionResult | None: ...


class PreApprovedOfferRepository(Protocol):
    async def replace_for_organization(
        self, organization_id: UUID, offers: Sequence[PreApprovedOffer]
    ) -> None:
        """Пересчёт перезаписывает все предложения компании: чего нет в `offers` — удаляется."""
        ...

    async def list_for_organization(self, organization_id: UUID) -> list[PreApprovedOffer]: ...
