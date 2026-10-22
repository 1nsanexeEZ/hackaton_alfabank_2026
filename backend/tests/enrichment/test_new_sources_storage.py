"""ГИР БО, Контур, БКИ руководителя и блокировки ФНС: построчно в JSONB и обратно в DTO;
старые снимки без новых полей читаются."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot, SourceError
from src.modules.enrichment.facade import (
    AccountBlockDTO,
    AccountingPeriodDTO,
    AccountingReportsDTO,
    ArbitrationDTO,
    BankruptcyMessageDTO,
    CounterpartyRiskDTO,
    CreditHistoryDTO,
    EnforcementDTO,
    GovContractsDTO,
    ObligationDTO,
    TaxProfileDTO,
)
from src.modules.enrichment.infrastructure.facade_impl import EnrichmentFacadeImpl
from src.modules.enrichment.infrastructure.models import SourceResultRecord
from src.modules.enrichment.infrastructure.repository import SqlAlchemyEnrichmentRepository
from src.modules.enrichment.infrastructure.serialization import data_from_json, data_to_json

_NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

TAX = TaxProfileDTO(
    tax_arrears=Decimal("350000"),
    avg_headcount=15,
    reported_revenue=Decimal("18000000"),
    reported_expenses=Decimal("21000000"),
    report_year=2025,
    tax_regime="УСН",
    disqualified_head=False,
    in_msp_registry=True,
    account_blocks=(AccountBlockDTO("4512", date(2026, 9, 30), "7703", "Неуплата налогов"),),
)
PERIOD = AccountingPeriodDTO(
    year=2025,
    revenue=Decimal("18000000"),
    cost_of_sales=Decimal("21000000"),
    sales_profit=Decimal("-3000000"),
    interest_payable=Decimal("1100000"),
    net_profit=Decimal("-4100000"),
    fixed_assets=Decimal("3150000"),
    inventories=Decimal("1800000"),
    receivables=Decimal("2700000"),
    cash=Decimal("1350000"),
    equity=Decimal("-2400000"),
    total_assets=Decimal("9000000"),
    long_term_liabilities=Decimal("0"),
    short_term_liabilities=Decimal("11400000"),
    total_liabilities=Decimal("9000000"),
)
ACCOUNTING = AccountingReportsDTO(available=True, reason=None, periods=(PERIOD,))
KONTUR = CounterpartyRiskDTO(
    reliability="red",
    notes=("Исполнительные производства",),
    arbitration=ArbitrationDTO(6, 0, Decimal("5200000")),
    enforcement=EnforcementDTO(4, Decimal("2600000")),
    bankruptcy_messages=(
        BankruptcyMessageDTO(date(2026, 8, 12), "Введение процедуры наблюдения", "А40-1/2026"),
    ),
    gov_contracts=GovContractsDTO(0, Decimal("0")),
    active_pledges=1,
)
HEAD = CreditHistoryDTO(
    obligations=(
        ObligationDTO(
            creditor="ПАО «Кредит»",
            kind="consumer",
            amount=Decimal("800000"),
            balance=Decimal("650000"),
            monthly_payment=Decimal("27000"),
            opened_at=date(2024, 3, 1),
            closes_at=None,
            overdue_days=45,
        ),
    ),
    inquiries_last_30d=4,
    has_active_overdue=True,
    max_overdue_days_12m=45,
    total_monthly_payments=Decimal("27000"),
)


def test_json_round_trip_keeps_every_field() -> None:
    for source, data in (
        ("fns", TAX),
        ("gir_bo", ACCOUNTING),
        ("kontur", KONTUR),
        ("bki_head", HEAD),
    ):
        assert data_from_json(source, data_to_json(source, data)) == data  # type: ignore[arg-type]


def test_unavailable_gir_bo_round_trip() -> None:
    nothing = AccountingReportsDTO(False, "ИП не сдают бухгалтерскую отчётность в ГИР БО", ())
    assert data_from_json("gir_bo", data_to_json("gir_bo", nothing)) == nothing


def _snapshot(*, head_skipped: str | None = None) -> EnrichmentSnapshot:
    snapshot = EnrichmentSnapshot(
        id=uuid4(),
        application_id=uuid4(),
        organization_id=uuid4(),
        inn="7703417070",
        requested_by_command=uuid4(),
        requested_sources=("egrul", "fns", "bki", "statement", "gir_bo", "kontur", "bki_head"),
        started_at=_NOW,
        completed_at=_NOW,
    )
    snapshot.record_success("fns", TAX, fetched_at=_NOW)
    snapshot.record_success("gir_bo", ACCOUNTING, fetched_at=_NOW)
    snapshot.record_failure("kontur", SourceError("timeout", "таймаут источника"), attempts=4)
    if head_skipped is None:
        snapshot.record_success("bki_head", HEAD, fetched_at=_NOW)
    else:
        snapshot.record_skipped("bki_head", SourceError(head_skipped, "нет"))
    return snapshot


async def _store_and_read(
    session_factory: async_sessionmaker[AsyncSession], snapshot: EnrichmentSnapshot
):  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        await SqlAlchemyEnrichmentRepository(session).add(snapshot)
        await session.commit()
    async with session_factory() as session:
        facade = EnrichmentFacadeImpl(session, registry=None)  # type: ignore[arg-type]
        return await facade.get_snapshot(snapshot.application_id)


async def test_new_sources_through_the_facade(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dto = await _store_and_read(session_factory, _snapshot())

    assert dto is not None
    assert dto.sources_ok == ("fns", "gir_bo", "bki_head")
    assert [(e.source, e.code) for e in dto.sources_failed] == [("kontur", "timeout")]
    assert dto.sources_skipped == ()
    assert dto.fns == TAX and dto.gir_bo == ACCOUNTING and dto.bki_head == HEAD
    assert dto.kontur is None


async def test_skipped_head_bureau_says_why(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dto = await _store_and_read(session_factory, _snapshot(head_skipped="no_consent"))

    assert dto is not None and dto.bki_head is None
    assert [(e.source, e.code) for e in dto.sources_skipped] == [("bki_head", "no_consent")]
    assert "bki_head" not in dto.sources_ok


async def test_old_tax_row_without_blocks_reads(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    snapshot = _snapshot()
    async with session_factory() as session:
        await SqlAlchemyEnrichmentRepository(session).add(snapshot)
        old = data_to_json("fns", TAX)
        del old["account_blocks"]
        await session.execute(
            update(SourceResultRecord)
            .where(
                SourceResultRecord.snapshot_id == snapshot.id, SourceResultRecord.source == "fns"
            )
            .values(data=old)
        )
        await session.commit()
    async with session_factory() as session:
        dto = await EnrichmentFacadeImpl(session, registry=None).get_snapshot(  # type: ignore[arg-type]
            snapshot.application_id
        )

    assert dto is not None and dto.fns is not None
    assert dto.fns.account_blocks == ()
    assert dto.fns.tax_arrears == Decimal("350000")
