from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from src.modules.enrichment.application.ports import SourceNotFound, SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.bki_http import BkiHttpSource
from src.modules.enrichment.infrastructure.adapters.egrul_http import EgrulHttpSource
from src.modules.enrichment.infrastructure.adapters.fns_http import FnsHttpSource
from tests.enrichment.fixtures import ROMASHKA_BKI, ROMASHKA_EGRUL, ROMASHKA_FNS, ZAKAT_EGRUL


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://mock")


def _demo_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/bki/report":
        return httpx.Response(200, json=ROMASHKA_BKI)
    table = {
        "/egrul/7701158817": ROMASHKA_EGRUL,
        "/fns/7701158817": ROMASHKA_FNS,
        "/egrul/7703417070": ZAKAT_EGRUL,
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
