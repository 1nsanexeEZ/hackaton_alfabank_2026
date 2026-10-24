"""Бенефициары со слов клиента (115-ФЗ, ст. 6.1, ст. 7 п. 14) и страна третьих лиц.

Пустой список — тоже ответ: больше 25% ни у кого и никто не контролирует компанию иначе. Банк
сверяет ответ с ЕГРЮЛ (enrichment). Страна — код ISO 3166-1 alpha-2, Россию не указывают.
"""

from datetime import timedelta

import pytest

from src.core.exceptions.exceptions import ConflictError, ValidationError
from src.modules.applications.domain.value_objects import (
    Actor,
    DeclaredOwner,
    OwnersDeclaration,
    ThirdParty,
)
from src.modules.applications.infrastructure.repositories.mappers import (
    owners_in,
    owners_out,
    third_party_in,
    third_party_out,
)
from tests.applications.unit.factories import APPLICANT_ID, NOW, ready_draft, snapshot

OWNER = DeclaredOwner("Смирнова Анна Сергеевна", "ownership")
SHADOW = DeclaredOwner("Теневой Тимур", "control", "AE")


def test_owners_and_nobody_are_answers() -> None:
    declaration = OwnersDeclaration((OWNER, SHADOW), APPLICANT_ID, NOW)
    assert declaration.owners == (OWNER, SHADOW)
    assert OwnersDeclaration((), APPLICANT_ID, NOW).owners == ()


@pytest.mark.parametrize(
    ("owner", "field", "code"),
    [
        (DeclaredOwner(" ", "ownership"), "beneficial_owners.owners.0.name", "invalid"),
        (DeclaredOwner("Смирнова", "gift"), "beneficial_owners.owners.0.basis", "unknown"),  # type: ignore[arg-type]
        (
            DeclaredOwner("Смирнова", "control", "Iran"),
            "beneficial_owners.owners.0.country",
            "unknown",
        ),
    ],
)
def test_invalid_owners(owner: DeclaredOwner, field: str, code: str) -> None:
    with pytest.raises(ValidationError) as error:
        OwnersDeclaration((owner,), APPLICANT_ID, NOW)
    assert error.value.details == {"field": field, "code": code}


def test_too_many_owners() -> None:
    owners = tuple(DeclaredOwner(f"Совладелец № {i}", "ownership") for i in range(21))
    with pytest.raises(ValidationError):
        OwnersDeclaration(owners, APPLICANT_ID, NOW)


def test_third_party_country() -> None:
    party = ThirdParty("person", "Хоссейни Али Реза", country="IR")
    party.validate("beneficiary.beneficiary")
    with pytest.raises(ValidationError) as error:
        ThirdParty("person", "Хоссейни Али Реза", country="ir").validate("beneficiary.beneficiary")
    assert error.value.details == {"field": "beneficiary.beneficiary.country", "code": "unknown"}


def test_declare_replace_and_withdraw_in_a_draft() -> None:
    application = ready_draft()
    assert application.beneficial_owners is None
    application.declare_owners((OWNER,), account_id=APPLICANT_ID, now=NOW)
    later = NOW + timedelta(hours=1)
    application.declare_owners((OWNER, SHADOW), account_id=APPLICANT_ID, now=later)
    assert application.beneficial_owners is not None
    assert application.beneficial_owners.owners == (OWNER, SHADOW)
    assert application.beneficial_owners.declared_at == later
    application.withdraw_owners(later)
    assert application.beneficial_owners is None


def test_answer_is_frozen_after_submission() -> None:
    application = ready_draft()
    application.submit(
        snapshot(), actor=Actor.client(APPLICANT_ID), has_other_active=False, now=NOW
    )
    with pytest.raises(ConflictError):
        application.declare_owners((OWNER,), account_id=APPLICANT_ID, now=NOW)


def test_storage_round_trip() -> None:
    declaration = OwnersDeclaration((OWNER, SHADOW), APPLICANT_ID, NOW)
    assert owners_in(owners_out(declaration)) == declaration
    assert owners_in(None) is None
    party = ThirdParty("organization", "ООО «Принципал»", "7707083893", "KZ")
    assert third_party_in(third_party_out(party)) == party
    stored = third_party_out(party)
    assert stored is not None
    del stored["country"]  # записи до страны
    assert third_party_in(stored) == ThirdParty("organization", "ООО «Принципал»", "7707083893")
