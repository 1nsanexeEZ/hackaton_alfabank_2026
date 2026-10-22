from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from src.applications.facade import ScoringInputDTO
from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.scoring import CalculateScore, ScoreCalculated, ScoringFailed
from src.enrichment.facade import (
    CreditHistoryDTO,
    EnrichmentSnapshotDTO,
    ObligationDTO,
    RegistryExtractDTO,
    TaxProfileDTO,
)
from src.scoring.application.calculate_score import CalculateScoreUseCase
from src.scoring.domain.model import ScoringResult
from src.scoring.infrastructure.config_loader import load_scorecard
from tests.fakes import builders
from tests.fakes.applications_facade import FakeApplicationsFacade
from tests.fakes.enrichment_facade import FakeEnrichmentFacade
from tests.fakes.messaging import FakeOutboxWriter

_NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
_CARD = load_scorecard()


class InMemoryScoringRepo:
    def __init__(self) -> None:
        self.by_command: dict[UUID, ScoringResult] = {}
        self.added: list[tuple[ScoringResult, dict[str, Any]]] = []

    async def add(self, result: ScoringResult, *, input_snapshot: dict[str, Any]) -> None:
        self.by_command[result.requested_by_command] = result
        self.added.append((result, input_snapshot))

    async def get_by_command(self, command_event_id: UUID) -> ScoringResult | None:
        return self.by_command.get(command_event_id)

    async def latest_for_application(self, application_id: UUID) -> ScoringResult | None:
        for result, _ in reversed(self.added):
            if result.application_id == application_id:
                return result
        return None


def _snapshot(
    application_id: UUID,
    organization_id: UUID,
    *,
    bki: CreditHistoryDTO | None,
    sources_failed: tuple = (),
) -> EnrichmentSnapshotDTO:
    return EnrichmentSnapshotDTO(
        id=uuid4(),
        application_id=application_id,
        organization_id=organization_id,
        collected_at=_NOW,
        sources_ok=("egrul", "fns"),
        sources_failed=sources_failed,
        egrul=RegistryExtractDTO(
            inn="7701158817",
            ogrn="1",
            legal_form="ООО",
            full_name="x",
            status="active",
            registered_at=date(2019, 1, 1),
            okved_main="56.10",
            okved_extra=(),
            head_last_name="С",
            head_first_name="А",
            head_middle_name=None,
            head_position="ГД",
            founders=(),
            address="a",
            region_code="77",
            mass_address=False,
        ),
        fns=TaxProfileDTO(
            tax_arrears=Decimal(0),
            avg_headcount=12,
            reported_revenue=Decimal("47500000"),
            reported_expenses=Decimal("41000000"),
            report_year=2025,
            tax_regime="УСН",
            disqualified_head=False,
            in_msp_registry=True,
        ),
        bki=bki,
        cashflow=None,
    )


def _romashka_bki() -> CreditHistoryDTO:
    obligation = ObligationDTO(
        creditor="Банк",
        kind="loan",
        amount=Decimal("5000000"),
        balance=Decimal("3000000"),
        monthly_payment=Decimal("180000"),
        opened_at=date(2024, 1, 1),
        closes_at=None,
        overdue_days=0,
    )
    return CreditHistoryDTO(
        obligations=(obligation,),
        inquiries_last_30d=0,
        has_active_overdue=False,
        max_overdue_days_12m=0,
        total_monthly_payments=Decimal("180000"),
    )


def _setup(
    code: str = "romashka", amount: str = "3000000", term: int = 24
) -> tuple[ScoringInputDTO, FakeApplicationsFacade]:
    organization = builders.organization_snapshot(code=code)
    card = builders.application_card(
        organization=organization, amount=Decimal(amount), term_months=term
    )
    scoring_input = builders.scoring_input(card)
    apps = FakeApplicationsFacade()
    apps.scoring_inputs[scoring_input.application_id] = scoring_input
    return scoring_input, apps


def _use_case(
    apps: FakeApplicationsFacade, enrichment: FakeEnrichmentFacade
) -> tuple[CalculateScoreUseCase, InMemoryScoringRepo]:
    repo = InMemoryScoringRepo()
    use_case = CalculateScoreUseCase(repo, _CARD, apps, enrichment, FrozenClock(_NOW))
    return use_case, repo


async def test_romashka_scores_and_publishes() -> None:
    scoring_input, apps = _setup()
    enrichment = FakeEnrichmentFacade()
    enrichment.add_snapshot(
        _snapshot(scoring_input.application_id, scoring_input.organization_id, bki=_romashka_bki())
    )
    use_case, repo = _use_case(apps, enrichment)

    await use_case.execute(
        CalculateScore(application_id=scoring_input.application_id),
        command_event_id=uuid4(),
        outbox=(outbox := FakeOutboxWriter()),
    )

    assert len(repo.added) == 1
    event = outbox.of_type(ScoreCalculated)[0]
    assert event.score == 790
    assert event.risk_grade == "A"
    assert event.flags == []
    result, stored = repo.added[0]
    assert result.input_hash  # зафиксирован снимок входа
    assert stored["request"]["amount"] == "3000000"


async def test_missing_snapshot_fails() -> None:
    scoring_input, apps = _setup()
    use_case, repo = _use_case(apps, FakeEnrichmentFacade())

    await use_case.execute(
        CalculateScore(application_id=scoring_input.application_id),
        command_event_id=uuid4(),
        outbox=(outbox := FakeOutboxWriter()),
    )

    assert repo.added == []
    assert outbox.of_type(ScoreCalculated) == []
    failed = outbox.of_type(ScoringFailed)[0]
    assert failed.reason == "enrichment_snapshot_missing"


async def test_duplicate_command_reuses_result() -> None:
    scoring_input, apps = _setup()
    enrichment = FakeEnrichmentFacade()
    enrichment.add_snapshot(
        _snapshot(scoring_input.application_id, scoring_input.organization_id, bki=_romashka_bki())
    )
    use_case, repo = _use_case(apps, enrichment)
    command = CalculateScore(application_id=scoring_input.application_id)
    event_id = uuid4()
    outbox = FakeOutboxWriter()

    await use_case.execute(command, command_event_id=event_id, outbox=outbox)
    await use_case.execute(command, command_event_id=event_id, outbox=outbox)

    assert len(repo.added) == 1
    calculated = outbox.of_type(ScoreCalculated)
    assert len(calculated) == 2
    assert calculated[0].result_id == calculated[1].result_id
