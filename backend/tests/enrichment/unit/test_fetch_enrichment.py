from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.enrichment import EnrichmentCompleted, FetchEnrichment
from src.enrichment.application.fetch_enrichment import FetchEnrichmentUseCase
from src.enrichment.application.ports import SourceUnavailable
from src.enrichment.application.sources import Sources
from src.enrichment.domain.snapshot import EnrichmentSnapshot
from src.enrichment.facade import CreditHistoryDTO, RegistryExtractDTO, TaxProfileDTO
from tests.fakes.messaging import FakeOutboxWriter

_CONSENT = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)


class InMemoryRepo:
    def __init__(self) -> None:
        self.by_command: dict[UUID, EnrichmentSnapshot] = {}
        self.added: list[EnrichmentSnapshot] = []

    async def add(self, snapshot: EnrichmentSnapshot) -> None:
        self.by_command[snapshot.requested_by_command] = snapshot
        self.added.append(snapshot)

    async def get_by_command(self, command_event_id: UUID) -> EnrichmentSnapshot | None:
        return self.by_command.get(command_event_id)

    async def latest_for_application(self, application_id: UUID) -> EnrichmentSnapshot | None:
        for snapshot in reversed(self.added):
            if snapshot.application_id == application_id:
                return snapshot
        return None


class FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch(self, inn: str) -> RegistryExtractDTO:
        self.calls.append(inn)
        return RegistryExtractDTO(
            inn=inn,
            ogrn="1",
            legal_form="ООО",
            full_name="x",
            status="active",
            registered_at=date(2019, 1, 1),
            okved_main="56.10",
            okved_extra=(),
            head_last_name="И",
            head_first_name="И",
            head_middle_name=None,
            head_position="ГД",
            founders=(),
            address="a",
            region_code="77",
            mass_address=False,
        )


class FakeTax:
    async def fetch(self, inn: str) -> TaxProfileDTO:
        return TaxProfileDTO(
            tax_arrears=Decimal(0),
            avg_headcount=1,
            reported_revenue=Decimal(100),
            reported_expenses=None,
            report_year=2025,
            tax_regime="УСН",
            disqualified_head=False,
            in_msp_registry=True,
        )


class FakeBureau:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, datetime]] = []

    async def fetch(self, inn: str, consent_at: datetime) -> CreditHistoryDTO:
        self.calls.append((inn, consent_at))
        if self.fail:
            raise SourceUnavailable("unavailable", "down")
        return CreditHistoryDTO(
            obligations=(),
            inquiries_last_30d=0,
            has_active_overdue=False,
            max_overdue_days_12m=0,
            total_monthly_payments=Decimal(0),
        )


def _command(consent: datetime | None = _CONSENT) -> FetchEnrichment:
    return FetchEnrichment(
        application_id=uuid4(),
        organization_id=uuid4(),
        inn="7701158817",
        sources=["egrul", "fns", "bki"],
        bki_consent_at=consent,
    )


async def test_all_sources_succeed() -> None:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo, Sources(FakeRegistry(), FakeTax(), FakeBureau()), FrozenClock()
    )
    await use_case.execute(_command(), command_event_id=uuid4(), outbox=outbox)
    completed = outbox.of_type(EnrichmentCompleted)
    assert len(completed) == 1
    assert set(completed[0].sources_ok) == {"egrul", "fns", "bki"}
    assert completed[0].sources_failed == []


async def test_bki_skipped_without_consent() -> None:
    repo, outbox, bureau = InMemoryRepo(), FakeOutboxWriter(), FakeBureau()
    use_case = FetchEnrichmentUseCase(
        repo, Sources(FakeRegistry(), FakeTax(), bureau), FrozenClock()
    )
    await use_case.execute(_command(consent=None), command_event_id=uuid4(), outbox=outbox)
    event = outbox.of_type(EnrichmentCompleted)[0]
    assert set(event.sources_ok) == {"egrul", "fns"}
    assert "bki" not in event.sources_ok
    assert "bki" not in event.sources_failed
    assert bureau.calls == []  # БКИ без согласия не запрашивается (218-ФЗ)


async def test_partial_failure_reports_failed_source() -> None:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo, Sources(FakeRegistry(), FakeTax(), FakeBureau(fail=True)), FrozenClock()
    )
    await use_case.execute(_command(), command_event_id=uuid4(), outbox=outbox)
    event = outbox.of_type(EnrichmentCompleted)[0]
    assert set(event.sources_ok) == {"egrul", "fns"}
    assert event.sources_failed == ["bki"]


async def test_duplicate_command_reuses_snapshot_and_republishes() -> None:
    repo, outbox, registry = InMemoryRepo(), FakeOutboxWriter(), FakeRegistry()
    use_case = FetchEnrichmentUseCase(
        repo, Sources(registry, FakeTax(), FakeBureau()), FrozenClock()
    )
    command, event_id = _command(), uuid4()
    await use_case.execute(command, command_event_id=event_id, outbox=outbox)
    await use_case.execute(command, command_event_id=event_id, outbox=outbox)
    assert len(repo.added) == 1
    assert registry.calls == ["7701158817"]
    completed = outbox.of_type(EnrichmentCompleted)
    assert len(completed) == 2
    assert completed[0].snapshot_id == completed[1].snapshot_id
