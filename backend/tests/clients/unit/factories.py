"""Demo companies (seed/demo_data.py) as domain objects for unit tests."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from seed.demo_data import COMPANIES_BY_CODE, DemoPerson
from src.modules.clients.domain.member import Actor
from src.modules.clients.domain.organization import Organization
from src.modules.clients.domain.rights import MemberRole, OrgPermission, PowerOfAttorney
from src.modules.clients.domain.value_objects import (
    Address,
    OkvedCode,
    PersonName,
    RegistryStatus,
    Requisites,
    TaxRegime,
)

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
BANK = Actor.bank()


def person(demo: DemoPerson) -> PersonName:
    return PersonName(demo.last_name, demo.first_name, demo.middle_name)


def head_of(code: str) -> PersonName:
    return person(COMPANIES_BY_CODE[code].registry_head)


def stranger_name() -> PersonName:
    return PersonName("Посторонний", "Пётр", "Петрович")


def organization(code: str = "romashka", **overrides: Any) -> Organization:
    company = COMPANIES_BY_CODE[code]
    values: dict[str, Any] = {
        "id": uuid4(),
        "requisites": Requisites.of(company.inn, company.ogrn, company.legal_form, company.kpp),
        "name": company.name,
        "registered_at": date(2020, 10, 21),
        "address": Address("г. Москва, ул. Тверская, д. 1", "77"),
        "okved_main": OkvedCode(company.okved_main),
        "tax_regime": TaxRegime.USN if company.legal_form == "IE" else TaxRegime.OSN,
        "employees_count": 10,
        "registry_status": RegistryStatus(company.registry_status),
        "registry_head": head_of(code),
    }
    values.update(overrides)
    return Organization.register(**values, now=NOW)


def with_head(code: str = "romashka") -> tuple[Organization, UUID]:
    """A company with its head confirmed by the registry (owner of an IE)."""
    org = organization(code)
    head_id = uuid4()
    role = MemberRole.OWNER if org.legal_form.is_entrepreneur else MemberRole.DIRECTOR
    org.add_member(BANK, head_id, role, NOW, person=head_of(code))
    org.pull_events()
    return org, head_id


def add(org: Organization, role: MemberRole, actor: Actor = BANK) -> UUID:
    account_id = uuid4()
    org.add_member(actor, account_id, role, NOW, person=stranger_name())
    org.pull_events()
    return account_id


def poa(
    *scope: OrgPermission,
    issued_at: date | None = None,
    valid_until: date | None = None,
    number: str = "77 АА 1234567",
) -> PowerOfAttorney:
    return PowerOfAttorney(
        number=number,
        issued_at=issued_at or NOW.date() - timedelta(days=30),
        valid_until=valid_until or NOW.date() + timedelta(days=365),
        scope=frozenset(scope or (OrgPermission.SIGN,)),
    )
