from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from src.core.domain.clock import FrozenClock
from src.core.messaging.contracts.enrichment import (
    EnrichmentCompleted,
    EnrichmentFailed,
    FetchEnrichment,
    PersonRef,
)
from src.modules.enrichment.application.interfaces.sources import Sources
from src.modules.enrichment.application.use_cases.fetch_enrichment import FetchEnrichmentUseCase
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot
from src.modules.enrichment.facade import (
    AccountingPeriodDTO,
    AccountingReportsDTO,
    ArbitrationDTO,
    BankStopListDTO,
    BankTurnoverDTO,
    CounterpartyRiskDTO,
    CreditHistoryDTO,
    EnforcementDTO,
    GovContractsDTO,
    ObligationDTO,
    PersonDTO,
    RegistryExtractDTO,
    TaxProfileDTO,
    TurnoverMonthDTO,
)
from tests.fakes.aml_sources import FakeAmlLists, FakePep, FakeZsk
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


class FakeAccounting:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def fetch(self, inn: str) -> AccountingReportsDTO:
        if self.fail:
            raise SourceUnavailable("timeout", "таймаут источника")
        amounts = dict.fromkeys(
            (f for f in AccountingPeriodDTO.__dataclass_fields__ if f != "year"), Decimal(1000)
        )
        return AccountingReportsDTO(True, None, (AccountingPeriodDTO(year=2025, **amounts),))


class FakeCounterparty:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def fetch(self, inn: str) -> CounterpartyRiskDTO:
        if self.fail:
            raise SourceUnavailable("unavailable", "HTTP 503")
        return CounterpartyRiskDTO(
            reliability="green",
            notes=(),
            arbitration=ArbitrationDTO(0, 0, Decimal(0)),
            enforcement=EnforcementDTO(0, Decimal(0)),
            bankruptcy_messages=(),
            gov_contracts=GovContractsDTO(0, Decimal(0)),
            active_pledges=0,
        )


class FakePersonBureau:
    def __init__(self, *, overdue_days: int = 0) -> None:
        self.overdue_days = overdue_days
        self.calls: list[tuple[PersonDTO, datetime]] = []

    async def fetch(self, person: PersonDTO, consent_at: datetime) -> CreditHistoryDTO:
        self.calls.append((person, consent_at))
        loan = ObligationDTO(
            creditor="АО «Банк»",
            kind="consumer",
            amount=Decimal(800000),
            balance=Decimal(650000),
            monthly_payment=Decimal(27000),
            opened_at=date(2024, 3, 1),
            closes_at=date(2028, 3, 1),
            overdue_days=self.overdue_days,
        )
        return CreditHistoryDTO(
            obligations=(loan,),
            inquiries_last_30d=0,
            has_active_overdue=self.overdue_days > 0,
            max_overdue_days_12m=self.overdue_days,
            total_monthly_payments=Decimal(27000),
        )


class FakeBankStopList:
    def __init__(self, *, reason: str | None = None, fail: bool = False) -> None:
        self.reason = reason
        self.fail = fail

    async def fetch(self, inn: str) -> BankStopListDTO:
        if self.fail:
            raise SourceUnavailable("unavailable", "HTTP 503")
        if self.reason is None:
            return BankStopListDTO(listed=False)
        return BankStopListDTO(listed=True, reason=self.reason, listed_at=date(2025, 6, 1))


class FakeBankTurnover:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def fetch(self, inn: str) -> BankTurnoverDTO:
        if self.fail:
            raise SourceUnavailable("unavailable", "HTTP 503")
        months = tuple(
            TurnoverMonthDTO(f"2025-{m:02d}", Decimal(4_000_000), Decimal(3_400_000))
            for m in range(1, 13)
        )
        return BankTurnoverDTO(client_since=date(2019, 1, 15), months=months)


def sources(
    registry: object | None = None,
    tax: object | None = None,
    bureau: object | None = None,
    accounting: object | None = None,
    counterparty: object | None = None,
    person_bureau: object | None = None,
    aml_lists: object | None = None,
    pep: object | None = None,
    zsk: object | None = None,
    bank_stop_list: object | None = None,
    bank_turnover: object | None = None,
) -> Sources:
    """Все источники; не переданный — рабочий фейк."""
    return Sources(
        registry or FakeRegistry(),  # type: ignore[arg-type]
        tax or FakeTax(),  # type: ignore[arg-type]
        bureau or FakeBureau(),  # type: ignore[arg-type]
        accounting or FakeAccounting(),  # type: ignore[arg-type]
        counterparty or FakeCounterparty(),  # type: ignore[arg-type]
        person_bureau or FakePersonBureau(),  # type: ignore[arg-type]
        aml_lists or FakeAmlLists(),  # type: ignore[arg-type]
        pep or FakePep(),  # type: ignore[arg-type]
        zsk or FakeZsk(),  # type: ignore[arg-type]
        bank_stop_list or FakeBankStopList(),  # type: ignore[arg-type]
        bank_turnover or FakeBankTurnover(),  # type: ignore[arg-type]
    )


async def test_bank_stop_list_is_requested_without_consent() -> None:
    """Стоп-лист — собственные данные банка: запрашивается и без согласия на БКИ."""
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo, sources(bank_stop_list=FakeBankStopList(reason="Подложные документы")), FrozenClock()
    )
    command = FetchEnrichment(
        application_id=uuid4(),
        organization_id=uuid4(),
        inn="7701158817",
        sources=["egrul", "bki", "bank_stop_list"],
    )

    await use_case.execute(command, command_event_id=uuid4(), outbox=outbox)

    [snapshot] = repo.by_command.values()
    stop = snapshot.data_of("bank_stop_list", BankStopListDTO)
    assert stop is not None and stop.listed and stop.reason == "Подложные документы"
    assert "bank_stop_list" in snapshot.sources_ok and "bki" in snapshot.sources_skipped


async def test_bank_stop_list_down_is_a_failed_source() -> None:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo, sources(bank_stop_list=FakeBankStopList(fail=True)), FrozenClock()
    )
    command = FetchEnrichment(
        application_id=uuid4(),
        organization_id=uuid4(),
        inn="7701158817",
        sources=["egrul", "bank_stop_list"],
    )

    await use_case.execute(command, command_event_id=uuid4(), outbox=outbox)

    [snapshot] = repo.by_command.values()
    assert "bank_stop_list" in snapshot.sources_failed and "egrul" in snapshot.sources_ok


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
        repo, sources(FakeRegistry(), FakeTax(), FakeBureau()), FrozenClock()
    )
    await use_case.execute(_command(), command_event_id=uuid4(), outbox=outbox)
    completed = outbox.of_type(EnrichmentCompleted)
    assert len(completed) == 1
    assert set(completed[0].sources_ok) == {"egrul", "fns", "bki"}
    assert completed[0].sources_failed == []


async def test_bki_skipped_without_consent() -> None:
    repo, outbox, bureau = InMemoryRepo(), FakeOutboxWriter(), FakeBureau()
    use_case = FetchEnrichmentUseCase(
        repo, sources(FakeRegistry(), FakeTax(), bureau), FrozenClock()
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
        repo, sources(FakeRegistry(), FakeTax(), FakeBureau(fail=True)), FrozenClock()
    )
    await use_case.execute(_command(), command_event_id=uuid4(), outbox=outbox)
    event = outbox.of_type(EnrichmentCompleted)[0]
    assert set(event.sources_ok) == {"egrul", "fns"}
    assert event.sources_failed == ["bki"]


async def test_duplicate_command_reuses_snapshot_and_republishes() -> None:
    repo, outbox, registry = InMemoryRepo(), FakeOutboxWriter(), FakeRegistry()
    use_case = FetchEnrichmentUseCase(
        repo, sources(registry, FakeTax(), FakeBureau()), FrozenClock()
    )
    command, event_id = _command(), uuid4()
    await use_case.execute(command, command_event_id=event_id, outbox=outbox)
    await use_case.execute(command, command_event_id=event_id, outbox=outbox)
    assert len(repo.added) == 1
    assert registry.calls == ["7701158817"]
    completed = outbox.of_type(EnrichmentCompleted)
    assert len(completed) == 2
    assert completed[0].snapshot_id == completed[1].snapshot_id


class DownSource:
    """Источник, до которого нет сети: любой запрос — `unavailable`."""

    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, inn: str, *args: object) -> RegistryExtractDTO:
        self.calls += 1
        raise SourceUnavailable("unavailable", "connection refused")


async def test_all_sources_down_publishes_failed() -> None:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo,
        sources(DownSource(), DownSource(), DownSource()),
        FrozenClock(),  # type: ignore[arg-type]
    )
    await use_case.execute(_command(), command_event_id=uuid4(), outbox=outbox)

    assert outbox.of_type(EnrichmentCompleted) == []
    failed = outbox.of_type(EnrichmentFailed)
    assert len(failed) == 1
    assert (
        failed[0].reason
        == "all_sources_failed: egrul=unavailable, fns=unavailable, bki=unavailable"
    )
    assert len(repo.added) == 1  # снимок с ошибками сохранён для аудита


async def test_registry_and_tax_down_without_bki_consent_fails() -> None:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo,
        sources(DownSource(), DownSource(), FakeBureau()),
        FrozenClock(),  # type: ignore[arg-type]
    )
    await use_case.execute(_command(consent=None), command_event_id=uuid4(), outbox=outbox)

    reason = outbox.of_type(EnrichmentFailed)[0].reason
    assert "bki=no_consent" in reason


async def test_duplicate_failed_command_republishes_failed() -> None:
    repo, outbox, registry = InMemoryRepo(), FakeOutboxWriter(), DownSource()
    use_case = FetchEnrichmentUseCase(
        repo,
        sources(registry, DownSource(), DownSource()),
        FrozenClock(),  # type: ignore[arg-type]
    )
    command, event_id = _command(), uuid4()
    await use_case.execute(command, command_event_id=event_id, outbox=outbox)
    await use_case.execute(command, command_event_id=event_id, outbox=outbox)

    assert len(repo.added) == 1
    assert registry.calls == 1
    assert len(outbox.of_type(EnrichmentFailed)) == 2


async def test_one_source_alive_is_still_completed() -> None:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo,
        sources(FakeRegistry(), DownSource(), DownSource()),
        FrozenClock(),  # type: ignore[arg-type]
    )
    await use_case.execute(_command(), command_event_id=uuid4(), outbox=outbox)

    assert outbox.of_type(EnrichmentFailed) == []
    event = outbox.of_type(EnrichmentCompleted)[0]
    assert event.sources_ok == ["egrul"]
    assert set(event.sources_failed) == {"fns", "bki"}


# --- ГИР БО, Контур, БКИ руководителя ---------------------------------------------------------

_HEAD = PersonRef(
    account_id=UUID(int=1), last_name="Смирнова", first_name="Анна", middle_name="Сергеевна"
)
_ALL = [
    "egrul",
    "fns",
    "bki",
    "statement",
    "gir_bo",
    "kontur",
    "bki_head",
    "aml",
    "bank_stop_list",
    "bank_turnover",
]


def _full_command(
    head: PersonRef | None = _HEAD, head_consent: datetime | None = _CONSENT
) -> FetchEnrichment:
    return FetchEnrichment(
        application_id=uuid4(),
        organization_id=uuid4(),
        inn="7701158817",
        sources=_ALL,
        bki_consent_at=_CONSENT,
        head=head,
        head_bki_consent_at=head_consent,
    )


async def test_default_command_asks_every_source() -> None:
    command = FetchEnrichment(application_id=uuid4(), organization_id=uuid4(), inn="7701158817")
    assert command.sources == _ALL


async def test_every_source_without_statements() -> None:
    repo, outbox, person = InMemoryRepo(), FakeOutboxWriter(), FakePersonBureau(overdue_days=45)
    use_case = FetchEnrichmentUseCase(repo, sources(person_bureau=person), FrozenClock())

    await use_case.execute(_full_command(), command_event_id=uuid4(), outbox=outbox)

    event = outbox.of_type(EnrichmentCompleted)[0]
    assert event.sources_ok == [
        "egrul",
        "fns",
        "bki",
        "gir_bo",
        "kontur",
        "bki_head",
        "aml",
        "bank_stop_list",
        "bank_turnover",
    ]
    assert event.sources_failed == [] and event.cash_gap_detected is None
    snapshot = repo.added[0]
    turnover = snapshot.data_of("bank_turnover", BankTurnoverDTO)
    assert turnover is not None and turnover.annual_inflow == Decimal(48_000_000)
    assert "statement" not in snapshot.results  # выписок нет — прогноза нет, и это не сбой
    head = snapshot.data_of("bki_head", CreditHistoryDTO)
    assert head is not None and head.obligations[0].overdue_days == 45
    assert snapshot.data_of("gir_bo", AccountingReportsDTO) is not None
    assert snapshot.data_of("kontur", CounterpartyRiskDTO) is not None
    [(query, consent_at)] = person.calls
    assert query == PersonDTO("Смирнова", "Анна", "Сергеевна", "7701158817")
    assert consent_at == _CONSENT


async def test_head_bureau_skipped_without_the_head_consent() -> None:
    repo, outbox, person = InMemoryRepo(), FakeOutboxWriter(), FakePersonBureau()
    use_case = FetchEnrichmentUseCase(repo, sources(person_bureau=person), FrozenClock())

    await use_case.execute(
        _full_command(head_consent=None), command_event_id=uuid4(), outbox=outbox
    )

    event = outbox.of_type(EnrichmentCompleted)[0]
    assert "bki_head" not in event.sources_ok and "bki_head" not in event.sources_failed
    result = repo.added[0].results["bki_head"]
    assert result.status == "skipped" and result.error is not None
    assert result.error.kind == "no_consent"
    assert repo.added[0].sources_skipped == ["bki_head"]
    assert person.calls == []  # без согласия руководителя его БКИ не запрашивается


async def test_head_bureau_skipped_without_a_head() -> None:
    repo, outbox, person = InMemoryRepo(), FakeOutboxWriter(), FakePersonBureau()
    use_case = FetchEnrichmentUseCase(repo, sources(person_bureau=person), FrozenClock())

    await use_case.execute(_full_command(head=None), command_event_id=uuid4(), outbox=outbox)

    error = repo.added[0].results["bki_head"].error
    assert error is not None and error.kind == "no_head"
    assert person.calls == []


async def test_old_command_without_head_fields_skips_head_bureau() -> None:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(repo, sources(), FrozenClock())
    command = FetchEnrichment.model_validate(
        {
            "application_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "inn": "7701158817",
            "sources": _ALL,
            "bki_consent_at": _CONSENT.isoformat(),
        }
    )

    await use_case.execute(command, command_event_id=uuid4(), outbox=outbox)

    assert repo.added[0].results["bki_head"].status == "skipped"
    assert outbox.of_type(EnrichmentCompleted)[0].sources_failed == []


async def test_new_sources_fail_partially() -> None:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    use_case = FetchEnrichmentUseCase(
        repo,
        sources(accounting=FakeAccounting(fail=True), counterparty=FakeCounterparty(fail=True)),
        FrozenClock(),
    )

    await use_case.execute(_full_command(), command_event_id=uuid4(), outbox=outbox)

    event = outbox.of_type(EnrichmentCompleted)[0]
    assert event.sources_failed == ["gir_bo", "kontur"]
    assert event.sources_ok == [
        "egrul",
        "fns",
        "bki",
        "bki_head",
        "aml",
        "bank_stop_list",
        "bank_turnover",
    ]
    assert repo.added[0].results["gir_bo"].error.kind == "timeout"  # type: ignore[union-attr]


async def test_every_external_source_down_fails_without_statement() -> None:
    repo, outbox = InMemoryRepo(), FakeOutboxWriter()
    down = DownSource()
    use_case = FetchEnrichmentUseCase(
        repo,
        sources(down, down, down, down, down, down, bank_stop_list=down, bank_turnover=down),
        FrozenClock(),
    )

    await use_case.execute(_full_command(), command_event_id=uuid4(), outbox=outbox)

    assert outbox.of_type(EnrichmentFailed)[0].reason == (
        "all_sources_failed: egrul=unavailable, fns=unavailable, bki=unavailable, "
        "gir_bo=unavailable, kontur=unavailable, bki_head=unavailable, aml=incomplete, "
        "bank_stop_list=unavailable, bank_turnover=unavailable"
    )
