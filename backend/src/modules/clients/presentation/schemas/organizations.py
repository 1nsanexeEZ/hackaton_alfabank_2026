from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.modules.clients.presentation.schemas.members import Role

LegalForm = Literal["LLC", "IE", "JSC"]


class OrganizationSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    inn: str
    legal_form: LegalForm
    registry_status: str
    # None — the caller is not a member (bank staff).
    my_role: Role | None
    my_permissions: list[str]


class AddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full: str
    region_code: str


class DiscrepancyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field: str
    declared: str | None
    registry: str | None


class VerificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: Literal["unverified", "verified", "mismatch"]
    checked_at: datetime | None
    discrepancies: list[DiscrepancyRead]


class OrganizationRead(OrganizationSummaryRead):
    ogrn: str
    kpp: str | None
    registered_at: date
    business_age_months: int
    address: AddressRead
    okved_main: str
    okved_extra: list[str]
    tax_regime: str
    employees_count: int
    # Head by the registry (ЕГРЮЛ/ЕГРИП).
    head_name: str | None
    verification: VerificationRead
    version: int


class FieldChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # `name`, `address.full`, `address.region_code`, `kpp`, `okved_main`,
    # `okved_extra` (codes joined with ", "), `registry_status`.
    field: str
    before: str | None
    after: str | None


class VerificationResultRead(BaseModel):
    """Outcome of the check against ЕГРЮЛ/ЕГРИП: what followed the registry
    silently and what is left for a person."""

    model_config = ConfigDict(from_attributes=True)

    organization: OrganizationRead
    updated_fields: list[FieldChangeRead]
    discrepancies: list[DiscrepancyRead]
