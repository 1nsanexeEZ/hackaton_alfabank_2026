import re
from datetime import datetime
from typing import Annotated, Any, Self, TypeAlias
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    model_validator,
)

from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.modules.identity.facade import ConsentType

_PHONE_RE = re.compile(r"^\+\d{10,15}$")


def normalize_phone(value: str) -> str:
    """'8 (999) 123-45-67' -> '+79991234567'."""
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    phone = "+" + digits
    if not _PHONE_RE.match(phone):
        raise ValueError("Phone must contain 10-15 digits")
    return phone


def _lower(value: str) -> str:
    return value.lower()


Phone: TypeAlias = Annotated[str, AfterValidator(normalize_phone)]
Email: TypeAlias = Annotated[EmailStr, AfterValidator(_lower)]
Password: TypeAlias = Annotated[SecretStr, Field(min_length=8, max_length=128)]


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254, description="Email or phone")
    password: SecretStr = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class DemoLoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254, description="Email or phone of a demo account")


class DemoAccountRead(BaseModel):
    login: str = Field(description="Email to pass to /auth/demo-login")
    phone: str | None
    role: str
    caption: str
    full_name: str


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    permissions: list[Permissions] = Field(default_factory=list)
    policies: dict[Permissions, list[Policies]] = Field(default_factory=dict)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[Permissions] | None = None
    policies: dict[Permissions, list[Policies]] | None = None


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    permissions: list[str]
    policies: dict[str, list[str]]
    created_at: datetime
    updated_at: datetime


class RoleShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class ProfileData(BaseModel):
    last_name: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=150)


class ProfileUpdate(BaseModel):
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=150)


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    last_name: str
    first_name: str
    middle_name: str | None
    position: str | None


class AccountCreate(BaseModel):
    email: Email | None = None
    phone: Phone | None = None
    password: Password
    role_id: UUID
    profile: ProfileData

    @model_validator(mode="after")
    def _has_login(self) -> Self:
        if self.email is None and self.phone is None:
            raise ValueError("Either email or phone is required")
        return self


class AccountUpdate(BaseModel):
    email: Email | None = None
    phone: Phone | None = None
    password: Password | None = None
    role_id: UUID | None = None
    profile: ProfileUpdate | None = None


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None
    phone: str | None
    role: RoleShort
    profile: ProfileRead | None
    created_at: datetime
    deleted_at: datetime | None


class MeRead(AccountRead):
    permissions: list[str]
    policies: dict[str, list[str]]


class JwksResponse(BaseModel):
    keys: list[dict[str, Any]]


class ConsentGive(BaseModel):
    types: list[ConsentType] = Field(min_length=1, max_length=2)


class ConsentRead(BaseModel):
    type: ConsentType
    given_at: datetime
    valid_until: datetime | None = Field(
        description="personal_data — null (until revoked), credit_bureau_personal — 6 months"
    )
    revoked_at: datetime | None
    active: bool
    text_version: str = Field(description="Edition of the consent text that was shown")
