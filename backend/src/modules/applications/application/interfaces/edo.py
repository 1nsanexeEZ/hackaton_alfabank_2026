from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EdoReceipt:
    document_id: str
    # True while signing goes through the mock of the electronic document flow.
    simulated: bool


class EdoClient(Protocol):
    """Electronic document flow (ЭДО): signs the contract."""

    # True while the document flow is a mock: the contract says so to the client.
    simulated: bool

    async def sign(
        self, application_id: UUID, number: str, offer_hash: str, signer_id: UUID
    ) -> EdoReceipt: ...
