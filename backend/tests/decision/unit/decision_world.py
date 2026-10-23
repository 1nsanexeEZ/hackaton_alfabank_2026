"""Мир golden-тестов политики на фейковых фасадах, данные — демо §9.

Чтобы цифры совпали со сквозными тестами, всё, кроме самих фасадов, — настоящее:
- продукты — каталог из `seed/products.py`, eligibility — доменная проверка products;
- снимок обогащения — настоящие HTTP-адаптеры enrichment поверх записанных ответов
  external-mocks (`tests/assessment/fixtures/external_mocks.json`), прогноз кассового разрыва —
  настоящий `CashflowBuilder` по `seed/statements/<код>.csv`. Мир policy_v1 опрашивает ЕГРЮЛ,
  ФНС и БКИ, как в момент её выхода; мир policy_v2 — все источники, руководитель по реестру
  дал согласие на свою кредитную историю. Проверка по 115-ФЗ (`aml`) — в каждом мире, как в
  конвейере на каждой заявке; policy_v1–v5 её не читают;
- результат скоринга — настоящая модель на том же входе, что собрал бы scoring: действующая
  PD-модель или, для golden policy_v1 и policy_v2, scorecard_v1 их времени.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from seed.demo_data import ACCOUNTS
from seed.products import catalog
from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.enrichment import FetchEnrichment, PersonRef
from src.modules.applications.facade import CollateralDTO, DocumentDTO, InfoRequestDTO
from src.modules.clients.facade import OrganizationSnapshotDTO
from src.modules.decision.application.input_builder import DecisionInputBuilder
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.enrichment.application.use_cases.build_cashflow import CashflowBuilder
from src.modules.enrichment.application.use_cases.fetch_enrichment import FetchEnrichmentUseCase
from src.modules.enrichment.application.use_cases.get_snapshot import GetSnapshotUseCase
from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot
from src.modules.enrichment.infrastructure.adapters.statement_csv import CsvStatementParser
from src.modules.products.application.borrowers import borrower_profile
from src.modules.products.application.mappers import check_dto, product_dto
from src.modules.scoring.application.input_builder import build_scoring_input
from src.modules.scoring.application.ports import ScoringModel
from src.modules.scoring.facade import FactorDTO, MlScoreDTO, ScoringResultDTO
from src.modules.scoring.infrastructure.config_loader import default_model, default_quality
from src.modules.scoring.infrastructure.ml_loader import default_ml_model
from tests.assessment.assessment_world import mock_sources
from tests.fakes import builders
from tests.fakes.applications_facade import FakeApplicationsFacade
from tests.fakes.enrichment_facade import FakeEnrichmentFacade
from tests.fakes.messaging import FakeOutboxWriter
from tests.fakes.products_facade import FakeProductsFacade
from tests.fakes.scoring_facade import FakeScoringFacade

NOW = builders.NOW
_BACKEND = Path(__file__).resolve().parents[3]
_STATEMENTS = _BACKEND / "seed" / "statements"
_CONSENT = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
V1_SOURCES = ("egrul", "fns", "bki")
ALL_SOURCES = ("egrul", "fns", "bki", "statement", "gir_bo", "kontur", "bki_head")
_CATALOG = {product.code.value: product for product in catalog()}


@dataclass(frozen=True)
class Scenario:
    code: str
    product: str
    amount: str
    term: int
    statement: bool = False
    collateral: tuple[str, str] | None = None  # (тип, стоимость)
    revenue_info_answered: bool = False


SCENARIOS: dict[str, Scenario] = {
    "s1_romashka": Scenario("romashka", "UNSECURED", "3000000", 24),
    "s2_ivanov": Scenario("ivanov", "UNSECURED", "5000000", 24, statement=True),
    "s3_vector": Scenario("vector", "CREDIT_LINE", "10000000", 24),
    "s4_zakat": Scenario("zakat", "UNSECURED", "2000000", 12),
    "s5a_progress": Scenario("progress", "CREDIT_LINE", "8000000", 24),
    "s5b_progress": Scenario(
        "progress", "CREDIT_LINE", "8000000", 24, statement=True, revenue_info_answered=True
    ),
    "s6_sboy": Scenario("sboy", "UNSECURED", "1000000", 12),
    "s7_romashka_mortgage": Scenario(
        "romashka", "MORTGAGE", "30000000", 120, collateral=("real_estate", "50000000")
    ),
}


@dataclass
class DecisionWorld:
    application_id: UUID
    organization_id: UUID
    applications: FakeApplicationsFacade
    enrichment: FakeEnrichmentFacade
    scoring: FakeScoringFacade
    products: FakeProductsFacade

    def builder(self, policy: CreditPolicy) -> DecisionInputBuilder:
        return DecisionInputBuilder(
            policy, self.applications, self.enrichment, self.scoring, self.products
        )

    @property
    def result(self) -> ScoringResultDTO:
        return self.scoring.results[self.application_id]


async def build_world(
    name: str,
    *,
    sources: Sequence[str] = V1_SOURCES,
    head_consent: bool = False,
    scoring_model: ScoringModel | None = None,
    automated_decision_consent: bool = False,
) -> DecisionWorld:
    """`head_consent` — руководитель по реестру дал личное согласие на запрос своего БКИ;
    `scoring_model` — чем считать скоринг, по умолчанию действующая PD-модель и рядом с ней
    ML-модель (у старых моделей golden policy_v1 и policy_v2 ML-оценки нет)."""
    scenario = SCENARIOS[name]
    organization = builders.organization_snapshot(scenario.code)
    products = _products(organization)

    terms = builders.product_terms(await products.get_product(scenario.product))
    documents: tuple[DocumentDTO, ...] = ()
    if scenario.statement:
        documents = (
            DocumentDTO(
                id=uuid4(),
                type="bank_statement",
                filename=f"{scenario.code}.csv",
                content_type="text/csv",
                size_bytes=1,
                status="accepted",
                uploaded_by=None,
                uploaded_at=NOW,
            ),
        )
    collateral = None
    if scenario.collateral is not None:
        kind, value = scenario.collateral
        collateral = CollateralDTO(kind, "Залог по заявке", Decimal(value), "self")  # type: ignore[arg-type]
    info_requests: tuple[InfoRequestDTO, ...] = ()
    if scenario.revenue_info_answered:
        info_requests = (
            InfoRequestDTO(
                id=uuid4(),
                requested_fields=(),
                requested_documents=("bank_statement",),
                comment="Подтвердите выручку выпиской по счёту за 6 месяцев.",
                created_at=NOW,
                due_at=None,
                status="answered",
                answered_at=NOW,
            ),
        )
    card = builders.application_card(
        organization=organization,
        amount=Decimal(scenario.amount),
        term_months=scenario.term,
        product_code=scenario.product,
        product_terms=terms,
        collateral=collateral,
        documents=documents,
        info_requests=info_requests,
    )

    applications = FakeApplicationsFacade()
    applications.add_card(card)
    applications.scoring_inputs[card.id] = builders.scoring_input(
        card,
        statement_document_ids=tuple(d.id for d in documents),
        automated_decision_consent_at=NOW if automated_decision_consent else None,
    )
    for document in documents:
        applications.add_document_content(
            document.id, (_STATEMENTS / f"{scenario.code}.csv").read_bytes()
        )

    enrichment = FakeEnrichmentFacade()
    head = registry_head(scenario.code)
    snapshot = enrichment.add_snapshot(
        await _enrich(applications, card.id, sources, head, head_consent)
    )

    scoring = FakeScoringFacade()
    source = await applications.get_scoring_input(card.id)
    model = scoring_model or default_model()
    scoring_input = build_scoring_input(source, snapshot)
    output = model.calculate(scoring_input)
    ml = default_ml_model().predict(scoring_input) if scoring_model is None else None
    # Качество данных — у действующей модели, как в CalculateScore; у старых его нет.
    quality = (
        default_quality().assess(scoring_input.sources_failed, output.data_completeness)
        if scoring_model is None
        else None
    )
    scoring.add_result(
        ScoringResultDTO(
            id=uuid4(),
            application_id=card.id,
            model_version=model.version,
            score=output.score,
            grade=output.grade,
            factors=tuple(
                FactorDTO(f.code, f.value, f.bin, f.points, f.direction, f.client_hint)
                for f in output.factors
            ),
            flags=output.flags,
            data_completeness=output.data_completeness,
            computed_at=NOW,
            segment=output.segment,
            scorecard=output.scorecard,
            pd_12m=output.pd_12m,
            reason_codes=output.reason_codes,
            ml=MlScoreDTO(
                model_version=ml.model_version,
                pd_12m=ml.pd_12m,
                score=ml.score,
                grade=ml.grade,
                factors=tuple(
                    FactorDTO(f.code, f.value, f.bin, f.points, f.direction) for f in ml.factors
                ),
                reason_codes=ml.reason_codes,
            )
            if ml is not None
            else None,
            quality=quality.level if quality is not None else None,
            quality_reasons=quality.reasons if quality is not None else (),
        )
    )
    return DecisionWorld(card.id, organization.id, applications, enrichment, scoring, products)


def _products(organization: OrganizationSnapshotDTO) -> FakeProductsFacade:
    fake = FakeProductsFacade()
    profile = borrower_profile(organization)
    for product in _CATALOG.values():
        fake.add_product(product_dto(product))
        fake.set_eligibility(check_dto(product.check_eligibility(profile), organization.id))
    return fake


def registry_head(company_code: str) -> PersonRef | None:
    """Участник, чьё ФИО совпало с руководителем в реестре (как `get_registry_head`)."""
    for number, account in enumerate(ACCOUNTS, start=1):
        for membership in account.memberships:
            if (
                membership.company_code == company_code
                and membership.role in ("director", "owner")
                and membership.authority == "registry"
            ):
                person = account.person
                return PersonRef(
                    account_id=UUID(int=number),
                    last_name=person.last_name,
                    first_name=person.first_name,
                    middle_name=person.middle_name,
                )
    return None


async def _enrich(
    applications: FakeApplicationsFacade,
    application_id: UUID,
    sources: Sequence[str],
    head: PersonRef | None,
    head_consent: bool,
) -> Any:
    source = await applications.get_scoring_input(application_id)
    repository = _InMemorySnapshots()
    use_case = FetchEnrichmentUseCase(
        repository,
        mock_sources(),
        FrozenClock(NOW),
        CashflowBuilder(applications, CsvStatementParser()),
    )
    command = FetchEnrichment(
        application_id=application_id,
        organization_id=source.organization_id,
        inn=source.organization.inn,
        sources=list(dict.fromkeys((*sources, "aml"))),
        bki_consent_at=_CONSENT,
        statement_document_ids=list(source.statement_document_ids),
        head=head,
        head_bki_consent_at=_CONSENT if head_consent and head is not None else None,
    )
    await use_case.execute(command, command_event_id=uuid4(), outbox=FakeOutboxWriter())
    return await GetSnapshotUseCase(repository).execute(application_id)


class _InMemorySnapshots:
    def __init__(self) -> None:
        self.added: list[EnrichmentSnapshot] = []

    async def add(self, snapshot: EnrichmentSnapshot) -> None:
        self.added.append(snapshot)

    async def get_by_command(self, command_event_id: UUID) -> EnrichmentSnapshot | None:
        return None

    async def latest_for_application(self, application_id: UUID) -> EnrichmentSnapshot | None:
        return self.added[-1] if self.added else None


def with_score(world: DecisionWorld, **overrides: Any) -> None:
    """Подменить результат скоринга (грейд, флаги) — для проверок отдельных правил."""
    world.scoring.add_result(replace(world.result, **overrides))
