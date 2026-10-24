"""POST /organizations/inn-check: the check of a company by INN before an application."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import Response

from seed.clients import ADDRESSES
from seed.demo_data import COMPANIES_BY_CODE
from src.core.access.permissions import Permissions
from src.core.config import Settings
from src.modules.enrichment.facade import (
    ArbitrationDTO,
    BankruptcyMessageDTO,
    BankStopListDTO,
    CompanyLookupDTO,
    CounterpartyRiskDTO,
    EnforcementDTO,
    EnrichmentFacade,
    GovContractsDTO,
    RegistryExtractDTO,
    SourceErrorDTO,
    TaxProfileDTO,
)
from tests.clients.api.conftest import NOW, SMIRNOVA, UNDERWRITER, Demo, start_demo
from tests.fakes import install
from tests.fakes.enrichment_facade import FakeEnrichmentFacade

URL = "/organizations/inn-check"
ROMASHKA = COMPANIES_BY_CODE["romashka"].inn
VECTOR = COMPANIES_BY_CODE["vector"]
KRAKH = "7707177012"
UNREGISTERED = "7707177990"


def extract(code: str) -> RegistryExtractDTO:
    """What external-mocks answer for a demo company."""
    company = COMPANIES_BY_CODE[code]
    head = company.registry_head
    return RegistryExtractDTO(
        inn=company.inn,
        ogrn=company.ogrn,
        legal_form="ООО",
        full_name=company.name.replace("ООО", "Общество с ограниченной ответственностью", 1),
        status=company.registry_status,
        registered_at=date(2020, 10, 21),
        okved_main=company.okved_main,
        okved_extra=(),
        head_last_name=head.last_name,
        head_first_name=head.first_name,
        head_middle_name=head.middle_name,
        head_position="Генеральный директор",
        founders=(),
        address=ADDRESSES[code],
        region_code="77",
        mass_address=False,
        kpp=company.kpp,
    )


TAX = TaxProfileDTO(
    tax_arrears=Decimal(0),
    avg_headcount=12,
    reported_revenue=Decimal(47_500_000),
    reported_expenses=Decimal(41_000_000),
    report_year=2025,
    tax_regime="УСН",
    disqualified_head=False,
    in_msp_registry=True,
    mass_head=False,
)
KONTUR = CounterpartyRiskDTO(
    reliability="green",
    notes=(),
    arbitration=ArbitrationDTO(0, 1, Decimal(0)),
    enforcement=EnforcementDTO(0, Decimal(0)),
    bankruptcy_messages=(),
    gov_contracts=GovContractsDTO(0, Decimal(0)),
    active_pledges=1,
)
CLEAN = BankStopListDTO(listed=False)


def clean(registry: RegistryExtractDTO) -> CompanyLookupDTO:
    return CompanyLookupDTO(registry, TAX, KONTUR, CLEAN)


@pytest.fixture
def enrichment() -> FakeEnrichmentFacade:
    fake = FakeEnrichmentFacade()
    fake.add_company(clean(extract("romashka")))
    fake.add_company(clean(extract("vector")))
    krakh = replace(
        extract("romashka"),
        inn=KRAKH,
        ogrn="1157707177011",
        full_name="Общество с ограниченной ответственностью «Крах»",
        status="bankrupt",
        kpp="770701001",
    )
    notice = BankruptcyMessageDTO(
        date(2026, 6, 15), "Признание должника банкротом", "А40-117701/2026"
    )
    kontur = replace(KONTUR, reliability="red", bankruptcy_messages=(notice,))
    fake.add_company(CompanyLookupDTO(krakh, TAX, kontur, CLEAN))
    return fake


@pytest.fixture
def demo(settings: Settings, enrichment: FakeEnrichmentFacade) -> Iterator[Demo]:
    def configure(app: FastAPI) -> None:
        install(app, EnrichmentFacade, enrichment)

    with start_demo(settings, configure) as value:
        yield value


def staff(demo: Demo) -> dict[str, str]:
    return demo.headers([Permissions.BACKOFFICE_READ], {}, demo.id_of(UNDERWRITER))


def check_inn(demo: Demo, headers: dict[str, str] | None = None, **body: Any) -> Response:
    return demo.client.post(URL, json=body, headers=staff(demo) if headers is None else headers)


def by_code(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {check["code"]: check for check in body["checks"]}


def test_good_company_of_a_client(demo: Demo) -> None:
    response = check_inn(demo, inn=ROMASHKA)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verdict"] == "ok" and body["summary"] == "Проверка пройдена"
    assert body["checked_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert body["organization_id"] == str(demo.orgs["romashka"])
    company = body["company"]
    assert company["name"] == "ООО «Ромашка»" and company["legal_form"] == "LLC"
    assert company["ogrn"] == "1027700399869" and company["kpp"] == "770101001"
    assert company["head_name"] == "Смирнова Анна Сергеевна"
    assert company["registry_status"] == "active"
    assert body["tax"]["tax_regime"] == "УСН"
    assert body["counterparty"]["reliability"] == "green"
    checks = by_code(body)
    assert {c["status"] for c in checks.values()} == {"passed"}
    assert checks["bank_client"] == {
        "code": "bank_client",
        "title": "Клиент банка",
        "status": "passed",
        "message": "Клиент банка, карточка сверена 21.10.2026",
        "source": "bank",
    }


def test_matching_requisites(demo: Demo) -> None:
    body = check_inn(
        demo, inn=ROMASHKA, ogrn="1027700399869", kpp="770101001", name="Ромашка"
    ).json()

    assert body["verdict"] == "ok"
    checks = by_code(body)
    assert [checks[c]["status"] for c in ("ogrn_match", "kpp_match", "name_match")] == [
        "passed"
    ] * 3


def test_inn_of_another_company(demo: Demo) -> None:
    """The INN of «Ромашка» with the OGRN and the name of «Вектор»."""
    body = check_inn(demo, inn=ROMASHKA, ogrn=VECTOR.ogrn, name="ООО «Вектор»").json()

    assert body["verdict"] == "fail"
    assert body["summary"] == "Не пройдена: ОГРН, наименование"
    checks = by_code(body)
    assert checks["ogrn_match"]["status"] == "failed"
    assert checks["ogrn_match"]["source"] == "input"
    assert checks["name_match"]["message"].startswith("По этому ИНН в реестре — ООО «Ромашка»")


def test_card_that_differs_from_the_registry(demo: Demo) -> None:
    """«Вектор»: at the seed's check the director differs from the head in the registry."""
    body = check_inn(demo, inn=VECTOR.inn, kpp="770101001").json()

    assert body["verdict"] == "warning"
    checks = by_code(body)
    assert checks["kpp_match"]["status"] == "warning"
    assert checks["bank_client"]["status"] == "warning"
    assert "заявлен Петров П. П., в реестре Сидоров С. С." in checks["bank_client"]["message"]


def test_bankrupt_company_that_is_not_a_client(demo: Demo) -> None:
    body = check_inn(demo, inn=KRAKH).json()

    assert body["verdict"] == "fail"
    assert body["summary"] == "Не пройдена: статус в реестре, банкротство"
    assert body["organization_id"] is None
    assert "bank_client" not in by_code(body)
    [message] = body["counterparty"]["bankruptcy_messages"]
    assert message == {
        "date": "2026-06-15",
        "type": "Признание должника банкротом",
        "case": "А40-117701/2026",
    }


def test_sources_that_did_not_answer(demo: Demo, enrichment: FakeEnrichmentFacade) -> None:
    failed = (SourceErrorDTO("fns", "unavailable", "HTTP 503"),)
    enrichment.add_company(CompanyLookupDTO(extract("romashka"), sources_failed=failed))

    body = check_inn(demo, inn=ROMASHKA).json()

    assert body["verdict"] == "warning"
    assert body["tax"] is None and body["counterparty"] is None
    checks = by_code(body)
    assert checks["tax_arrears"]["status"] == "skipped"
    assert checks["bank_stop_list"]["status"] == "skipped"


def test_unknown_inn(demo: Demo) -> None:
    response = check_inn(demo, inn=UNREGISTERED)

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "not_found"
    assert body["summary"] == "ИНН не найден в ЕГРЮЛ"
    assert body["company"] is None and body["organization_id"] is None
    assert [(c["code"], c["status"]) for c in body["checks"]] == [
        ("inn_checksum", "passed"),
        ("registry_found", "failed"),
    ]


def test_typo_in_the_inn_asks_nobody(demo: Demo, enrichment: FakeEnrichmentFacade) -> None:
    enrichment.registry_down = True

    response = check_inn(demo, inn="7701158818")

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "fail" and body["company"] is None
    assert [(c["code"], c["status"]) for c in body["checks"]] == [("inn_checksum", "failed")]


def test_registry_down(demo: Demo, enrichment: FakeEnrichmentFacade) -> None:
    enrichment.registry_down = True

    response = check_inn(demo, inn=ROMASHKA)

    assert response.status_code == 503
    assert response.json()["code"] == "unavailable"


@pytest.mark.parametrize(
    "body",
    [
        {"inn": "770115881"},
        {"inn": "77011588170"},
        {"inn": "770115881a"},
        {"inn": ROMASHKA, "ogrn": "12345"},
        {"inn": ROMASHKA, "kpp": "77010100"},
        {"inn": ROMASHKA, "name": ""},
    ],
)
def test_bad_request(demo: Demo, body: dict[str, str]) -> None:
    assert check_inn(demo, **body).status_code == 422


def test_bank_staff_only(demo: Demo) -> None:
    assert check_inn(demo, demo.as_client(SMIRNOVA), inn=ROMASHKA).status_code == 403
    assert check_inn(demo, demo.as_underwriter(), inn=ROMASHKA).status_code == 403
    assert check_inn(demo, demo.as_admin(), inn=ROMASHKA).status_code == 200
    assert demo.client.post(URL, json={"inn": ROMASHKA}).status_code == 401
    assert demo.outbox() == []
