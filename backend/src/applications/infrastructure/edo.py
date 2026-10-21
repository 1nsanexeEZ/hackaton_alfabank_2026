"""Electronic document flow (ЭДО) for signing. There is no real qualified
signature in the case: signing goes through a real interface to a mock, so
the adapter can be swapped for the bank's EDO without touching use cases."""

from uuid import UUID

import httpx

from src.applications.application.ports import EdoReceipt
from src.core.exceptions.exceptions import InfrastructureError


class SimulatedEdoClient:
    """Used while the external mocks service is not configured."""

    async def sign(
        self, application_id: UUID, number: str, offer_hash: str, signer_id: UUID
    ) -> EdoReceipt:
        return EdoReceipt(document_id=f"SIM-{offer_hash[:16]}", simulated=True)


class HttpEdoClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def sign(
        self, application_id: UUID, number: str, offer_hash: str, signer_id: UUID
    ) -> EdoReceipt:
        payload = {
            "application_id": str(application_id),
            "number": number,
            "document_hash": offer_hash,
            "signer_id": str(signer_id),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._base_url}/edo/sign", json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise InfrastructureError("Document flow service is unavailable") from exc
        return EdoReceipt(document_id=str(data["document_id"]), simulated=True)
