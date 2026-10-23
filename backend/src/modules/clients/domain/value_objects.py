"""Value objects of a client company: requisites with check digits, registry
data, names. Each one validates itself in the constructor."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Self

from src.core.exceptions.exceptions import ValidationError
from src.modules.clients.domain.enums import (
    LegalForm,
    RegistryStatus,
    TaxRegime,
    VerificationStatus,
)


def _invalid(field_name: str, code: str, message: str) -> ValidationError:
    return ValidationError(message, details={"field": field_name, "code": code})


def _require_aware(moment: datetime, name: str) -> None:
    if moment.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


# The patent system is open to entrepreneurs only.
ENTREPRENEUR_ONLY_REGIMES: frozenset[TaxRegime] = frozenset({TaxRegime.PATENT})


def parse_enum[E: StrEnum](kind: type[E], value: str, field_name: str) -> E:
    try:
        return kind(value)
    except ValueError:
        raise _invalid(field_name, "unknown", f"Unknown {field_name}: {value!r}") from None


# --- requisites ---------------------------------------------------------------

_INN_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN_W11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN_W12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _inn_check_digit(digits: str, weights: tuple[int, ...]) -> int:
    return sum(int(d) * w for d, w in zip(digits, weights, strict=True)) % 11 % 10


@dataclass(frozen=True, slots=True)
class Inn:
    """10 digits — a legal entity (LLC, JSC), 12 — an individual entrepreneur."""

    value: str

    def __post_init__(self) -> None:
        v = self.value
        if re.fullmatch(r"[0-9]{10}|[0-9]{12}", v) is None:
            raise _invalid("inn", "bad_format", "INN must have 10 or 12 digits")
        if len(v) == 10:
            valid = _inn_check_digit(v[:9], _INN_W10) == int(v[9])
        else:
            valid = _inn_check_digit(v[:10], _INN_W11) == int(v[10]) and _inn_check_digit(
                v[:11], _INN_W12
            ) == int(v[11])
        if not valid:
            raise _invalid("inn", "bad_checksum", "INN check digit is wrong")

    @property
    def is_entrepreneur(self) -> bool:
        return len(self.value) == 12

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Ogrn:
    """ОГРН (13 digits, starts with 1 or 5) of a legal entity or ОГРНИП
    (15 digits, starts with 3) of an entrepreneur."""

    value: str

    def __post_init__(self) -> None:
        v = self.value
        if re.fullmatch(r"[15][0-9]{12}|3[0-9]{14}", v) is None:
            raise _invalid("ogrn", "bad_format", "OGRN must have 13 digits, OGRNIP — 15")
        modulo = 11 if len(v) == 13 else 13
        if int(v[:-1]) % modulo % 10 != int(v[-1]):
            raise _invalid("ogrn", "bad_checksum", "OGRN check digit is wrong")

    @property
    def is_entrepreneur(self) -> bool:
        return len(self.value) == 15

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Kpp:
    """Tax registration reason code of a legal entity: `770101001`."""

    value: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9]{4}[0-9A-Z]{2}[0-9]{3}", self.value) is None:
            raise _invalid("kpp", "bad_format", "KPP must look like 770101001")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Requisites:
    """Registration identifiers:
    ИНН 10 ⇔ ОГРН 13 ⇔ LLC/JSC ⇔ КПП;  ИНН 12 ⇔ ОГРНИП 15 ⇔ IE ⇔ no КПП.
    INN, OGRN and the legal form are fixed for the life of the company; КПП
    follows the registry (it changes when the company moves to another tax
    office)."""

    inn: Inn
    ogrn: Ogrn
    legal_form: LegalForm
    kpp: Kpp | None = None

    def __post_init__(self) -> None:
        entrepreneur = self.legal_form.is_entrepreneur
        if self.inn.is_entrepreneur != entrepreneur:
            raise _invalid("inn", "inconsistent_requisites", "INN does not match the legal form")
        if self.ogrn.is_entrepreneur != entrepreneur:
            raise _invalid("ogrn", "inconsistent_requisites", "OGRN does not match the legal form")
        if entrepreneur and self.kpp is not None:
            raise _invalid("kpp", "inconsistent_requisites", "An entrepreneur has no KPP")
        if not entrepreneur and self.kpp is None:
            raise _invalid("kpp", "missing", "KPP is required for a legal entity")

    @classmethod
    def of(cls, inn: str, ogrn: str, legal_form: str, kpp: str | None = None) -> Self:
        return cls(
            inn=Inn(inn),
            ogrn=Ogrn(ogrn),
            legal_form=parse_enum(LegalForm, legal_form, "legal_form"),
            kpp=Kpp(kpp) if kpp is not None else None,
        )


# --- activity, address, period ------------------------------------------------

# ОКВЭД 2 sections by the first two digits of a code (division).
_OKVED_SECTIONS: tuple[tuple[str, int, int], ...] = (
    ("A", 1, 3),
    ("B", 5, 9),
    ("C", 10, 33),
    ("D", 35, 35),
    ("E", 36, 39),
    ("F", 41, 43),
    ("G", 45, 47),
    ("H", 49, 53),
    ("I", 55, 56),
    ("J", 58, 63),
    ("K", 64, 66),
    ("L", 68, 68),
    ("M", 69, 75),
    ("N", 77, 82),
    ("O", 84, 84),
    ("P", 85, 85),
    ("Q", 86, 88),
    ("R", 90, 93),
    ("S", 94, 96),
    ("T", 97, 98),
    ("U", 99, 99),
)


def _okved_section(division: int) -> str | None:
    return next((s for s, low, high in _OKVED_SECTIONS if low <= division <= high), None)


@dataclass(frozen=True, slots=True)
class OkvedCode:
    """ОКВЭД 2 code: `62`, `62.01`, `47.19.1`. `division` — its first two
    digits (products filter by them), `section` — the letter A..U."""

    value: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9]{2}(\.[0-9]{1,2}){0,2}", self.value) is None:
            raise _invalid("okved", "bad_format", "OKVED code must look like 62.01")
        if _okved_section(int(self.value[:2])) is None:
            raise _invalid("okved", "unknown_division", "No such OKVED division")

    @property
    def division(self) -> str:
        return self.value[:2]

    @property
    def section(self) -> str:
        section = _okved_section(int(self.division))
        assert section is not None
        return section

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Address:
    full: str
    # Subject of the federation: "77" — Moscow.
    region_code: str

    def __post_init__(self) -> None:
        if not self.full.strip() or len(self.full) > 500:
            raise _invalid("address", "invalid", "Address is empty or too long")
        if re.fullmatch(r"[0-9]{2}", self.region_code) is None:
            raise _invalid("region_code", "bad_format", "Region code must have 2 digits")


@dataclass(frozen=True, slots=True)
class FiscalPeriod:
    """A year or one of its quarters (`quarter` None — the whole year)."""

    year: int
    quarter: int | None = None

    def __post_init__(self) -> None:
        if not 2000 <= self.year <= 2100:
            raise _invalid("period_year", "out_of_range", "Year is out of range")
        if self.quarter is not None and not 1 <= self.quarter <= 4:
            raise _invalid("period_quarter", "out_of_range", "Quarter must be 1..4")

    @property
    def is_annual(self) -> bool:
        return self.quarter is None

    @property
    def ends_on(self) -> date:
        if self.quarter is None or self.quarter == 4:
            return date(self.year, 12, 31)
        return date(self.year, self.quarter * 3 + 1, 1) - timedelta(days=1)

    def is_closed(self, today: date) -> bool:
        """A report is possible only for a period that is over."""
        return self.ends_on < today

    def __str__(self) -> str:
        return str(self.year) if self.quarter is None else f"{self.year} Q{self.quarter}"


# --- people and registry check ------------------------------------------------


@dataclass(frozen=True, slots=True, repr=False)
class PersonName:
    """Full name of a person. Personal data: repr() is masked so a name never
    lands in logs or tracebacks; use `full` explicitly to show it."""

    last_name: str
    first_name: str
    middle_name: str | None = None

    def __post_init__(self) -> None:
        for name in ("last_name", "first_name"):
            value = getattr(self, name)
            if not value.strip() or len(value) > 100:
                raise _invalid(name, "invalid", "Name is empty or too long")
        if self.middle_name is not None and len(self.middle_name) > 100:
            raise _invalid("middle_name", "invalid", "Name is too long")

    @property
    def full(self) -> str:
        parts = (self.last_name, self.first_name, self.middle_name)
        return " ".join(p.strip() for p in parts if p and p.strip())

    @property
    def short(self) -> str:
        """`Петров П. П.`"""
        initials = " ".join(f"{p.strip()[0]}." for p in (self.first_name, self.middle_name) if p)
        return f"{self.last_name.strip()} {initials}"

    def normalized(self) -> str:
        """For comparison with the registry: lower case, ё → е, single spaces."""
        return " ".join(self.full.lower().replace("ё", "е").split())

    def matches(self, other: "PersonName") -> bool:
        return self.normalized() == other.normalized()

    def __repr__(self) -> str:
        return "PersonName(***)"


@dataclass(frozen=True, slots=True)
class Discrepancy:
    """One field where the declared data differs from the registry."""

    field: str
    declared: str | None
    registry: str | None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Outcome of the check of the declared data against ЕГРЮЛ/ЕГРИП."""

    status: VerificationStatus = VerificationStatus.UNVERIFIED
    checked_at: datetime | None = None
    discrepancies: tuple[Discrepancy, ...] = ()

    def __post_init__(self) -> None:
        if self.status is VerificationStatus.UNVERIFIED:
            if self.checked_at is not None or self.discrepancies:
                raise ValueError("An unverified company has no check results")
            return
        if self.checked_at is None:
            raise ValueError("A checked company needs the moment of the check")
        _require_aware(self.checked_at, "checked_at")
        if (self.status is VerificationStatus.MISMATCH) != bool(self.discrepancies):
            raise ValueError("Discrepancies go with the mismatch status only")

    @classmethod
    def verified(cls, now: datetime) -> Self:
        return cls(VerificationStatus.VERIFIED, now)

    @classmethod
    def mismatch(cls, now: datetime, discrepancies: tuple[Discrepancy, ...]) -> Self:
        return cls(VerificationStatus.MISMATCH, now, discrepancies)


MAX_NAME_LENGTH = 255


@dataclass(frozen=True, slots=True)
class RegistryExtract:
    """What ЕГРЮЛ/ЕГРИП says about a company, in our value objects. `kpp`
    None — the registry did not say (an entrepreneur has none anyway)."""

    inn: Inn
    ogrn: Ogrn
    name: str
    address: Address
    okved_main: OkvedCode
    status: RegistryStatus
    head: PersonName
    kpp: Kpp | None = None
    okved_extra: tuple[OkvedCode, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > MAX_NAME_LENGTH:
            raise _invalid("name", "invalid", "Company name is empty or too long")


@dataclass(frozen=True, slots=True)
class FieldChange:
    """A field of the card brought to the registry: `address.full` was
    `before`, now is `after`."""

    field: str
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class RegistryChanges:
    """Outcome of a check against the registry: `updated` — fields that
    followed the registry silently, `discrepancies` — what is left for a
    person to look at (the head)."""

    updated: tuple[FieldChange, ...] = ()
    discrepancies: tuple[Discrepancy, ...] = ()
