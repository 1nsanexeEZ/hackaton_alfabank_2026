"""HTTP adapters to the EDO and ABS mocks speak the mocks' own format
(external-mocks/app/schemas.py and main.py)."""

import json
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.applications.infrastructure.abs import HttpAbsClient, settlement_account
from src.modules.applications.infrastructure.edo import HttpEdoClient

ORGANIZATION = UUID("00000000-0000-0000-0000-0000000000b1")


def transport(handler):  # type: ignore[no-untyped-def]
    calls: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    return httpx.MockTransport(record), calls


async def test_edo_sends_hash_and_signer() -> None:
    signer = uuid4()

    def mock(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "signature_id": "sig-42",
                "document_hash": body["document_hash"],
                "signer": body["signer"],
                "signed_at": "2026-10-21T12:00:00+00:00",
                "simulated": True,
            },
        )

    mock_transport, calls = transport(mock)
    receipt = await HttpEdoClient("http://mocks:8100/", transport=mock_transport).sign(
        uuid4(), "КР-2026-000001", "a" * 64, signer
    )

    [request] = calls
    assert str(request.url) == "http://mocks:8100/edo/sign"
    assert json.loads(request.content) == {"document_hash": "a" * 64, "signer": str(signer)}
    assert (receipt.document_id, receipt.simulated) == ("sig-42", True)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"detail": "down"}),
        httpx.Response(422, json={"detail": [{"loc": ["body", "signer"]}]}),
        httpx.Response(200, json={"signature_id": "x", "document_hash": "other"}),
        httpx.Response(200, json={"document_hash": "a" * 64}),
        httpx.Response(200, content=b"not json"),
    ],
    ids=["down", "rejected", "other-document", "no-id", "garbage"],
)
async def test_edo_failures_are_infrastructure_errors(response: httpx.Response) -> None:
    mock_transport, _ = transport(lambda request: response)
    with pytest.raises(InfrastructureError):
        await HttpEdoClient("http://mocks:8100", transport=mock_transport).sign(
            uuid4(), "КР-2026-000001", "a" * 64, uuid4()
        )


async def test_abs_sends_account_and_kopecks() -> None:
    application_id = uuid4()

    def mock(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "operation_id": "op-7",
                "application_id": body["application_id"],
                "account": body["account"],
                "amount_kop": body["amount_kop"],
                "status": "executed",
                "simulated": True,
            },
        )

    mock_transport, calls = transport(mock)
    receipt = await HttpAbsClient("http://mocks:8100", transport=mock_transport).disburse(
        application_id, "КР-2026-000001", ORGANIZATION, Decimal("3000000.50"), 24, Decimal("23.5")
    )

    [request] = calls
    assert str(request.url) == "http://mocks:8100/abs/disbursements"
    assert request.headers["Idempotency-Key"] == str(application_id)
    assert json.loads(request.content) == {
        "application_id": str(application_id),
        "account": settlement_account(ORGANIZATION),
        "amount_kop": 300000050,
    }
    assert (receipt.reference, receipt.simulated) == ("op-7", True)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={"operation_id": "op", "status": "rejected"}),
        httpx.Response(200, json={"status": "executed"}),
    ],
    ids=["down", "not-executed", "no-operation"],
)
async def test_abs_failures_are_infrastructure_errors(response: httpx.Response) -> None:
    mock_transport, _ = transport(lambda request: response)
    with pytest.raises(InfrastructureError):
        await HttpAbsClient("http://mocks:8100", transport=mock_transport).disburse(
            uuid4(), "КР-2026-000001", ORGANIZATION, Decimal("1"), 12, Decimal("20")
        )


def test_settlement_account_is_stable_and_twenty_digits() -> None:
    account = settlement_account(ORGANIZATION)
    assert account == settlement_account(ORGANIZATION)
    assert len(account) == 20 and account.isdigit() and account.startswith("40702810")
    assert settlement_account(uuid4()) != account
