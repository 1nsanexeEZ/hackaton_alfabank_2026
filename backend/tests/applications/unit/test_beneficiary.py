"""Выгодоприобретатель и залогодатель — третье лицо (115-ФЗ): что клиент говорит в заявке.

Ответ «действую к своей выгоде» — тоже ответ, он хранится с тем, кто его дал, и моментом.
Выгодоприобретатель — человек по ФИО или организация по наименованию и ИНН, с основанием.
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from src.core.domain import Money
from src.core.exceptions.exceptions import ConflictError, ValidationError
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.entities import Document, InfoRequest
from src.modules.applications.domain.enums import ApplicationStatus
from src.modules.applications.domain.value_objects import (
    Actor,
    BeneficiaryDeclaration,
    CollateralDeclaration,
    Consents,
    ThirdParty,
)
from src.modules.applications.infrastructure.repositories.mappers import (
    beneficiary_in,
    beneficiary_out,
    collateral_in,
    collateral_out,
)
from tests.applications.unit.factories import APPLICANT_ID, NOW, ready_draft, snapshot, uploaded

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


# --- договор с третьим лицом --------------------------------------------------------------


def _acting_for_third_party(basis: str = "agency") -> CreditApplication:
    application = ready_draft()
    application.declare_beneficiary(
        acts_for_third_party=True,
        beneficiary=AGENT,
        basis=basis,  # type: ignore[arg-type]
        account_id=APPLICANT_ID,
        now=NOW,
    )
    return application


def _contract_violation(basis: str | None = "agency") -> dict[str, object]:
    violation: dict[str, object] = {
        "code": "missing",
        "field": "documents.beneficiary_contract",
        "type": "beneficiary_contract",
    }
    if basis is not None:
        violation["basis"] = basis
    return violation


def _submit(application: CreditApplication) -> None:
    application.submit(
        snapshot(), actor=Actor.client(APPLICANT_ID), has_other_active=False, now=NOW
    )


def _upload_contract(application: CreditApplication) -> Document:
    document = application.add_document(
        document_id=uuid4(),
        document_type="beneficiary_contract",
        filename="agency.pdf",
        content_type="application/pdf",
        size_bytes=4096,
        uploaded_by=APPLICANT_ID,
        now=NOW,
    )
    application.confirm_document(document.id, 4096, "application/pdf", NOW)
    return document


@pytest.mark.parametrize("basis", ["agency", "commission", "mandate", "trust_management"])
def test_contract_is_required_when_acting_for_a_third_party(basis: str) -> None:
    application = _acting_for_third_party(basis)
    violations = application.check_ready("LLC", has_other_active=False)
    assert [v.as_dict() for v in violations] == [_contract_violation(basis)]

    with pytest.raises(ValidationError) as error:
        _submit(application)
    assert error.value.details == {"violations": [_contract_violation(basis)]}
    assert application.status is ApplicationStatus.DRAFT


def test_uploaded_contract_lets_the_application_go() -> None:
    application = _acting_for_third_party()
    application.documents.append(uploaded("beneficiary_contract"))
    assert application.check_ready("LLC", has_other_active=False) == []
    _submit(application)
    assert application.status is ApplicationStatus.SUBMITTED


def test_announced_but_not_confirmed_contract_does_not_count() -> None:
    application = _acting_for_third_party()
    document = application.add_document(
        document_id=uuid4(),
        document_type="beneficiary_contract",
        filename="agency.pdf",
        content_type="application/pdf",
        size_bytes=4096,
        uploaded_by=APPLICANT_ID,
        now=NOW,
    )
    violations = application.check_ready("LLC", has_other_active=False)
    assert [v.as_dict() for v in violations] == [_contract_violation()]
    application.confirm_document(document.id, 4096, "application/pdf", NOW)
    assert application.check_ready("LLC", has_other_active=False) == []


def test_contract_is_not_needed_when_acting_alone_or_without_an_answer() -> None:
    application = ready_draft()
    assert application.check_ready("LLC", has_other_active=False) == []
    application.declare_beneficiary(
        acts_for_third_party=False, beneficiary=None, basis=None, account_id=APPLICANT_ID, now=NOW
    )
    assert application.check_ready("LLC", has_other_active=False) == []


def test_another_document_is_not_the_contract() -> None:
    application = _acting_for_third_party()
    application.documents.append(uploaded("other"))
    violations = application.check_ready("LLC", has_other_active=False)
    assert [v.as_dict() for v in violations] == [_contract_violation()]


def test_contract_is_listed_with_the_rest_of_the_problems() -> None:
    application = _acting_for_third_party()
    application.consents = Consents()
    fields = [v.field for v in application.check_ready("LLC", has_other_active=False)]
    assert fields == [
        "documents.beneficiary_contract",
        "consents.personal_data",
        "consents.credit_bureau",
    ]


def test_removed_contract_is_required_again() -> None:
    application = _acting_for_third_party()
    contract = uploaded("beneficiary_contract")
    application.documents.append(contract)
    application.remove_document(contract.id, NOW)
    violations = application.check_ready("LLC", has_other_active=False)
    assert [v.as_dict() for v in violations] == [_contract_violation()]


def _info_requested(
    *, fields: tuple[str, ...], documents: tuple[str, ...] = ()
) -> tuple[CreditApplication, InfoRequest]:
    """Submitted by a client acting alone, then asked for more by the bank."""
    application = ready_draft()
    application.declare_beneficiary(
        acts_for_third_party=False, beneficiary=None, basis=None, account_id=APPLICANT_ID, now=NOW
    )
    _submit(application)
    application.start_review(NOW)
    request = application.request_info(
        info_request_id=uuid4(),
        fields=fields,
        documents=documents,
        comment="Уточните данные заявки",
        due_at=None,
        now=NOW,
    )
    return application, request


def test_answer_with_a_new_third_party_needs_the_contract() -> None:
    application, request = _info_requested(fields=("beneficiary",))
    application.declare_beneficiary(
        acts_for_third_party=True,
        beneficiary=AGENT,
        basis="mandate",
        account_id=APPLICANT_ID,
        now=NOW,
    )
    with pytest.raises(ValidationError) as error:
        application.answer_info_request(request.id, Actor.client(APPLICANT_ID), NOW)
    assert error.value.details == {"violations": [_contract_violation("mandate")]}
    assert application.status is ApplicationStatus.INFO_REQUESTED

    # the section is open, so the client attaches the agreement without a separate request
    document = _upload_contract(application)
    assert document.info_request_id == request.id
    application.answer_info_request(request.id, Actor.client(APPLICANT_ID), NOW)
    assert application.status is ApplicationStatus.IN_REVIEW


def test_answer_that_the_client_acts_alone_needs_no_contract() -> None:
    application, request = _info_requested(fields=("beneficiary",))
    application.answer_info_request(request.id, Actor.client(APPLICANT_ID), NOW)
    assert application.status is ApplicationStatus.IN_REVIEW


def test_contract_from_the_draft_is_enough_for_the_answer() -> None:
    application = _acting_for_third_party("commission")
    application.documents.append(uploaded("beneficiary_contract"))
    _submit(application)
    application.start_review(NOW)
    request = application.request_info(
        info_request_id=uuid4(),
        fields=("beneficiary",),
        documents=(),
        comment="Подтвердите данные",
        due_at=None,
        now=NOW,
    )
    application.answer_info_request(request.id, Actor.client(APPLICANT_ID), NOW)
    assert application.status is ApplicationStatus.IN_REVIEW


def test_other_info_request_does_not_ask_for_the_contract() -> None:
    """An application submitted before the contract became mandatory is not stuck."""
    application, request = _info_requested(fields=("collateral",))
    application.beneficiary = _declaration()
    application.answer_info_request(request.id, Actor.client(APPLICANT_ID), NOW)
    assert application.status is ApplicationStatus.IN_REVIEW


def test_underwriter_may_ask_for_the_contract_explicitly() -> None:
    application, request = _info_requested(
        fields=("collateral",), documents=("beneficiary_contract",)
    )
    with pytest.raises(ValidationError) as error:
        application.answer_info_request(request.id, Actor.client(APPLICANT_ID), NOW)
    assert error.value.details == {"violations": [_contract_violation(None)]}
    _upload_contract(application)
    application.answer_info_request(request.id, Actor.client(APPLICANT_ID), NOW)
    assert application.status is ApplicationStatus.IN_REVIEW


def test_contract_is_not_accepted_in_an_unrelated_info_request() -> None:
    application, _ = _info_requested(fields=("collateral",))
    with pytest.raises(ValidationError) as error:
        _upload_contract(application)
    assert error.value.details == {"field": "type", "code": "unexpected_document"}
