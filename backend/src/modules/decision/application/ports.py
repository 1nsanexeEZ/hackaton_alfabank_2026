"""Порты decision: хранилища решений, предодобрений, предскринов учредителей, проектных оценок
стартапов и версий политики, транзакция ночного пакета. Соседние модули (applications,
enrichment, scoring, products, clients, identity) decision читает через их фасады прямо в use
case."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from src.core.messaging.outbox import OutboxWriter
from src.core.uow import UnitOfWork
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.domain.policy_version import PolicyVersion
from src.modules.decision.domain.result import DecisionResult
from src.modules.market.facade import MarketFacade
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade

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
    # Ключевая, с которой посчитано; None — проектное предложение или посчитано до того, как
    # предложение стало её помнить (такие считаются устаревшими).
    key_rate: Decimal | None = None


class DecisionRepository(Protocol):
    async def add(self, result: DecisionResult) -> None:
        """Новое решение становится последним по заявке."""
        ...

    async def get_by_command(self, command_event_id: UUID) -> DecisionResult | None: ...

    async def latest_for_application(self, application_id: UUID) -> DecisionResult | None: ...

    async def latest_automatic(self, application_id: UUID) -> DecisionResult | None: ...


class DecisionHistory(Protocol):
    """Прошлые автоматические решения — для примерки версии политики."""

    async def recent_automatic(self, limit: int) -> list[DecisionResult]:
        """Последнее автоматическое решение по каждой из `limit` заявок, где такие решения
        свежее всего; ручные решения не берём."""
        ...


class PolicyVersionRepository(Protocol):
    """Версии политики админа (`decision_policy_versions`); встроенной здесь нет."""

    async def list_all(self) -> list[PolicyVersion]: ...

    async def get(self, version: str) -> PolicyVersion | None: ...

    async def codes(self) -> list[str]: ...

    async def active_version(self) -> str | None:
        """Код активной версии — один короткий запрос на команду; None — действует встроенная."""
        ...

    async def add(self, version: PolicyVersion) -> None: ...

    async def save(self, version: PolicyVersion) -> None: ...

    async def delete(self, version: str) -> None: ...


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

    async def organizations_expiring_by(self, day: date, limit: int) -> list[UUID]:
        """Компании, у которых хоть одно предложение по оценке без заявки действует не дольше
        `day` (и уже истекшие); раньше истекающие — первыми. Проектные не считаются: их не
        продлить пересчётом, только новой проектной оценкой."""
        ...

    async def organizations_priced_at_other_key_rate(
        self, key_rate: Decimal, limit: int
    ) -> list[UUID]:
        """Компании, у которых хоть одно предложение по оценке без заявки посчитано не по этой
        ключевой (или ставка не записана). Проектные не считаются, как и в
        `organizations_expiring_by`."""
        ...


class PreApprovalTransaction(UnitOfWork, Protocol):
    """Транзакция на своей сессии — вне запроса и обработчика Kafka (ночной пакет): вход
    открывает сессию, выход откатывает незакоммиченное и закрывает её. Хранилище, фасады
    соседей и outbox привязаны к этой сессии."""

    @property
    def offers(self) -> PreApprovedOfferRepository: ...

    @property
    def policy_versions(self) -> PolicyVersionRepository: ...

    @property
    def clients(self) -> ClientsFacade: ...

    @property
    def products(self) -> ProductsFacade: ...

    @property
    def scoring(self) -> ScoringFacade: ...

    @property
    def market(self) -> MarketFacade: ...

    @property
    def outbox(self) -> OutboxWriter: ...


# Новая транзакция на каждый вызов: пакет пересчитывает каждую компанию в своей.
PreApprovalTransactions = Callable[[], PreApprovalTransaction]


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
