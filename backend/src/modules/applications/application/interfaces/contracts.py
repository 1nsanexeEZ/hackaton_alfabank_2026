from typing import Protocol
from uuid import UUID

from src.modules.applications.application.dto.contract_documents import (
    BankCertificateDTO,
    ContractPrintDTO,
    SealCheckDTO,
    SealedPdfDTO,
)
from src.modules.applications.domain.contract_documents import (
    ContractDocument,
    ContractDocumentKind,
    SigningEvent,
)


class ContractRenderer(Protocol):
    """The print form of the contract as PDF bytes."""

    def render(self, document: ContractPrintDTO) -> bytes: ...


class ContractSealer(Protocol):
    """The bank's advanced electronic signature embedded in the PDF."""

    def certificate(self) -> BankCertificateDTO: ...

    async def seal(self, pdf: bytes) -> SealedPdfDTO: ...

    async def check(self, pdf: bytes) -> SealCheckDTO: ...


class ContractArchive(Protocol):
    """Storage that keeps a written file unchanged (write once, read many)."""

    async def put(self, key: str, content: bytes) -> None: ...

    async def read(self, key: str) -> bytes: ...


class ContractDocumentRepository(Protocol):
    async def latest(
        self, application_id: UUID, kind: ContractDocumentKind | None = None
    ) -> ContractDocument | None: ...

    async def for_offer(
        self, application_id: UUID, kind: ContractDocumentKind, offer_hash: str
    ) -> ContractDocument | None: ...

    async def get(self, document_id: UUID) -> ContractDocument | None: ...

    async def by_sha256(self, sha256: str) -> ContractDocument | None: ...

    async def add(self, document: ContractDocument) -> None: ...

    async def events(self, application_id: UUID) -> list[SigningEvent]: ...

    async def add_event(self, event: SigningEvent) -> None: ...
