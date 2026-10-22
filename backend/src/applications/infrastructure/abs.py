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


class HttpAbsClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

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
            "number": number,
            "organization_id": str(organization_id),
            "amount": str(amount),
            "term_months": term_months,
            "rate": str(rate),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/abs/disbursements",
                    json=payload,
                    # a retried command must not pay out twice
                    headers={"Idempotency-Key": str(application_id)},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise InfrastructureError("Core banking system is unavailable") from exc
        return DisbursementReceipt(reference=str(data["reference"]), simulated=True)
