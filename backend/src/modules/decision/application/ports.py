"""Порты decision: хранилища решений, предодобрений и предскринов учредителей. Соседние модули
(applications, enrichment, scoring, products, clients, identity) decision читает через их
фасады прямо в use case."""

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


PrescreenStatus = Literal["passed", "failed"]


@dataclass(frozen=True, slots=True)
class PrescreenCheck:
    code: str
    passed: bool
    message: str  # для клиента


@dataclass(frozen=True, slots=True)
class FounderPrescreen:
    """Предскрин учредителя стартапа по его личной кредитной истории. Неизменяемый: повторная
    проверка — новая запись, действует последняя."""

    id: UUID
    organization_id: UUID
    founder_account_id: UUID
    founder_name: str
    status: PrescreenStatus
    reasons: tuple[PrescreenCheck, ...]
    version: str  # версия правил предскрина (scoring)
    checked_at: datetime
    valid_until: datetime

    def valid_at(self, moment: datetime) -> bool:
        return self.checked_at <= moment <= self.valid_until


class FounderPrescreenRepository(Protocol):
    async def add(self, prescreen: FounderPrescreen) -> None: ...

    async def latest_for_organization(self, organization_id: UUID) -> FounderPrescreen | None: ...
