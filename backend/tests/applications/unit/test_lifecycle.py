"""Beyond the status table: what each step stores and emits."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from src.core.domain import Money
from src.core.exceptions.exceptions import (
    ConflictError,
    InvalidStatusTransitionError,
    NotFoundError,
    ValidationError,
)
from src.modules.applications.domain.enums import ApplicationStatus, InfoRequestStatus
from src.modules.applications.domain.events import (
    ApplicationCancelled,
    ApplicationInfoProvided,
    ApplicationSigned,
    ApplicationStatusChanged,
    OfferAccepted,
    OfferDeclined,
    OfferExpired,
)
from src.modules.applications.domain.fields_schema import ProductFieldsSchema
from src.modules.applications.domain.value_objects import (
    PROCESS,
    SYSTEM,
    Actor,
    CollateralDeclaration,
    LoanRequest,
)
from tests.applications.unit.factories import (
    APPLICANT_ID,
    AUTO_FIELDS,
    NOW,
    in_status,
    offer,
    ready_draft,
    snapshot,
    summary,
    terms,
)

S = ApplicationStatus
CLIENT = Actor.client(APPLICANT_ID)


def event_types(application) -> list[str]:  # type: ignore[no-untyped-def]
    return [type(e).__name__ for e in application.pull_events()]


def test_happy_path_to_disbursement() -> None:
    application = ready_draft()
    application.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW)
    assert application.start_review(NOW, client_stage="Заявка принята") is True
    assert application.client_stage == "Заявка принята"
    application.present_offer(offer(), summary(), NOW)
    application.accept_offer(CLIENT, NOW + timedelta(hours=1))
    signature = application.sign(
        CLIENT,
        NOW + timedelta(hours=2),
        application.offer.fingerprint(),  # type: ignore[union-attr]
    )
    application.mark_disbursed(NOW + timedelta(days=1))

    assert application.status is S.DISBURSED
    assert application.closed_at == NOW + timedelta(days=1)
    assert signature.signed_by == APPLICANT_ID
    assert signature.offer_hash == application.offer.fingerprint()  # type: ignore[union-attr]
    assert [(h.from_status, h.to_status) for h in application.history] == [
        (None, "draft"),
        ("draft", "submitted"),
        ("submitted", "in_review"),
        ("in_review", "offer_ready"),
        ("offer_ready", "signing"),
        ("signing", "signed"),
        ("signed", "disbursed"),
    ]
    assert [h.actor for h in application.history[2:4]] == [PROCESS, PROCESS]


def test_status_change_carries_the_client_stage() -> None:
    application = in_status(S.SUBMITTED)
    application.start_review(NOW, client_stage="Проверяем данные о компании")
    [changed] = application.pull_events()
    assert isinstance(changed, ApplicationStatusChanged)
    assert changed.client_stage == "Проверяем данные о компании"


def test_client_stage_from_process() -> None:
    application = in_status(S.IN_REVIEW)
    assert application.set_client_stage("Оцениваем заявку", NOW) is True
    assert application.set_client_stage("Оцениваем заявку", NOW) is False
    closed = in_status(S.REJECTED)
    assert closed.set_client_stage("Оцениваем заявку", NOW) is False


# --- information request -----------------------------------------------------


def requested() -> object:
    application = in_status(S.IN_REVIEW)
    application.info_requests.clear()
    application.documents = [d for d in application.documents if d.info_request_id is None]
    request = application.request_info(
        info_request_id=uuid4(),
        fields=("collateral", "supplier_name"),
        documents=("financial_statement",),
        comment="Нужна отчётность за год",
        due_at=NOW + timedelta(days=5),
        now=NOW,
    )
    application.pull_events()
    return application, request


def test_info_request_round_trip() -> None:
    application, request = requested()  # type: ignore[misc]
    assert application.status is S.INFO_REQUESTED
    assert application.open_info_request is request

    with pytest.raises(ValidationError) as error:
        application.answer_info_request(request.id, CLIENT, NOW)
    assert error.value.details["violations"][0]["field"] == "documents.financial_statement"

    document = application.add_document(
        document_id=uuid4(),
        document_type="financial_statement",
        filename="balance.pdf",
        content_type="application/pdf",
        size_bytes=50_000,
        uploaded_by=APPLICANT_ID,
        now=NOW,
    )
    assert document.info_request_id == request.id
    application.confirm_document(document.id, 50_000, "application/pdf", NOW)
    application.answer_info_request(request.id, CLIENT, NOW + timedelta(hours=1))

    assert application.status is S.IN_REVIEW
    assert request.status is InfoRequestStatus.ANSWERED
    assert request.answered_by == APPLICANT_ID
    events = application.pull_events()
    provided = [e for e in events if isinstance(e, ApplicationInfoProvided)]
    assert provided[0].document_ids == (document.id,)


def test_only_requested_parts_are_editable_during_info_request() -> None:
    application, _ = requested()  # type: ignore[misc]
    application.change_collateral(
        CollateralDeclaration("equipment", "Станок", Money.of(800_000), "self"), NOW
    )
    with pytest.raises(ConflictError) as error:
        application.change_request(LoanRequest(Money.of(1), 12, "equipment"), NOW)
    assert error.value.details["code"] == "not_editable"

    with pytest.raises(ValidationError):  # bank did not ask for a statement
        application.add_document(
            document_id=uuid4(),
            document_type="bank_statement",
            filename="s.csv",
            content_type="text/csv",
            size_bytes=10,
            uploaded_by=APPLICANT_ID,
            now=NOW,
        )


def test_requested_product_field_is_editable() -> None:
    application, _ = requested()  # type: ignore[misc]
    application.product_terms = terms(code="AUTO", fields_schema=ProductFieldsSchema(AUTO_FIELDS))
    application.change_product_fields({"supplier_name": "ООО Авто"}, NOW)
    assert application.product_fields["supplier_name"] == "ООО Авто"
    with pytest.raises(ConflictError):  # the bank did not ask for the price
        application.change_product_fields({"price": 1}, NOW)


def test_answer_to_a_closed_request() -> None:
    application, request = requested()  # type: ignore[misc]
    application.reject(summary("REJECT"), NOW)
    assert request.status is InfoRequestStatus.EXPIRED
    with pytest.raises(InvalidStatusTransitionError):
        application.answer_info_request(request.id, CLIENT, NOW)


def test_answer_to_an_unknown_request() -> None:
    application, _ = requested()  # type: ignore[misc]
    with pytest.raises(NotFoundError):
        application.answer_info_request(uuid4(), CLIENT, NOW)


def test_request_must_ask_for_something() -> None:
    with pytest.raises(ValueError):
        in_status(S.IN_REVIEW).request_info(
            info_request_id=uuid4(), fields=(), documents=(), comment="?", due_at=None, now=NOW
        )


# --- offer -------------------------------------------------------------------


def test_offer_is_stored_with_the_client_summary() -> None:
    application = in_status(S.IN_REVIEW)
    application.offer = None
    new_offer = offer()
    application.present_offer(new_offer, summary("COUNTER_OFFER"), NOW)
    assert application.offer is new_offer
    assert application.decision_summary.outcome == "COUNTER_OFFER"  # type: ignore[union-attr]


def test_expired_offer_cannot_be_presented() -> None:
    with pytest.raises(ValueError):
        in_status(S.IN_REVIEW).present_offer(offer(expires_at=NOW), summary(), NOW)


def test_offer_accepted_before_expiry_only() -> None:
    application = in_status(S.OFFER_READY)
    with pytest.raises(ConflictError) as error:
        application.accept_offer(CLIENT, application.offer.expires_at)  # type: ignore[union-attr]
    assert error.value.details["code"] == "offer_expired"
    assert application.status is S.OFFER_READY

    application.accept_offer(CLIENT, NOW)
    assert event_types(application) == ["ApplicationStatusChanged", OfferAccepted.__name__]


def test_offer_declined() -> None:
    application = in_status(S.OFFER_READY)
    application.decline_offer(CLIENT, NOW, reason="Дорого")
    assert application.history[-1].reason == "Дорого"
    assert event_types(application)[-1] == OfferDeclined.__name__


def test_offer_expiry_is_idempotent() -> None:
    application = in_status(S.OFFER_READY)
    assert application.expire_offer(NOW) is False  # not yet
    later = NOW + timedelta(days=7)
    assert application.expire_offer(later) is True
    assert application.history[-1].actor == SYSTEM
    assert event_types(application)[-1] == OfferExpired.__name__
    assert application.expire_offer(later) is False


def test_signature_fixes_the_offer() -> None:
    application = in_status(S.SIGNING)
    offer_hash = application.offer.fingerprint()  # type: ignore[union-attr]
    signature = application.sign(CLIENT, NOW, offer_hash)
    assert signature.offer_hash == offer_hash
    assert event_types(application)[-1] == ApplicationSigned.__name__
    with pytest.raises(InvalidStatusTransitionError):  # signing twice
        application.sign(CLIENT, NOW, offer_hash)


def test_a_changed_offer_is_not_signed() -> None:
    """The client signs the offer it saw in the contract, not whatever is
    current by the time the request arrives."""
    application = in_status(S.SIGNING)
    seen = replace(application.offer, rate=Decimal("30")).fingerprint()  # type: ignore[type-var]
    with pytest.raises(ConflictError) as error:
        application.sign(CLIENT, NOW, seen)
    assert error.value.details == {"code": "offer_changed"}
    assert application.status is S.SIGNING
    assert application.signature is None


def test_offer_fingerprint_depends_on_terms() -> None:
    first = offer()
    assert first.fingerprint() == first.fingerprint()
    assert replace(first, rate=first.rate + 1).fingerprint() != first.fingerprint()


# --- cancel and process commands ---------------------------------------------


def test_cancel_closes_the_open_info_request() -> None:
    application, request = requested()  # type: ignore[misc]
    application.cancel(CLIENT, NOW, reason="Передумали")
    assert application.status is S.CANCELLED
    assert request.status is InfoRequestStatus.EXPIRED
    events = application.pull_events()
    assert isinstance(events[-1], ApplicationCancelled)
    assert events[-1].reason == "Передумали"


def test_repeated_process_commands_are_no_ops() -> None:
    reviewed = in_status(S.IN_REVIEW)
    assert reviewed.start_review(NOW) is False
    disbursed = in_status(S.DISBURSED)
    assert disbursed.mark_disbursed(NOW) is False


def test_version_check() -> None:
    application = ready_draft()
    application.check_version(1)
    with pytest.raises(ConflictError) as error:
        application.check_version(2)
    assert error.value.details == {"code": "version_conflict", "version": 1}


def test_snapshots_are_kept_after_submit() -> None:
    application = ready_draft()
    application.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW)
    for change in (
        lambda: application.change_request(LoanRequest(), NOW),
        lambda: application.change_collateral(None, NOW),
        lambda: application.change_product_fields({}, NOW),
        lambda: application.set_consents(
            personal_data=False, credit_bureau=False, account_id=APPLICANT_ID, now=NOW
        ),
    ):
        with pytest.raises(ConflictError):
            change()
    assert application.org_snapshot == snapshot()


def test_consents_keep_the_first_moment() -> None:
    application = ready_draft()
    later = NOW + timedelta(hours=3)
    application.set_consents(
        personal_data=True, credit_bureau=True, account_id=APPLICANT_ID, now=later
    )
    assert application.consents.personal_data_at == NOW
    application.set_consents(
        personal_data=True, credit_bureau=False, account_id=APPLICANT_ID, now=later
    )
    assert application.consents.credit_bureau_at is None
    assert not application.consents.complete


def test_automated_decision_consent_is_optional_and_keeps_the_first_moment() -> None:
    """ст. 16 152-ФЗ: согласие на автоматизированное решение — по желанию, без него заявку
    тоже можно подать; данное однажды хранит первый момент, снятая галочка его отзывает."""
    application = ready_draft()
    assert application.consents.complete and application.consents.automated_decision_at is None
    application.set_consents(
        personal_data=True,
        credit_bureau=True,
        account_id=APPLICANT_ID,
        now=NOW,
        automated_decision=True,
    )
    later = NOW + timedelta(hours=1)
    application.set_consents(
        personal_data=True,
        credit_bureau=True,
        account_id=APPLICANT_ID,
        now=later,
        automated_decision=True,
    )
    assert application.consents.automated_decision_at == NOW
    application.set_consents(
        personal_data=True, credit_bureau=True, account_id=APPLICANT_ID, now=later
    )
    assert application.consents.automated_decision_at is None
