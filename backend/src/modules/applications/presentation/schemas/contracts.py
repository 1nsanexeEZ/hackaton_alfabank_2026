from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.modules.applications.presentation.schemas.applications import ApplicationOut, OfferOut


class SignIn(BaseModel):
    password: SecretStr = Field(min_length=1, max_length=128)
    # `offer_hash` from GET /applications/{id}/contract: the client signs what it saw.
    offer_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    # `document.sha256` of the draft PDF the client read; 422 `document_changed` if it differs.
    document_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    # `version` of GET /esign/rules the client accepted; 422 `rules_outdated` if not current.
    rules_version: str | None = Field(default=None, max_length=32)


class SignatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signed_at: datetime
    offer_hash: str
    edo_document_id: str
    # Signing goes through a mock of the document flow, not a real signature.
    simulated: bool


class SignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    application: ApplicationOut
    signature: SignatureOut


class ContractBorrowerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    inn: str
    ogrn: str
    kpp: str | None
    legal_form: str
    head_name: str | None


class ContractSignerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: UUID
    name: str
    authority: Literal["registry", "power_of_attorney"]


class ContractPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int
    due_date: date | None
    principal: Decimal
    interest: Decimal
    total: Decimal
    balance_after: Decimal


class ContractScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    amount: Decimal
    term_months: int
    rate: Decimal
    repayment: str
    monthly_payment: Decimal
    total_interest: Decimal
    total_paid: Decimal
    payments: list[ContractPaymentOut]


class ContractSignatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signed_by: UUID
    signed_at: datetime
    edo_document_id: str | None
    simulated: bool


class ContractDocumentOut(BaseModel):
    """The current PDF: `draft` until the client signs, then `signed` (sealed by the bank).
    `pending` — being made, `failed` — could not be made, the contract still works."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None
    kind: Literal["draft", "signed"]
    status: Literal["pending", "ready", "failed"]
    sha256: str | None
    created_at: datetime | None
    filename: str | None
    verify_url: str | None


class ContractOut(BaseModel):
    """The loan contract to show before signing. `number` is the application
    number; `offer_hash` and `document.sha256` go back in `POST /applications/{id}/sign`."""

    model_config = ConfigDict(from_attributes=True)

    number: str
    offer_hash: str
    status: Literal["unsigned", "signed"]
    borrower: ContractBorrowerOut
    signers: list[ContractSignerOut]
    terms: OfferOut
    schedule: ContractScheduleOut
    signature: ContractSignatureOut | None
    # Unique identifier of the deal (218-FZ): the UUID and a check symbol.
    uid: str | None = None
    document: ContractDocumentOut | None = None


class EsignRulesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: str
    title: str
    effective_from: str
    paragraphs: list[str]


class BankCertificateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    serial: str
    subject: str
    issuer: str
    valid_from: datetime
    valid_to: datetime


class VerifiedSignatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    party: Literal["client", "bank"]
    type: Literal["simple", "advanced"]
    signer: str
    role: str | None
    authority: Literal["registry", "power_of_attorney"] | None
    signed_at: datetime
    method: Literal["password", "pades"]
    rules_version: str | None
    timestamp_at: datetime | None
    certificate: BankCertificateOut | None


class ContractVerificationOut(BaseModel):
    """What anyone with the QR code sees: no IP, no account ids, the client by initials."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    number: str
    uid: str
    kind: Literal["draft", "signed"]
    sha256: str
    created_at: datetime
    borrower: str
    signatures: list[VerifiedSignatureOut]
    # The signing log of the contract is unbroken: each entry holds the hash of the one before.
    log_intact: bool
    # The bank's key comes from the demo CA of the stand, it is not a qualified one.
    demo: bool


class FileSignatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    present: bool
    intact: bool
    trusted: bool
    signer: str | None
    signed_at: datetime | None
    timestamp_at: datetime | None


class FileVerificationOut(BaseModel):
    """`problems`: not_in_archive, draft_not_signed, no_signature, signature_broken,
    untrusted_certificate."""

    model_config = ConfigDict(from_attributes=True)

    valid: bool
    document_id: UUID | None
    matches_archive: bool
    signature: FileSignatureOut
    problems: list[str]
