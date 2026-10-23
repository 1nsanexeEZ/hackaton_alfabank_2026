from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.enrichment.application.use_cases.get_snapshot import GetSnapshotUseCase
from src.modules.enrichment.application.use_cases.latest_cashflow import GetLatestCashflowUseCase
from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot, SourceError
from src.modules.enrichment.facade import (
    CashflowForecastDTO,
    CashflowMonthDTO,
    CashflowProjectionDTO,
    CreditHistoryDTO,
    RegistryExtractDTO,
    TaxProfileDTO,
)
from src.modules.enrichment.infrastructure.repositories.enrichment_repository import (
    SqlAlchemyEnrichmentRepository,
)

_NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def _registry() -> RegistryExtractDTO:
    return RegistryExtractDTO(
        inn="7701158817",
        ogrn="1027700399869",
        legal_form="ООО",
        full_name="ООО «Ромашка»",
        status="active",
        registered_at=date(2019, 1, 15),
        okved_main="56.10",
        okved_extra=("56.29",),
        head_last_name="Смирнова",
        head_first_name="Анна",
        head_middle_name="Сергеевна",
        head_position="Генеральный директор",
        founders=(),
        address="г. Москва",
        region_code="77",
        mass_address=False,
    )


def _snapshot() -> tuple[EnrichmentSnapshot, UUID]:
    application_id = uuid4()
    snapshot = EnrichmentSnapshot(
        id=uuid4(),
        application_id=application_id,
        organization_id=uuid4(),
        inn="7701158817",
        requested_by_command=uuid4(),
        requested_sources=("egrul", "fns", "bki"),
        started_at=_NOW,
    )
    snapshot.record_success("egrul", _registry(), fetched_at=_NOW)
    snapshot.record_success(
        "fns",
        TaxProfileDTO(
            tax_arrears=Decimal(0),
            avg_headcount=12,
            reported_revenue=Decimal("47500000"),
            reported_expenses=Decimal("41000000"),
            report_year=2025,
            tax_regime="УСН",
            disqualified_head=False,
            in_msp_registry=True,
        ),
        fetched_at=_NOW,
    )
    snapshot.record_failure("bki", SourceError("unavailable", "503"))
    snapshot.completed_at = _NOW
    return snapshot, application_id


async def test_roundtrip_through_facade(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    snapshot, application_id = _snapshot()
    async with session_factory() as session:
        await SqlAlchemyEnrichmentRepository(session).add(snapshot)
        await session.commit()

    async with session_factory() as session:
        dto = await GetSnapshotUseCase(SqlAlchemyEnrichmentRepository(session)).execute(
            application_id
        )

    assert dto is not None
    assert set(dto.sources_ok) == {"egrul", "fns"}
    assert dto.egrul is not None
    assert dto.egrul.status == "active"
    assert dto.egrul.head_last_name == "Смирнова"
    assert dto.egrul.okved_extra == ("56.29",)
    assert dto.fns is not None
    assert dto.fns.reported_revenue == Decimal("47500000")
    assert dto.bki is None
    assert len(dto.sources_failed) == 1
    assert dto.sources_failed[0].source == "bki"
    assert dto.sources_failed[0].code == "unavailable"
    assert dto.cashflow is None


async def test_get_by_command_reconstructs_data(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    snapshot, _ = _snapshot()
    async with session_factory() as session:
        await SqlAlchemyEnrichmentRepository(session).add(snapshot)
        await session.commit()

    async with session_factory() as session:
        found = await SqlAlchemyEnrichmentRepository(session).get_by_command(
            snapshot.requested_by_command
        )

    assert found is not None
    assert found.id == snapshot.id
    registry = found.data_of("egrul", RegistryExtractDTO)
    assert registry is not None
    assert registry.inn == "7701158817"
    assert registry.okved_extra == ("56.29",)


def _forecast() -> CashflowForecastDTO:
    return CashflowForecastDTO(
        months_history=(
            CashflowMonthDTO(
                month="2026-09",
                inflow=Decimal("1000000.00"),
                outflow=Decimal("800000.00"),
                net=Decimal("200000.00"),
                balance=Decimal("200000.00"),
            ),
        ),
        forecast=(CashflowProjectionDTO(month="2026-11", projected_balance=Decimal("-120000.00")),),
        gap_detected=True,
        gap_month="2026-11",
        gap_amount=Decimal("120000.00"),
        annual_inflow=Decimal("6000000.00"),
        revenue_confirmed=True,
        method="тест",
        statement_document_ids=(uuid4(),),
    )


async def test_cashflow_roundtrip_through_facade(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    snapshot, application_id = _snapshot()
    snapshot.record_cashflow(_forecast(), fetched_at=_NOW)
    async with session_factory() as session:
        await SqlAlchemyEnrichmentRepository(session).add(snapshot)
        await session.commit()

    async with session_factory() as session:
        dto = await GetSnapshotUseCase(SqlAlchemyEnrichmentRepository(session)).execute(
            application_id
        )

    assert dto is not None
    assert dto.cashflow is not None
    assert dto.cashflow.gap_detected is True
    assert dto.cashflow.gap_month == "2026-11"
    assert dto.cashflow.gap_amount == Decimal("120000.00")
    assert dto.cashflow.revenue_confirmed is True
    assert dto.cashflow.months_history[0].net == Decimal("200000.00")
    assert dto.cashflow.forecast[0].projected_balance == Decimal("-120000.00")
    # `statement` — внутренний источник, не попадает ни в успешные, ни в проваленные.
    assert "statement" not in dto.sources_ok
    assert all(error.source != "statement" for error in dto.sources_failed)


async def test_latest_cashflow_of_the_company(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Самый свежий прогноз по выписке среди заявок компании; более новая заявка без выписки
    его не затирает, у компании без выписок — None."""
    with_statement, _ = _snapshot()
    with_statement.record_cashflow(_forecast(), fetched_at=_NOW)
    organization_id = with_statement.organization_id
    later, _ = _snapshot()
    later.organization_id = organization_id
    later.started_at = _NOW + timedelta(days=3)
    newer_forecast = replace(_forecast(), gap_detected=False, gap_month=None, gap_amount=None)
    older, _ = _snapshot()
    older.organization_id = organization_id
    older.started_at = _NOW - timedelta(days=30)
    older.record_cashflow(newer_forecast, fetched_at=_NOW)
    async with session_factory() as session:
        repository = SqlAlchemyEnrichmentRepository(session)
        for snapshot in (with_statement, later, older):
            await repository.add(snapshot)
        await session.commit()

    async with session_factory() as session:
        use_case = GetLatestCashflowUseCase(SqlAlchemyEnrichmentRepository(session))
        found = await use_case.execute(organization_id)
        missing = await use_case.execute(uuid4())

    assert found is not None and found.gap_detected is True and found.gap_month == "2026-11"
    assert missing is None


def test_credit_history_dto_isolation() -> None:
    # БКИ при неуспехе не попадает в снимок, а неизменяемость DTO защищает границу раскрытия.
    history = CreditHistoryDTO(
        obligations=(),
        inquiries_last_30d=0,
        has_active_overdue=False,
        max_overdue_days_12m=0,
        total_monthly_payments=Decimal(0),
    )
    assert history.inquiries_last_30d == 0
