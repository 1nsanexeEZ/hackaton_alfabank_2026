"""Порты decision: хранилища решений, предодобрений, предскринов учредителей и проектных оценок
стартапов. Соседние модули (applications, enrichment, scoring, products, clients, identity)
decision читает через их фасады прямо в use case."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from src.modules.decision.domain.result import DecisionResult

# estimate — оценка компании без заявки (RecalculatePreApproved); project — проектная оценка
# стартапа по бизнес-плану и финмодели (AssessProject).
PreApprovalBasis = Literal["estimate", "full", "project"]


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
        """Пересчёт перезаписывает предложения компании, кроме проектных: чего нет в `offers` —
        удаляется. Проектное предложение стартапа живёт по своей оценке."""
        ...

    async def replace_project_offers(
        self, organization_id: UUID, offers: Sequence[PreApprovedOffer]
    ) -> None:
        """Проектная оценка перезаписывает только предложения с `basis = project`."""
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


ProjectStatus = Literal["passed", "failed"]


@dataclass(frozen=True, slots=True)
class ProjectCheck:
    code: str  # founder_prescreen | industry | dscr | own_funds | coverage | product_amount
    passed: bool
    message: str  # для клиента, без порогов


@dataclass(frozen=True, slots=True)
class ProjectFigures:
    """Цифры проектной оценки для андеррайтера: что просили, на каких условиях считали платёж и
    что получилось на запрошенной сумме."""

    requested_amount: Decimal
    term_months: int
    rate: Decimal  # % годовых, по которой считали платёж: верх коридора продукта
    cash_flow: Decimal  # выручка − расходы за горизонт финмодели
    debt_service: Decimal  # платежи по кредиту за тот же горизонт
    dscr: Decimal | None
    own_share: Decimal
    coverage: Decimal
    capacity: Decimal  # сколько проект выдерживает по scoring, без рамок продукта


@dataclass(frozen=True, slots=True)
class ProjectAssessment:
    """Проектная оценка стартапа по бизнес-плану и финмодели. Неизменяемая: повторная оценка —
    новая запись, действует последняя. `passed` — предложение STARTUP с `basis = project`."""

    id: UUID
    organization_id: UUID
    product_code: str
    plan_revision: int  # ревизия бизнес-плана, по которой оценивали
    status: ProjectStatus
    reasons: tuple[ProjectCheck, ...]
    figures: ProjectFigures
    # Предодобрено: в рамках продукта и шага суммы; None — предложить нечего.
    max_amount: Decimal | None
    version: str  # версия правил проектной оценки (scoring)
    checked_at: datetime
    valid_until: datetime

    def valid_at(self, moment: datetime) -> bool:
        return self.checked_at <= moment <= self.valid_until


class ProjectAssessmentRepository(Protocol):
    async def add(self, assessment: ProjectAssessment) -> None: ...

    async def latest_for_organization(self, organization_id: UUID) -> ProjectAssessment | None: ...
