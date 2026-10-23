"""What a login is: an email in any case or a phone in any format."""

import re
from dataclasses import dataclass

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


def normalize_email(value: str) -> str:
    return value.lower()


@dataclass(frozen=True, slots=True)
class Login:
    """Exactly one of the two is set."""

    email: str | None = None
    phone: str | None = None


def parse_login(raw: str) -> Login | None:
    """Email in any case or phone in any format (`8 (999) 123-45-67`); None — neither."""
    raw = raw.strip()
    if "@" in raw:
        return Login(email=normalize_email(raw))
    try:
        return Login(phone=normalize_phone(raw))
    except ValueError:
        return None
