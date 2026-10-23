from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.identity.domain.enums import CompanyConsentType, PersonalConsentType


class ConsentGive(BaseModel):
    types: list[PersonalConsentType] = Field(min_length=1, max_length=2)


class ConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: PersonalConsentType
    given_at: datetime
    valid_until: datetime | None = Field(
        description="personal_data — null (until revoked), credit_bureau_personal — 6 months"
    )
    revoked_at: datetime | None
    active: bool
    text_version: str = Field(description="Edition of the consent text that was shown")


class OrganizationConsentGive(BaseModel):
    types: list[CompanyConsentType] = Field(min_length=1, max_length=1)


class OrganizationConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: CompanyConsentType
    organization_id: UUID
    given_by: UUID = Field(description="Account of the representative who gave it")
    given_at: datetime
    valid_until: datetime | None = Field(description="credit_bureau_company — 6 months")
    revoked_at: datetime | None
    revoked_by: UUID | None = Field(description="Account of the representative who revoked it")
    active: bool
    text_version: str = Field(description="Edition of the consent text that was shown")
