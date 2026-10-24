"""Выгодоприобретатель и залогодатель — третье лицо (115-ФЗ): что клиент говорит в заявке.

Ответ «действую к своей выгоде» — тоже ответ, он хранится с тем, кто его дал, и моментом.
Выгодоприобретатель — человек по ФИО или организация по наименованию и ИНН, с основанием.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from src.core.domain import Money
from src.core.exceptions.exceptions import ConflictError, ValidationError
from src.modules.applications.domain.value_objects import (
    Actor,
    BeneficiaryDeclaration,
    CollateralDeclaration,
    ThirdParty,
)
from src.modules.applications.infrastructure.repositories.mappers import (
    beneficiary_in,
    beneficiary_out,
    collateral_in,
    collateral_out,
)
from tests.applications.unit.factories import APPLICANT_ID, NOW, ready_draft, snapshot

AGENT = ThirdParty("organization", "ООО «Транзитный агент»", "7707115094")
PERSON = ThirdParty("person", "Посредников Павел Павлович")


def _declaration(**overrides: object) -> BeneficiaryDeclaration:
    values: dict[str, object] = {
        "acts_for_third_party": True,
        "declared_by": APPLICANT_ID,
        "declared_at": NOW,
        "beneficiary": AGENT,
        "basis": "agency",
        **overrides,
    }
    return BeneficiaryDeclaration(**values)  # type: ignore[arg-type]


def test_acting_for_itself_is_an_answer() -> None:
    declaration = _declaration(acts_for_third_party=False, beneficiary=None, basis=None)
    assert not declaration.acts_for_third_party and declaration.declared_by == APPLICANT_ID


@pytest.mark.parametrize(
    ("overrides", "field", "code"),
    [
        ({"beneficiary": None}, "beneficiary.beneficiary", "missing"),
        ({"basis": None}, "beneficiary.basis", "missing"),
        ({"basis": "gift"}, "beneficiary.basis", "missing"),
        (
            {"beneficiary": ThirdParty("organization", "ООО «Агент»")},
            "beneficiary.beneficiary.inn",
            "missing",
        ),
        (
            {"beneficiary": ThirdParty("organization", "ООО «Агент»", "7707115095")},
            "beneficiary.beneficiary.inn",
            "bad_checksum",
        ),
        ({"beneficiary": ThirdParty("person", " ")}, "beneficiary.beneficiary.name", "invalid"),
        (
            {"acts_for_third_party": False, "basis": None},
            "beneficiary.beneficiary",
            "unexpected",
        ),
    ],
)
def test_invalid_answers(overrides: dict[str, object], field: str, code: str) -> None:
    with pytest.raises(ValidationError) as error:
        _declaration(**overrides)
    assert error.value.details == {"field": field, "code": code}


def test_person_without_inn_and_entrepreneur_inn() -> None:
    assert _declaration(beneficiary=PERSON, basis="mandate").beneficiary == PERSON
    entrepreneur = ThirdParty("organization", "ИП Иванов", "770669871605")
    assert _declaration(beneficiary=entrepreneur).beneficiary == entrepreneur


def test_pledgor_only_for_third_party_collateral() -> None:
    value = Money.of(Decimal("1000000"))
    pledge = CollateralDeclaration("equipment", "Станок", value, "third_party", PERSON)
    assert pledge.owner_party == PERSON
    with pytest.raises(ValidationError):
        CollateralDeclaration("equipment", "Станок", value, "self", PERSON)
    assert CollateralDeclaration("equipment", "Станок", value, "third_party").owner_party is None


def test_declare_replace_and_withdraw_in_a_draft() -> None:
    application = ready_draft()
    assert application.beneficiary is None
    application.declare_beneficiary(
        acts_for_third_party=False, beneficiary=None, basis=None, account_id=APPLICANT_ID, now=NOW
    )
    assert application.beneficiary is not None
    later = NOW + timedelta(hours=1)
    application.declare_beneficiary(
        acts_for_third_party=True,
        beneficiary=AGENT,
        basis="commission",
        account_id=APPLICANT_ID,
        now=later,
    )
    assert application.beneficiary.declared_at == later
    assert application.beneficiary.beneficiary == AGENT
    application.withdraw_beneficiary(later)
    assert application.beneficiary is None


def test_answer_is_frozen_after_submission() -> None:
    application = ready_draft()
    application.submit(
        snapshot(), actor=Actor.client(APPLICANT_ID), has_other_active=False, now=NOW
    )
    with pytest.raises(ConflictError):
        application.declare_beneficiary(
            acts_for_third_party=False,
            beneficiary=None,
            basis=None,
            account_id=APPLICANT_ID,
            now=NOW,
        )


def test_storage_round_trip() -> None:
    declaration = _declaration(beneficiary=PERSON, basis="trust_management")
    assert beneficiary_in(beneficiary_out(declaration)) == declaration
    assert beneficiary_in(None) is None
    pledge = CollateralDeclaration(
        "real_estate", "Офис", Money.of(Decimal("5000000")), "third_party", AGENT
    )
    stored = collateral_out(pledge)
    assert collateral_in(stored) == pledge
    assert stored is not None
    del stored["owner_party"]  # записи до выгодоприобретателя
    assert collateral_in(stored) == CollateralDeclaration(
        "real_estate", "Офис", Money.of(Decimal("5000000")), "third_party"
    )
