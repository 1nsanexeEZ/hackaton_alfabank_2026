from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.modules.identity.application.dto.auth import CredentialsDTO, IssuedTokenDTO


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254, description="Email or phone")
    password: SecretStr = Field(min_length=1, max_length=128)

    def to_dto(self) -> CredentialsDTO:
        return CredentialsDTO(login=self.login, password=self.password.get_secret_value())


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

    @classmethod
    def from_dto(cls, issued: IssuedTokenDTO) -> Self:
        return cls(access_token=issued.access_token, expires_in=issued.expires_in)


class DemoLoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254, description="Email or phone of a demo account")


class DemoAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    login: str = Field(description="Email to pass to /auth/demo-login")
    phone: str | None
    role: str
    caption: str
    full_name: str


class JwksResponse(BaseModel):
    keys: list[dict[str, Any]]
