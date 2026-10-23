from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.modules.identity.domain.enums import ConsentType


class ConsentGive(BaseModel):
    types: list[ConsentType] = Field(min_length=1, max_length=2)


class ConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: ConsentType
    given_at: datetime
    valid_until: datetime | None = Field(
        description="personal_data — null (until revoked), credit_bureau_personal — 6 months"
    )
    revoked_at: datetime | None
    active: bool
    text_version: str = Field(description="Edition of the consent text that was shown")
