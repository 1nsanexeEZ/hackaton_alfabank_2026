from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CredentialsDTO:
    login: str
    password: str


@dataclass(frozen=True, slots=True)
class IssuedTokenDTO:
    access_token: str
    expires_at: datetime
    expires_in: int


@dataclass(frozen=True, slots=True)
class DemoAccountEntryDTO:
    """A demo account as the catalog declares it."""

    email: str
    caption: str


@dataclass(frozen=True, slots=True)
class DemoAccountDTO:
    login: str
    phone: str | None
    role: str
    caption: str
    full_name: str
