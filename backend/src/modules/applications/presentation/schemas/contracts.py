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


class ContractOut(BaseModel):
    """The loan contract to show before signing. `number` is the application
    number; `offer_hash` goes back in `POST /applications/{id}/sign`."""

    model_config = ConfigDict(from_attributes=True)

    number: str
    offer_hash: str
    status: Literal["unsigned", "signed"]
    borrower: ContractBorrowerOut
    signers: list[ContractSignerOut]
    terms: OfferOut
    schedule: ContractScheduleOut
    signature: ContractSignatureOut | None
