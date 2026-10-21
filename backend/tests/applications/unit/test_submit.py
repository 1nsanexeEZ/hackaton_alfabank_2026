"""Submission: one test per condition of invariant 3 (docs/design/applications.md)."""

from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest

from src.applications.domain.application import CreditApplication
from src.applications.domain.entities import DocumentStatus
from src.applications.domain.events import ApplicationStatusChanged, ApplicationSubmitted
from src.applications.domain.fields_schema import ProductFieldsSchema
from src.applications.domain.statuses import ApplicationStatus
from src.applications.domain.value_objects import (
    Actor,
    CollateralDeclaration,
    Consents,
    DocumentRequirement,
    LoanRequest,
)
from src.core.domain import Money
from src.core.exceptions.exceptions import InvalidStatusTransitionError, ValidationError
from tests.applications.unit.factories import (
    APPLICANT_ID,
    AUTO_FIELDS,
    NOW,
    ORG_ID,
    in_status,
    ready_draft,
    snapshot,
    terms,
    uploaded,
)

CLIENT = Actor.client(APPLICANT_ID)


def violations_of(application: CreditApplication, **kwargs: Any) -> list[dict[str, Any]]:
    with pytest.raises(ValidationError) as error:
        application.submit(
            kwargs.get("snapshot", snapshot()),
            actor=CLIENT,
            has_other_active=kwargs.get("has_other_active", False),
            now=NOW,
        )
    assert application.status is ApplicationStatus.DRAFT
    assert application.pull_events() == []
    assert error.value.details is not None
    return error.value.details["violations"]


def fields(violations: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(v["code"], v["field"]) for v in violations]


def test_ready_draft_is_submitted() -> None:
    application = ready_draft()
    application.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW)

    assert application.status is ApplicationStatus.SUBMITTED
    assert application.org_snapshot == snapshot()
    assert application.submitted_at == NOW
    events = application.pull_events()
    assert [type(e) for e in events] == [ApplicationStatusChanged, ApplicationSubmitted]
    submitted = events[1]
    assert isinstance(submitted, ApplicationSubmitted)
    assert submitted.amount == Money.of(3_000_000)
    assert (submitted.product_code, submitted.term_months, submitted.purpose) == (
        "UNSECURED",
        24,
        "working_capital",
    )
    assert application.history[-1].actor == CLIENT


@pytest.mark.parametrize("missing", ["amount", "term_months", "purpose"])
def test_request_must_be_complete(missing: str) -> None:
    application = ready_draft()
    application.request = replace(application.request, **{missing: None})
    assert fields(violations_of(application)) == [("missing", f"request.{missing}")]


@pytest.mark.parametrize("amount", [99_999, 5_000_001])
def test_amount_within_product_terms(amount: int) -> None:
    application = ready_draft()
    application.request = replace(application.request, amount=Money.of(amount))
    [violation] = violations_of(application)
    assert violation == {
        "code": "out_of_range",
        "field": "request.amount",
        "min": "100000.00",
        "max": "5000000.00",
    }


def test_amount_bounds_are_inclusive() -> None:
    for amount in (100_000, 5_000_000):
        application = ready_draft()
        application.request = replace(application.request, amount=Money.of(amount))
        application.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW)


@pytest.mark.parametrize("term", [2, 37])
def test_term_within_product_terms(term: int) -> None:
    application = ready_draft()
    application.request = replace(application.request, term_months=term)
    assert fields(violations_of(application)) == [("out_of_range", "request.term_months")]


def test_product_fields_follow_the_schema() -> None:
    application = ready_draft(terms(code="AUTO", fields_schema=ProductFieldsSchema(AUTO_FIELDS)))
    application.product_fields = {"vehicle_type": "plane"}
    assert sorted(fields(violations_of(application))) == [
        ("not_allowed", "product_fields.vehicle_type"),
        ("required", "product_fields.price"),
    ]

    application.product_fields = {"vehicle_type": "truck", "price": 4_500_000}
    application.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW)


def test_collateral_required_by_product() -> None:
    application = ready_draft(terms(code="SECURED", collateral_required=True))
    assert fields(violations_of(application)) == [("missing", "collateral")]

    application.collateral = CollateralDeclaration(
        "real_estate", "Офис 120 м²", Money.of(9_000_000), "self"
    )
    application.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW)


def test_collateral_required_from_amount() -> None:
    product = terms(collateral_required_from=Money.of(3_000_000))
    below = ready_draft(product)
    below.request = replace(below.request, amount=Money.of(2_999_999))
    below.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW)

    at_threshold = ready_draft(product)
    assert fields(violations_of(at_threshold)) == [("missing", "collateral")]


def test_required_document_must_be_uploaded() -> None:
    application = ready_draft()
    application.documents.clear()
    [violation] = violations_of(application)
    assert violation == {
        "code": "missing",
        "field": "documents.bank_statement",
        "type": "bank_statement",
    }


def test_announced_but_not_uploaded_document_does_not_count() -> None:
    application = ready_draft()
    application.documents[0].status = DocumentStatus.PENDING_UPLOAD
    assert fields(violations_of(application)) == [("missing", "documents.bank_statement")]


def test_document_required_from_amount() -> None:
    product = terms(
        required_documents=(
            DocumentRequirement("bank_statement", "Выписка"),
            DocumentRequirement("financial_statement", "Отчётность", Money.of(3_000_000)),
        )
    )
    small = ready_draft(product)
    small.request = replace(small.request, amount=Money.of(1_000_000))
    small.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW)

    large = ready_draft(product)
    assert fields(violations_of(large)) == [("missing", "documents.financial_statement")]
    large.documents.append(uploaded("financial_statement"))
    large.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW)


def test_document_required_for_legal_form() -> None:
    product = terms(
        required_documents=(
            DocumentRequirement("bank_statement", "Выписка"),
            DocumentRequirement("charter", "Устав", legal_forms=frozenset({"LLC", "JSC"})),
        )
    )
    entrepreneur = ready_draft(product)
    entrepreneur.submit(snapshot(legal_form="IE"), actor=CLIENT, has_other_active=False, now=NOW)

    company = ready_draft(product)
    assert fields(violations_of(company, snapshot=snapshot(legal_form="LLC"))) == [
        ("missing", "documents.charter")
    ]


@pytest.mark.parametrize(
    "consents,missing",
    [
        (Consents(None, NOW, APPLICANT_ID), "consents.personal_data"),
        (Consents(NOW, None, APPLICANT_ID), "consents.credit_bureau"),
    ],
    ids=["personal-data", "credit-bureau"],
)
def test_both_consents_are_required(consents: Consents, missing: str) -> None:
    application = ready_draft()
    application.consents = consents
    assert fields(violations_of(application)) == [("missing", missing)]


def test_one_active_application_per_product() -> None:
    application = ready_draft()
    assert fields(violations_of(application, has_other_active=True)) == [
        ("duplicate_active", "product_code")
    ]


def test_all_problems_are_reported_at_once() -> None:
    application = ready_draft(terms(collateral_required=True))
    application.request = LoanRequest()
    application.consents = Consents()
    application.documents.clear()
    assert len(violations_of(application, has_other_active=True)) == 8


def test_only_a_draft_is_submitted() -> None:
    application = in_status(ApplicationStatus.SUBMITTED)
    with pytest.raises(InvalidStatusTransitionError):
        application.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW)


def test_snapshot_must_belong_to_the_company() -> None:
    with pytest.raises(ValueError, match="another organization"):
        ready_draft().submit(
            snapshot(organization_id=uuid4()), actor=CLIENT, has_other_active=False, now=NOW
        )


def test_check_ready_feeds_the_draft_hint() -> None:
    application = ready_draft()
    assert application.check_ready("LLC", has_other_active=False) == []
    application.request = LoanRequest(purpose="equipment")
    assert [v.field for v in application.check_ready("LLC", False)] == [
        "request.amount",
        "request.term_months",
    ]
    assert application.organization_id == ORG_ID
