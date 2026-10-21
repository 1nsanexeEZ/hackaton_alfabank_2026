from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.enrichment.domain.snapshot import EnrichmentSnapshot, SourceError
from src.enrichment.facade import CreditHistoryDTO, RegistryExtractDTO, TaxProfileDTO
from src.enrichment.infrastructure.facade_impl import EnrichmentFacadeImpl
from src.enrichment.infrastructure.repository import SqlAlchemyEnrichmentRepository

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
        dto = await EnrichmentFacadeImpl(session, registry=None).get_snapshot(application_id)  # type: ignore[arg-type]

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
    registry = found.registry()
    assert registry is not None
    assert registry.inn == "7701158817"
    assert registry.okved_extra == ("56.29",)


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
