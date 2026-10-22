from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from src.modules.enrichment.domain.snapshot import EnrichmentSnapshot, SourceError
from src.modules.enrichment.facade import RegistryExtractDTO

_NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def _snapshot() -> EnrichmentSnapshot:
    return EnrichmentSnapshot(
        id=uuid4(),
        application_id=uuid4(),
        organization_id=uuid4(),
        inn="7701158817",
        requested_by_command=uuid4(),
        requested_sources=("egrul", "fns", "bki"),
        started_at=_NOW,
    )


def _registry() -> RegistryExtractDTO:
    return RegistryExtractDTO(
        inn="7701158817",
        ogrn="1027700399869",
        legal_form="ООО",
        full_name="ООО «Ромашка»",
        status="active",
        registered_at=date(2019, 1, 15),
        okved_main="56.10",
        okved_extra=(),
        head_last_name="Смирнова",
        head_first_name="Анна",
        head_middle_name="Сергеевна",
        head_position="Генеральный директор",
        founders=(),
        address="г. Москва",
        region_code="77",
        mass_address=False,
    )


def test_record_success_exposes_data() -> None:
    snapshot = _snapshot()
    registry = _registry()
    snapshot.record_success("egrul", registry, fetched_at=_NOW)
    assert snapshot.sources_ok == ["egrul"]
    assert snapshot.registry() is registry
    assert snapshot.tax() is None


def test_record_failure_is_not_ok() -> None:
    snapshot = _snapshot()
    snapshot.record_failure("bki", SourceError("unavailable", "503"))
    assert snapshot.sources_failed == ["bki"]
    assert snapshot.credit_history() is None


def test_skipped_is_neither_ok_nor_failed() -> None:
    snapshot = _snapshot()
    snapshot.record_skipped("bki", SourceError("no_consent", ""))
    assert "bki" not in snapshot.sources_ok
    assert "bki" not in snapshot.sources_failed


def test_is_complete_when_all_requested_have_a_result() -> None:
    snapshot = _snapshot()
    assert snapshot.is_complete is False
    snapshot.record_success("egrul", _registry(), fetched_at=_NOW)
    snapshot.record_failure("fns", SourceError("timeout", "t"))
    snapshot.record_skipped("bki", SourceError("no_consent", ""))
    assert snapshot.is_complete is True
