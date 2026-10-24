"""The registry extract of enrichment as clients value objects; the company by INN for the
check before an application."""

import logging
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.clients.domain.enums import LegalForm, RegistryStatus
from src.modules.clients.domain.inn_check import (
    AccountBlock,
    BankruptcyNotice,
    Founder,
    StopListRecord,
)
from src.modules.clients.domain.value_objects import Kpp, PersonName
from src.modules.clients.infrastructure.adapters.enrichment_company_check import (
    EnrichmentCompanyCheck,
    legal_form_of,
)
from src.modules.clients.infrastructure.adapters.enrichment_registry import (
    EnrichmentRegistryLookup,
    extract_of,
    short_name,
)
from src.modules.enrichment.facade import (
    AccountBlockDTO,
    ArbitrationDTO,
    BankruptcyMessageDTO,
    BankStopListDTO,
    CompanyLookupDTO,
    CounterpartyRiskDTO,
    EnforcementDTO,
    EnrichmentSnapshotDTO,
    FounderDTO,
    GovContractsDTO,
    RegistryExtractDTO,
    TaxProfileDTO,
)
from tests.fakes.enrichment_facade import FakeEnrichmentFacade

DTO = RegistryExtractDTO(
    inn="7701158817",
    ogrn="1027700399869",
    legal_form="ООО",
    full_name="Общество с ограниченной ответственностью «Ромашка»",
    status="active",
    registered_at=date(2020, 10, 21),
    okved_main="56.10",
    okved_extra=("56.29",),
    head_last_name="Смирнова",
    head_first_name="Анна",
    head_middle_name="Сергеевна",
    head_position="Генеральный директор",
    founders=(),
    address="г. Москва, ул. Тверская, д. 1",
    region_code="77",
    mass_address=False,
    kpp="770101001",
)


@pytest.mark.parametrize(
    ("full", "short"),
    [
        ("Общество с ограниченной ответственностью «Ромашка»", "ООО «Ромашка»"),
        ("ОБЩЕСТВО С ОГРАНИЧЕННОЙ  ОТВЕТСТВЕННОСТЬЮ «ВЕКТОР»", "ООО «ВЕКТОР»"),
        ("Публичное акционерное общество «Банк»", "ПАО «Банк»"),
        ("Акционерное общество «Завод»", "АО «Завод»"),
        ("Индивидуальный предприниматель Иванов Иван Иванович", "ИП Иванов Иван Иванович"),
        ("ООО «Ромашка»", "ООО «Ромашка»"),
    ],
)
def test_short_name(full: str, short: str) -> None:
    assert short_name(full) == short


def test_extract_in_value_objects() -> None:
    extract = extract_of(DTO)
    assert extract.name == "ООО «Ромашка»"
    assert extract.kpp == Kpp("770101001")
    assert extract.status is RegistryStatus.ACTIVE
    assert extract.head == PersonName("Смирнова", "Анна", "Сергеевна")
    assert [code.value for code in extract.okved_extra] == ["56.29"]
    assert extract_of(replace(DTO, kpp=None)).kpp is None


@pytest.mark.parametrize(
    "broken",
    [
        {"okved_main": "6"},
        {"status": "dissolved"},
        {"head_last_name": ""},
        {"region_code": "Москва"},
    ],
)
def test_unreadable_extract_is_the_registry_fault(broken: dict[str, str]) -> None:
    with pytest.raises(InfrastructureError) as error:
        extract_of(replace(DTO, **broken))  # type: ignore[arg-type]
    assert error.value.details is not None
    assert error.value.details["code"] == "bad_registry_data"


# --- the extract enrichment fetched for an application -------------------------


def snapshot(egrul: RegistryExtractDTO | None) -> EnrichmentSnapshotDTO:
    return EnrichmentSnapshotDTO(
        id=uuid4(),
        application_id=uuid4(),
        organization_id=uuid4(),
        collected_at=datetime(2026, 10, 21, 12, 0, tzinfo=UTC),
        sources_ok=("egrul",) if egrul else (),
        sources_failed=(),
        egrul=egrul,
        fns=None,
        bki=None,
        cashflow=None,
    )


async def test_extract_of_the_application_with_its_company() -> None:
    enrichment = FakeEnrichmentFacade()
    taken = enrichment.add_snapshot(snapshot(DTO))

    found = await EnrichmentRegistryLookup(enrichment).of_application(taken.application_id)

    assert found == (taken.organization_id, extract_of(DTO))


async def test_no_extract_for_the_application() -> None:
    enrichment = FakeEnrichmentFacade()
    failed = enrichment.add_snapshot(snapshot(None))
    lookup = EnrichmentRegistryLookup(enrichment)

    assert await lookup.of_application(failed.application_id) is None
    assert await lookup.of_application(uuid4()) is None


async def test_unreadable_extract_of_the_application_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    enrichment = FakeEnrichmentFacade()
    broken = enrichment.add_snapshot(snapshot(replace(DTO, okved_main="6")))

    with caplog.at_level(logging.WARNING):
        found = await EnrichmentRegistryLookup(enrichment).of_application(broken.application_id)

    assert found is None
    assert "Unreadable registry extract" in caplog.text


# --- the company by INN for the check before an application --------------------


@pytest.mark.parametrize(
    ("inn", "form", "legal_form"),
    [
        ("7701158817", "ООО", LegalForm.LLC),
        ("7701158817", "АО", LegalForm.JSC),
        ("7701158817", "ПАО", LegalForm.JSC),
        ("770669871605", "ИП", LegalForm.IE),
    ],
)
def test_legal_form_of_the_extract(inn: str, form: str, legal_form: LegalForm) -> None:
    assert legal_form_of(replace(DTO, inn=inn, legal_form=form)) is legal_form


async def test_company_by_inn_in_value_objects() -> None:
    enrichment = FakeEnrichmentFacade()
    tax = TaxProfileDTO(
        tax_arrears=Decimal(350_000),
        avg_headcount=15,
        reported_revenue=Decimal(18_000_000),
        reported_expenses=None,
        report_year=2025,
        tax_regime="УСН",
        disqualified_head=False,
        in_msp_registry=True,
        account_blocks=(AccountBlockDTO("4512", date(2026, 9, 30), "7703", "Неуплата налогов"),),
        mass_head=False,
    )
    kontur = CounterpartyRiskDTO(
        reliability="red",
        notes=("Исполнительные производства",),
        arbitration=ArbitrationDTO(6, 0, Decimal(5_200_000)),
        enforcement=EnforcementDTO(4, Decimal(2_600_000)),
        bankruptcy_messages=(BankruptcyMessageDTO(date(2026, 8, 12), "Наблюдение", "А40-1/2026"),),
        gov_contracts=GovContractsDTO(0, Decimal(0)),
        active_pledges=1,
    )
    founder = FounderDTO("Смирнова Анна Сергеевна", Decimal(100))
    enrichment.add_company(
        CompanyLookupDTO(
            registry=replace(DTO, founders=(founder,), mass_address=True, unreliable=("head",)),
            tax=tax,
            counterparty=kontur,
            bank_stop_list=BankStopListDTO(listed=True, reason="Подложные документы"),
        )
    )
    source = EnrichmentCompanyCheck(enrichment)

    record = await source.lookup("7701158817")

    assert record is not None
    assert record.registry.extract == extract_of(replace(DTO, founders=(founder,)))
    assert record.registry.legal_form is LegalForm.LLC
    assert record.registry.mass_address and record.registry.unreliable == ("head",)
    assert record.registry.founders == (Founder("Смирнова Анна Сергеевна", Decimal(100)),)
    assert record.tax is not None and record.tax.tax_arrears == Decimal(350_000)
    assert record.tax.account_blocks == (
        AccountBlock("4512", date(2026, 9, 30), "Неуплата налогов"),
    )
    assert record.court is not None and record.court.enforcement_active == 4
    assert record.court.bankruptcy == (
        BankruptcyNotice(date(2026, 8, 12), "Наблюдение", "А40-1/2026"),
    )
    assert record.stop_list == StopListRecord(listed=True, reason="Подложные документы")
    assert await source.lookup("7702987976") is None


async def test_sources_that_did_not_answer_stay_empty() -> None:
    enrichment = FakeEnrichmentFacade()
    enrichment.add_company(CompanyLookupDTO(registry=DTO))

    record = await EnrichmentCompanyCheck(enrichment).lookup("7701158817")

    assert record is not None
    assert record.tax is None and record.court is None and record.stop_list is None


async def test_unreadable_company_extract_is_the_registry_fault() -> None:
    enrichment = FakeEnrichmentFacade()
    enrichment.add_company(CompanyLookupDTO(registry=replace(DTO, okved_main="6")))

    with pytest.raises(InfrastructureError):
        await EnrichmentCompanyCheck(enrichment).lookup("7701158817")
