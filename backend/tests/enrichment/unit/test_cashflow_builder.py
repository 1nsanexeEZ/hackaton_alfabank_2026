from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.enrichment import EnrichmentCompleted, FetchEnrichment
from src.modules.applications.facade import ScoringInputDTO
from src.modules.enrichment.application.use_cases.build_cashflow import CashflowBuilder
from src.modules.enrichment.application.use_cases.fetch_enrichment import FetchEnrichmentUseCase
from src.modules.enrichment.facade import CashflowForecastDTO
from src.modules.enrichment.infrastructure.adapters.statement_csv import CsvStatementParser
from tests.enrichment.unit.test_fetch_enrichment import (
    FakeBureau,
    FakeRegistry,
    FakeTax,
    InMemoryRepo,
    sources,
)
from tests.fakes import builders
from tests.fakes.messaging import FakeOutboxWriter

_SEED = Path(__file__).resolve().parents[3] / "seed" / "statements"
_CONSENT = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)


class StubApplications:
    """Отдаёт scoring_input и содержимое выписки — ровно то, что читает CashflowBuilder."""

    def __init__(self, scoring_input: ScoringInputDTO, content: bytes) -> None:
        self._scoring_input = scoring_input
        self._content = content

    async def get_scoring_input(self, application_id: UUID) -> ScoringInputDTO:
        return self._scoring_input

    async def read_document(self, application_id: UUID, document_id: UUID) -> bytes:
        return self._content


def _ivanov_scoring_input() -> ScoringInputDTO:
    # ИП Иванов: оборот ~6 млн, неравномерный — с новым кредитом прогноз уходит в разрыв.
    organization = builders.organization_snapshot(code="ivanov")
    card = builders.application_card(
        organization=organization, amount=Decimal("5000000"), term_months=24
    )
    return builders.scoring_input(card)


def _command(scoring_input: ScoringInputDTO, statement_ids: list[UUID]) -> FetchEnrichment:
    return FetchEnrichment(
        application_id=scoring_input.application_id,
        organization_id=scoring_input.organization_id,
        inn="770669871605",
        sources=["egrul", "fns", "bki"],
        bki_consent_at=_CONSENT,
        statement_document_ids=statement_ids,
    )


def _use_case(
    builder: CashflowBuilder,
) -> tuple[FetchEnrichmentUseCase, InMemoryRepo, FakeOutboxWriter]:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo, sources(FakeRegistry(), FakeTax(), FakeBureau()), FrozenClock(), builder
    )
    return use_case, repo, outbox


async def test_cashflow_added_when_statement_present() -> None:
    scoring_input = _ivanov_scoring_input()
    builder = CashflowBuilder(
        StubApplications(scoring_input, (_SEED / "ivanov.csv").read_bytes()), CsvStatementParser()
    )
    use_case, repo, outbox = _use_case(builder)

    await use_case.execute(
        _command(scoring_input, [uuid4()]), command_event_id=uuid4(), outbox=outbox
    )

    forecast = repo.added[0].data_of("statement", CashflowForecastDTO)
    assert forecast is not None
    assert forecast.gap_detected is True
    assert forecast.revenue_confirmed is True
    assert outbox.of_type(EnrichmentCompleted)[0].cash_gap_detected is True


async def test_no_cashflow_without_statement() -> None:
    scoring_input = _ivanov_scoring_input()
    builder = CashflowBuilder(StubApplications(scoring_input, b""), CsvStatementParser())
    use_case, repo, outbox = _use_case(builder)

    await use_case.execute(_command(scoring_input, []), command_event_id=uuid4(), outbox=outbox)

    assert repo.added[0].data_of("statement", CashflowForecastDTO) is None
    assert outbox.of_type(EnrichmentCompleted)[0].cash_gap_detected is None


async def test_unparseable_statement_does_not_fail_enrichment() -> None:
    scoring_input = _ivanov_scoring_input()
    builder = CashflowBuilder(
        StubApplications(scoring_input, b"foo;bar\n1;2\n"), CsvStatementParser()
    )
    use_case, repo, outbox = _use_case(builder)

    await use_case.execute(
        _command(scoring_input, [uuid4()]), command_event_id=uuid4(), outbox=outbox
    )

    snapshot = repo.added[0]
    assert snapshot.data_of("statement", CashflowForecastDTO) is None
    assert "statement" not in snapshot.sources_failed  # внутренний источник, не внешний провал
    assert set(snapshot.sources_ok) == {"egrul", "fns", "bki"}
    assert outbox.of_type(EnrichmentCompleted)[0].cash_gap_detected is None
