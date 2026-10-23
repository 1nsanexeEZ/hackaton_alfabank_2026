from datetime import datetime
from typing import Annotated, Self, TypeAlias
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

from src.modules.identity.application.dto.accounts import (
    CreateAccountDTO,
    ProfileChangesDTO,
    ProfileDTO,
    UpdateAccountDTO,
)
from src.modules.identity.application.dto.common import UNSET
from src.modules.identity.domain.login_policy import normalize_email, normalize_phone
from src.modules.identity.presentation.schemas.roles import RoleShort

Phone: TypeAlias = Annotated[str, AfterValidator(normalize_phone)]
Email: TypeAlias = Annotated[EmailStr, AfterValidator(normalize_email)]
Password: TypeAlias = Annotated[SecretStr, Field(min_length=8, max_length=128)]


class ProfileData(BaseModel):
    last_name: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=150)

    def to_dto(self) -> ProfileDTO:
        return ProfileDTO(**self.model_dump())


class ProfileUpdate(BaseModel):
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=150)

    def to_dto(self) -> ProfileChangesDTO:
        """Fields that weren't sent stay as they are; null clears a field."""
        return ProfileChangesDTO(**self.model_dump(exclude_unset=True))


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

    def to_dto(self) -> CreateAccountDTO:
        return CreateAccountDTO(
            email=self.email,
            phone=self.phone,
            password=self.password.get_secret_value(),
            role_id=self.role_id,
            profile=self.profile.to_dto(),
        )


class AccountUpdate(BaseModel):
    email: Email | None = None
    phone: Phone | None = None
    password: Password | None = None
    role_id: UUID | None = None
    profile: ProfileUpdate | None = None

    def to_dto(self) -> UpdateAccountDTO:
        """`email`/`phone` sent as null clear the login; not sent — stay."""
        sent = self.model_fields_set
        return UpdateAccountDTO(
            email=self.email if "email" in sent else UNSET,
            phone=self.phone if "phone" in sent else UNSET,
            password=self.password.get_secret_value() if self.password is not None else None,
            role_id=self.role_id,
            profile=self.profile.to_dto() if self.profile is not None else None,
        )


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None
    phone: str | None
    role: RoleShort
    profile: ProfileRead | None
    created_at: datetime
    deleted_at: datetime | None
