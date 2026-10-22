from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from src.modules.enrichment.application.ports import (
    PersonQuery,
    SourceNotFound,
    SourceUnavailable,
)
from src.modules.enrichment.facade import AccountBlockDTO, BankruptcyMessageDTO
from src.modules.enrichment.infrastructure.adapters.bki_http import BkiHttpSource
from src.modules.enrichment.infrastructure.adapters.bki_person_http import BkiPersonHttpSource
from src.modules.enrichment.infrastructure.adapters.egrul_http import EgrulHttpSource
from src.modules.enrichment.infrastructure.adapters.fns_http import FnsHttpSource
from src.modules.enrichment.infrastructure.adapters.gir_bo_http import GirBoHttpSource
from src.modules.enrichment.infrastructure.adapters.kontur_http import KonturHttpSource
from tests.enrichment.fixtures import (
    IVANOV_GIR_BO,
    ROMASHKA_BKI,
    ROMASHKA_EGRUL,
    ROMASHKA_FNS,
    ZAKAT_EGRUL,
    ZAKAT_FNS,
    ZAKAT_GIR_BO,
    ZAKAT_KONTUR,
    ZAKATOV_BKI,
)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://mock")


def _demo_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/bki/report":
        return httpx.Response(200, json=ROMASHKA_BKI)
    if request.url.path == "/bki/person-report":
        return httpx.Response(200, json=ZAKATOV_BKI)
    table = {
        "/egrul/7701158817": ROMASHKA_EGRUL,
        "/fns/7701158817": ROMASHKA_FNS,
        "/egrul/7703417070": ZAKAT_EGRUL,
        "/fns/7703417070": ZAKAT_FNS,
        "/gir-bo/7703417070": ZAKAT_GIR_BO,
        "/gir-bo/770669871605": IVANOV_GIR_BO,
        "/kontur/7703417070": ZAKAT_KONTUR,
    }
    body = table.get(request.url.path)
    return httpx.Response(200, json=body) if body else httpx.Response(404, json={"detail": "nf"})


async def test_egrul_maps_foreign_format() -> None:
    dto = await EgrulHttpSource(_client(_demo_handler), backoff=()).fetch("7701158817")
    assert dto.status == "active"
    assert (dto.head_last_name, dto.head_first_name, dto.head_middle_name) == (
        "Смирнова",
        "Анна",
        "Сергеевна",
    )
    assert dto.legal_form == "ООО"
    assert dto.registered_at == date(2019, 1, 15)
    assert dto.okved_extra == ("56.29",)
    assert dto.founders[0].share_percent == Decimal(100)


async def test_egrul_head_record_date() -> None:
    head = {**ROMASHKA_EGRUL["Руководитель"], "ДатаЗаписи": "2026-07-01"}
    body = {**ROMASHKA_EGRUL, "Руководитель": head}
    client = _client(lambda request: httpx.Response(200, json=body))
    dto = await EgrulHttpSource(client, backoff=()).fetch("7701158817")
    assert dto.head_since == date(2026, 7, 1)


async def test_egrul_without_head_record_date() -> None:
    dto = await EgrulHttpSource(_client(_demo_handler), backoff=()).fetch("7701158817")
    assert dto.head_since is None


async def test_egrul_status_lowercased() -> None:
    dto = await EgrulHttpSource(_client(_demo_handler), backoff=()).fetch("7703417070")
    assert dto.status == "liquidating"


async def test_fns_kopecks_to_rubles() -> None:
    dto = await FnsHttpSource(_client(_demo_handler), backoff=()).fetch("7701158817")
    assert dto.tax_arrears == Decimal(0)
    assert dto.reported_revenue == Decimal("47500000")
    assert dto.avg_headcount == 12
    assert dto.in_msp_registry is True


async def test_bki_maps_obligations_and_aggregates() -> None:
    dto = await BkiHttpSource(_client(_demo_handler), backoff=()).fetch(
        "7701158817", datetime(2026, 10, 21, tzinfo=UTC)
    )
    assert dto.obligations[0].monthly_payment == Decimal("180000")
    assert dto.total_monthly_payments == Decimal("180000")
    assert dto.max_overdue_days_12m == 0
    assert dto.has_active_overdue is False
    assert dto.inquiries_last_30d == 1


async def test_not_found_raises() -> None:
    with pytest.raises(SourceNotFound):
        await EgrulHttpSource(_client(_demo_handler), backoff=()).fetch("0000000000")


async def test_server_error_raises_unavailable() -> None:
    source = EgrulHttpSource(_client(lambda _: httpx.Response(503)), backoff=())
    with pytest.raises(SourceUnavailable) as exc:
        await source.fetch("7701158817")
    assert exc.value.kind == "unavailable"


async def test_unknown_status_is_bad_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={**ROMASHKA_EGRUL, "Статус": {"Код": "ZOMBIE"}})

    with pytest.raises(SourceUnavailable) as exc:
        await EgrulHttpSource(_client(handler), backoff=()).fetch("7701158817")
    assert exc.value.kind == "bad_response"


# --- ФНС: блокировки, ГИР БО, Контур, БКИ физлица --------------------------------------------


async def test_fns_account_blocks() -> None:
    dto = await FnsHttpSource(_client(_demo_handler), backoff=()).fetch("7703417070")
    assert dto.tax_arrears == Decimal("350000")
    assert dto.account_blocks == (
        AccountBlockDTO("4512", date(2026, 9, 30), "7703", "Неуплата налогов"),
    )


async def test_fns_without_blocks_field_has_none() -> None:
    dto = await FnsHttpSource(_client(_demo_handler), backoff=()).fetch("7701158817")
    assert dto.account_blocks == ()


async def test_gir_bo_thousands_to_rubles_oldest_first() -> None:
    dto = await GirBoHttpSource(_client(_demo_handler), backoff=()).fetch("7703417070")
    assert dto.available is True and dto.reason is None
    assert [p.year for p in dto.periods] == [2024, 2025]
    latest = dto.latest
    assert latest is not None and latest.year == 2025
    assert latest.revenue == Decimal("18000000")
    assert latest.equity == Decimal("-2400000")
    assert latest.total_liabilities == latest.total_assets == Decimal("9000000")


async def test_gir_bo_entrepreneur_is_unavailable() -> None:
    dto = await GirBoHttpSource(_client(_demo_handler), backoff=()).fetch("770669871605")
    assert dto.available is False and dto.periods == () and dto.latest is None
    assert dto.reason == "ИП не сдают бухгалтерскую отчётность в ГИР БО"


async def test_gir_bo_period_without_a_line_is_bad_response() -> None:
    broken = {**ZAKAT_GIR_BO, "periods": [{"year": 2025, "balance": {}, "income": {}}]}
    source = GirBoHttpSource(_client(lambda _: httpx.Response(200, json=broken)), backoff=())
    with pytest.raises(SourceUnavailable) as exc:
        await source.fetch("7703417070")
    assert exc.value.kind == "bad_response"


async def test_kontur_maps_courts_and_bailiffs() -> None:
    dto = await KonturHttpSource(_client(_demo_handler), backoff=()).fetch("7703417070")
    assert dto.reliability == "red"
    assert dto.arbitration.as_defendant == 6
    assert dto.arbitration.defendant_sum == Decimal("5200000")
    assert (dto.enforcement.active, dto.enforcement.sum) == (4, Decimal("2600000"))
    assert dto.bankruptcy_messages == (
        BankruptcyMessageDTO(date(2026, 8, 12), "Введение процедуры наблюдения", "А40-1234/2026"),
    )
    assert dto.notes[0] == "Юрлицо в процессе ликвидации"


async def test_kontur_partial_answer_keeps_what_came() -> None:
    partial = {
        "reliability": "yellow",
        "arbitration": {"as_defendant": 1, "as_plaintiff": 0, "defendant_sum_rub": 100},
        "enforcement_proceedings": {"active": 0, "sum_rub": 0},
    }
    source = KonturHttpSource(_client(lambda _: httpx.Response(200, json=partial)), backoff=())
    dto = await source.fetch("7703417070")
    assert dto.notes == () and dto.bankruptcy_messages == ()
    assert dto.gov_contracts.count == 0 and dto.active_pledges == 0


async def test_kontur_unknown_reliability_is_bad_response() -> None:
    weird = {**ZAKAT_KONTUR, "reliability": "purple"}
    source = KonturHttpSource(_client(lambda _: httpx.Response(200, json=weird)), backoff=())
    with pytest.raises(SourceUnavailable) as exc:
        await source.fetch("7703417070")
    assert exc.value.kind == "bad_response"


async def test_person_bureau_sends_the_person_and_the_consent() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=ZAKATOV_BKI)

    person = PersonQuery("Закатов", "Олег", "Олегович", "7703417070")
    consent = datetime(2026, 10, 21, 10, tzinfo=UTC)
    dto = await BkiPersonHttpSource(_client(handler), backoff=()).fetch(person, consent)

    assert dto.has_active_overdue is True
    assert dto.obligations[0].overdue_days == 45
    assert dto.total_monthly_payments == Decimal("27000")
    [body] = seen
    assert body["company_inn"] == "7703417070" and body["last_name"] == "Закатов"
    assert body["consent_at"] == consent.isoformat()


async def test_new_sources_retry_after_503() -> None:
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=ZAKAT_KONTUR)

    pauses: list[float] = []

    async def sleep(seconds: float) -> None:
        pauses.append(seconds)

    source = KonturHttpSource(_client(flaky), backoff=(0.5, 1.0, 2.0), sleep=sleep)
    dto = await source.fetch("7703417070")
    assert dto.reliability == "red" and calls["n"] == 3 and pauses == [0.5, 1.0]


@pytest.mark.parametrize(
    "source",
    [GirBoHttpSource, KonturHttpSource],
    ids=["gir_bo", "kontur"],
)
async def test_new_sources_timeout_after_retries(source: type) -> None:
    def hang(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async def sleep(_: float) -> None:
        return None

    with pytest.raises(SourceUnavailable) as exc:
        await source(_client(hang), backoff=(0.0, 0.0), sleep=sleep).fetch("7703417070")
    assert exc.value.kind == "timeout" and exc.value.attempts == 3


async def test_person_bureau_unavailable() -> None:
    source = BkiPersonHttpSource(_client(lambda _: httpx.Response(503)), backoff=())
    person = PersonQuery("Сбоев", "Семён", None, "7705729405")
    with pytest.raises(SourceUnavailable):
        await source.fetch(person, datetime(2026, 10, 21, tzinfo=UTC))
