"""Contract documents: the print form, its archive copy and their checks."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from src.modules.applications.application.dto.views import ContractDTO

DocumentKind = Literal["draft", "signed"]


@dataclass(frozen=True, slots=True)
class ClientSignatureDTO:
    """The client's simple electronic signature as the document shows it."""

    signer: str
    role: str
    authority: Literal["registry", "power_of_attorney"]
    signed_at: datetime
    ip: str | None
    method: Literal["password"]
    rules_version: str | None
    # SHA-256 of the draft the client saw and signed.
    document_hash: str | None
    edo_document_id: str | None


@dataclass(frozen=True, slots=True)
class BankCertificateDTO:
    subject: str
    serial: str
    issuer: str
    valid_from: datetime
    valid_to: datetime


@dataclass(frozen=True, slots=True)
class BankSealDTO:
    signer: str
    certificate: BankCertificateDTO
    signed_at: datetime
    timestamp_at: datetime | None


@dataclass(frozen=True, slots=True)
class SigningEventDTO:
    at: datetime
    kind: str
    actor: str
    text: str
    hash: str


@dataclass(frozen=True, slots=True)
class ContractPrintDTO:
    """Everything the PDF shows."""

    document_id: UUID
    kind: DocumentKind
    uid: str
    verify_url: str
    contract: ContractDTO
    product_name: str
    purpose: str | None
    issued_at: datetime
    client_signature: ClientSignatureDTO | None
    # Printed into the stamp just before the bank signs the file.
    bank_seal: BankSealDTO | None
    events: tuple[SigningEventDTO, ...]


@dataclass(frozen=True, slots=True)
class SealedPdfDTO:
    content: bytes
    signed_at: datetime
    timestamp_at: datetime | None


@dataclass(frozen=True, slots=True)
class SealCheckDTO:
    present: bool
    intact: bool
    trusted: bool
    signer: str | None
    signed_at: datetime | None
    timestamp_at: datetime | None


@dataclass(frozen=True, slots=True)
class DocumentFileDTO:
    content: bytes
    filename: str
    kind: DocumentKind
    sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedSignatureDTO:
    party: Literal["client", "bank"]
    type: Literal["simple", "advanced"]
    signer: str
    role: str | None
    authority: Literal["registry", "power_of_attorney"] | None
    signed_at: datetime
    method: Literal["password", "pades"]
    rules_version: str | None
    timestamp_at: datetime | None
    certificate: BankCertificateDTO | None


@dataclass(frozen=True, slots=True)
class ContractVerificationDTO:
    """What anyone with the QR code may see about the document."""

    document_id: UUID
    number: str
    uid: str
    kind: DocumentKind
    sha256: str
    created_at: datetime
    borrower: str
    signatures: tuple[VerifiedSignatureDTO, ...]
    log_intact: bool
    demo: bool


@dataclass(frozen=True, slots=True)
class FileSignatureDTO:
    present: bool
    intact: bool
    trusted: bool
    signer: str | None
    signed_at: datetime | None
    timestamp_at: datetime | None


@dataclass(frozen=True, slots=True)
class FileVerificationDTO:
    valid: bool
    document_id: UUID | None
    matches_archive: bool
    signature: FileSignatureDTO
    problems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EsignRulesDTO:
    version: str
    title: str
    effective_from: str
    paragraphs: tuple[str, ...]
