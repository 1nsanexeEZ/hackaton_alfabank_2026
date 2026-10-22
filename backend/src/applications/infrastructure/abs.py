"""Core banking system (АБС) for the payout. In the case it is a mock: the
call goes through a real interface, the adapter can be swapped for the
bank's system without touching use cases."""

from decimal import Decimal
from uuid import UUID

import httpx

from src.applications.application.ports import DisbursementReceipt
from src.core.exceptions.exceptions import InfrastructureError


class SimulatedAbsClient:
    """Used while the external mocks service is not configured."""

    async def disburse(
        self,
        application_id: UUID,
        number: str,
        organization_id: UUID,
        amount: Decimal,
        term_months: int,
        rate: Decimal,
    ) -> DisbursementReceipt:
        return DisbursementReceipt(reference=f"SIM-{number}", simulated=True)


def settlement_account(organization_id: UUID) -> str:
    """The case has no real accounts: a stable synthetic settlement account
    (40702810… — a company's rouble account) per organization."""
    return "40702810" + f"{organization_id.int % 10**12:012d}"


class HttpAbsClient:
    """`POST /abs/disbursements` of external-mocks:
    `{application_id, account, amount_kop}` →
    `{operation_id, application_id, account, amount_kop, status, simulated}`."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    async def disburse(
        self,
        application_id: UUID,
        number: str,
        organization_id: UUID,
        amount: Decimal,
        term_months: int,
        rate: Decimal,
    ) -> DisbursementReceipt:
        payload = {
            "application_id": str(application_id),
            "account": settlement_account(organization_id),
            # kopecks: no float on the way to the core banking system
            "amount_kop": int((amount * 100).to_integral_exact()),
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/abs/disbursements",
                    json=payload,
                    # a retried command must not pay out twice
                    headers={"Idempotency-Key": str(application_id)},
                )
                response.raise_for_status()
                data = response.json()
            if data.get("status") != "executed":
                raise ValueError(f"Payout is not executed: {data.get('status')}")
            return DisbursementReceipt(
                reference=str(data["operation_id"]),
                simulated=bool(data.get("simulated", True)),
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise InfrastructureError("Core banking system is unavailable") from exc
