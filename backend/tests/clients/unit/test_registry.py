"""Organization.apply_registry: the card follows ЕГРЮЛ/ЕГРИП, the head does not."""

from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest

from seed.demo_data import COMPANIES_BY_CODE
from src.modules.clients.domain.enums import (
    Authority,
    MemberRole,
    RegistryStatus,
    VerificationStatus,
)
from src.modules.clients.domain.events import (
    OrganizationVerificationMismatch,
    OrganizationVerified,
)
from src.modules.clients.domain.organization import Organization
from src.modules.clients.domain.value_objects import (
    Address,
    Discrepancy,
    FieldChange,
    Inn,
    Kpp,
    Ogrn,
    OkvedCode,
    PersonName,
    RegistryExtract,
)
from tests.clients.unit.factories import BANK, NOW, head_of, organization, stranger_name, with_head

R = MemberRole


def extract_of(org: Organization, **overrides: Any) -> RegistryExtract:
    """What the registry says when nothing has changed."""
    same = RegistryExtract(
        inn=org.requisites.inn,
        ogrn=org.requisites.ogrn,
        name=org.name,
        address=org.address,
        okved_main=org.okved_main,
        status=org.registry_status,
        head=org.registry_head or stranger_name(),
        kpp=org.requisites.kpp,
        okved_extra=org.okved_extra,
    )
    return replace(same, **overrides)


def test_nothing_changed_is_verified() -> None:
    org = organization("romashka")

    changes = org.apply_registry(extract_of(org), NOW)

    assert changes.updated == () and changes.discrepancies == ()
    assert org.verification.status is VerificationStatus.VERIFIED
    assert org.verification.checked_at == NOW
    assert [type(e) for e in org.pull_events()] == [OrganizationVerified]


def test_name_follows_the_registry() -> None:
    org = organization("romashka")

    changes = org.apply_registry(extract_of(org, name="ООО «Ромашка и Ко»"), NOW)

    assert changes.updated == (FieldChange("name", "ООО «Ромашка»", "ООО «Ромашка и Ко»"),)
    assert org.name == "ООО «Ромашка и Ко»"
    assert org.verification.status is VerificationStatus.VERIFIED


def test_address_follows_the_registry() -> None:
    org = organization("romashka")
    moved = Address("г. Санкт-Петербург, Невский пр., д. 5", "78")

    changes = org.apply_registry(extract_of(org, address=moved), NOW)

    assert changes.updated == (
        FieldChange("address.full", "г. Москва, ул. Тверская, д. 1", moved.full),
        FieldChange("address.region_code", "77", "78"),
    )
    assert org.address == moved


def test_kpp_follows_the_registry_inn_and_ogrn_stay() -> None:
    org = organization("romashka")
    inn, ogrn = org.requisites.inn, org.requisites.ogrn

    changes = org.apply_registry(extract_of(org, kpp=Kpp("770143001")), NOW)

    assert changes.updated == (FieldChange("kpp", "770101001", "770143001"),)
    assert org.requisites.kpp == Kpp("770143001")
    assert org.requisites.inn == inn and org.requisites.ogrn == ogrn


def test_kpp_unknown_to_the_registry_is_kept() -> None:
    org = organization("romashka")

    changes = org.apply_registry(extract_of(org, kpp=None), NOW)

    assert changes.updated == ()
    assert org.requisites.kpp == Kpp("770101001")


def test_ogrn_never_changes() -> None:
    org = organization("romashka")
    other = Ogrn(COMPANIES_BY_CODE["vector"].ogrn)

    changes = org.apply_registry(extract_of(org, ogrn=other), NOW)

    assert changes.updated == ()
    assert org.requisites.ogrn.value == COMPANIES_BY_CODE["romashka"].ogrn


def test_extract_of_another_company_is_refused() -> None:
    org = organization("romashka")
    vector = Inn(COMPANIES_BY_CODE["vector"].inn)

    with pytest.raises(ValueError):
        org.apply_registry(extract_of(org, inn=vector), NOW)
    assert org.verification.status is VerificationStatus.UNVERIFIED
    assert org.pull_events() == []


def test_main_okved_follows_the_registry() -> None:
    org = organization("romashka")

    changes = org.apply_registry(extract_of(org, okved_main=OkvedCode("56.29")), NOW)

    assert changes.updated == (FieldChange("okved_main", "56.10", "56.29"),)
    assert org.okved_main == OkvedCode("56.29")


def test_extra_okved_follow_the_registry() -> None:
    org = organization("romashka", okved_extra=[OkvedCode("56.30")])
    extra = (OkvedCode("56.21"), OkvedCode("56.30"))

    changes = org.apply_registry(extract_of(org, okved_extra=extra), NOW)

    assert changes.updated == (FieldChange("okved_extra", "56.30", "56.21, 56.30"),)
    assert org.okved_extra == extra


def test_extra_okved_in_another_order_are_not_a_change() -> None:
    org = organization("romashka", okved_extra=[OkvedCode("56.21"), OkvedCode("56.30")])

    extract = extract_of(org, okved_extra=(OkvedCode("56.30"), OkvedCode("56.21")))
    changes = org.apply_registry(extract, NOW)

    assert changes.updated == ()
    assert org.okved_extra == (OkvedCode("56.21"), OkvedCode("56.30"))


def test_registry_status_follows_the_registry() -> None:
    org = organization("romashka")

    changes = org.apply_registry(extract_of(org, status=RegistryStatus.LIQUIDATING), NOW)

    assert changes.updated == (FieldChange("registry_status", "active", "liquidating"),)
    assert org.registry_status is RegistryStatus.LIQUIDATING
    # The stop factor belongs to decision: the check itself passes.
    assert org.verification.status is VerificationStatus.VERIFIED


def test_new_head_in_the_registry_is_a_discrepancy() -> None:
    org, head_id = with_head("romashka")
    new_head = PersonName("Новикова", "Нина", "Николаевна")

    changes = org.apply_registry(extract_of(org, head=new_head), NOW)

    discrepancy = Discrepancy("head_name", "Смирнова А. С.", "Новикова Н. Н.")
    # Smirnova acts as the head too: one discrepancy, not two.
    assert changes.discrepancies == (discrepancy,)
    assert changes.updated == ()
    assert org.registry_head == head_of("romashka")
    assert org.member(head_id).authority is Authority.REGISTRY
    assert org.verification.status is VerificationStatus.MISMATCH
    assert org.verification.discrepancies == (discrepancy,)
    [event] = org.pull_events()
    assert isinstance(event, OrganizationVerificationMismatch)
    assert event.discrepancies == (discrepancy,)


def test_unknown_head_is_not_filled_in_silently() -> None:
    org = organization("romashka", registry_head=None)

    changes = org.apply_registry(extract_of(org, head=head_of("romashka")), NOW)

    assert changes.discrepancies == (Discrepancy("head_name", None, "Смирнова А. С."),)
    assert org.registry_head is None


def test_director_under_another_name_is_a_discrepancy() -> None:
    org = organization("vector")
    petrov = uuid4()
    org.add_member(BANK, petrov, R.DIRECTOR, NOW, person=PersonName("Петров", "Пётр", "Петрович"))
    org.pull_events()

    names = {petrov: PersonName("Петров", "Пётр", "Петрович")}
    changes = org.apply_registry(extract_of(org), NOW, declared=names)

    assert changes.discrepancies == (Discrepancy("head_name", "Петров П. П.", "Сидоров С. С."),)
    assert org.verification.status is VerificationStatus.MISMATCH


def test_only_the_head_role_is_checked() -> None:
    org, head_id = with_head("romashka")
    accountant = uuid4()
    org.add_member(BANK, accountant, R.ACCOUNTANT, NOW, person=stranger_name())
    founder = uuid4()
    org.add_member(BANK, founder, R.OWNER, NOW, person=stranger_name())
    names = {
        head_id: PersonName("СМИРНОВА", "Анна", "Сергеевна"),
        accountant: stranger_name(),
        founder: stranger_name(),
    }

    changes = org.apply_registry(extract_of(org), NOW, declared=names)

    assert changes.discrepancies == ()
    assert org.verification.status is VerificationStatus.VERIFIED


def test_entrepreneur_is_checked_as_the_owner() -> None:
    org, owner = with_head("ivanov")

    names = {owner: head_of("ivanov")}
    assert org.apply_registry(extract_of(org), NOW, declared=names).discrepancies == ()

    renamed = {owner: PersonName("Иванов", "Иван", "Петрович")}
    changes = org.apply_registry(extract_of(org), NOW, declared=renamed)
    assert changes.discrepancies == (Discrepancy("head_name", "Иванов И. П.", "Иванов И. И."),)
    assert org.requisites.kpp is None


def test_head_without_a_known_name_is_skipped() -> None:
    org = organization("vector")
    org.add_member(BANK, uuid4(), R.DIRECTOR, NOW, person=None)

    assert org.apply_registry(extract_of(org), NOW, declared={}).discrepancies == ()


def test_a_later_check_replaces_the_previous_one() -> None:
    org = organization("romashka")
    org.apply_registry(extract_of(org, head=stranger_name()), NOW)

    org.apply_registry(extract_of(org), NOW)

    assert org.verification.status is VerificationStatus.VERIFIED
    assert org.verification.discrepancies == ()
