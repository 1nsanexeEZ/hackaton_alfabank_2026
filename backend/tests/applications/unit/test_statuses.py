"""Every pair of statuses: the table itself and the aggregate methods behind it."""

from collections.abc import Callable
from datetime import timedelta
from itertools import product

import pytest

from src.core.exceptions.exceptions import InvalidStatusTransitionError
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.statuses import (
    ACTIVE_STATUSES,
    FINAL_STATUSES,
    TRANSITIONS,
    ApplicationStatus,
    can_transition,
    ensure_transition,
)
from src.modules.applications.domain.value_objects import Actor
from tests.applications.unit.factories import (
    APPLICANT_ID,
    INFO_REQUEST_ID,
    NOW,
    in_status,
    offer,
    snapshot,
    summary,
)

S = ApplicationStatus
CLIENT = Actor.client(APPLICANT_ID)

# The spec from docs/design/applications.md, written out independently of the code.
ALLOWED = {
    (S.DRAFT, S.SUBMITTED),
    (S.DRAFT, S.CANCELLED),
    (S.SUBMITTED, S.IN_REVIEW),
    (S.SUBMITTED, S.CANCELLED),
    (S.IN_REVIEW, S.INFO_REQUESTED),
    (S.IN_REVIEW, S.OFFER_READY),
    (S.IN_REVIEW, S.REJECTED),
    (S.INFO_REQUESTED, S.IN_REVIEW),
    (S.INFO_REQUESTED, S.REJECTED),
    (S.INFO_REQUESTED, S.CANCELLED),
    (S.OFFER_READY, S.SIGNING),
    (S.OFFER_READY, S.OFFER_DECLINED),
    (S.OFFER_READY, S.EXPIRED),
    (S.OFFER_READY, S.CANCELLED),
    (S.SIGNING, S.SIGNED),
    (S.SIGNED, S.DISBURSED),
}
PAIRS = list(product(S, S))


def pair_id(pair: tuple[ApplicationStatus, ApplicationStatus]) -> str:
    return f"{pair[0].value}->{pair[1].value}"


@pytest.mark.parametrize("pair", PAIRS, ids=[pair_id(p) for p in PAIRS])
def test_transition_table(pair: tuple[ApplicationStatus, ApplicationStatus]) -> None:
    source, target = pair
    assert can_transition(source, target) == (pair in ALLOWED)
    if pair in ALLOWED:
        ensure_transition(source, target)
    else:
        with pytest.raises(InvalidStatusTransitionError) as error:
            ensure_transition(source, target)
        assert error.value.details == {"from": source.value, "to": target.value}


def test_final_and_active_statuses() -> None:
    assert FINAL_STATUSES == {S.DISBURSED, S.REJECTED, S.OFFER_DECLINED, S.EXPIRED, S.CANCELLED}
    assert ACTIVE_STATUSES == set(S) - FINAL_STATUSES
    assert all(not TRANSITIONS[status] for status in FINAL_STATUSES)
    # nothing ever goes back to a draft
    assert all(S.DRAFT not in targets for targets in TRANSITIONS.values())


def action(
    source: ApplicationStatus, target: ApplicationStatus
) -> Callable[[CreditApplication], object]:
    """The aggregate method that leads to `target`."""
    actions: dict[ApplicationStatus, Callable[[CreditApplication], object]] = {
        S.SUBMITTED: lambda a: a.submit(snapshot(), actor=CLIENT, has_other_active=False, now=NOW),
        S.IN_REVIEW: (
            (lambda a: a.answer_info_request(INFO_REQUEST_ID, CLIENT, NOW))
            if source is S.INFO_REQUESTED
            else (lambda a: a.start_review(NOW))
        ),
        S.INFO_REQUESTED: lambda a: a.request_info(
            info_request_id=INFO_REQUEST_ID,
            fields=(),
            documents=("financial_statement",),
            comment="Нужна отчётность",
            due_at=None,
            now=NOW,
        ),
        S.OFFER_READY: lambda a: a.present_offer(offer(), summary(), NOW),
        S.REJECTED: lambda a: a.reject(summary("REJECT"), NOW),
        S.SIGNING: lambda a: a.accept_offer(CLIENT, NOW),
        S.SIGNED: lambda a: a.sign(CLIENT, NOW),
        S.DISBURSED: lambda a: a.mark_disbursed(NOW),
        S.OFFER_DECLINED: lambda a: a.decline_offer(CLIENT, NOW),
        S.CANCELLED: lambda a: a.cancel(CLIENT, NOW),
    }
    return actions[target]


# Repeated commands of the process are acknowledged without changes.
IDEMPOTENT = {(S.IN_REVIEW, S.IN_REVIEW), (S.DISBURSED, S.DISBURSED)}
METHOD_PAIRS = [p for p in PAIRS if p[1] not in (S.DRAFT, S.EXPIRED)]


@pytest.mark.parametrize("pair", METHOD_PAIRS, ids=[pair_id(p) for p in METHOD_PAIRS])
def test_aggregate_follows_the_table(pair: tuple[ApplicationStatus, ApplicationStatus]) -> None:
    source, target = pair
    application = in_status(source)
    history_before = len(application.history)
    run = action(source, target)

    if pair in ALLOWED:
        run(application)
        assert application.status is target
        assert application.history[-1].from_status == source.value
        assert application.history[-1].to_status == target.value
        changed = [
            e for e in application.pull_events() if type(e).__name__ == "ApplicationStatusChanged"
        ]
        assert [(e.from_status, e.to_status) for e in changed] == [(source.value, target.value)]
        assert (application.closed_at is not None) == (target in FINAL_STATUSES)
    elif pair in IDEMPOTENT:
        assert run(application) is False
        assert application.status is source and application.pull_events() == []
    else:
        with pytest.raises(InvalidStatusTransitionError):
            run(application)
        assert application.status is source
        assert len(application.history) == history_before
        assert application.pull_events() == []


@pytest.mark.parametrize("source", list(S), ids=[s.value for s in S])
def test_expire_offer_only_from_offer_ready(source: ApplicationStatus) -> None:
    application = in_status(source)
    expired = application.expire_offer(NOW + timedelta(days=8))
    assert expired == (source is S.OFFER_READY)
    assert application.status is (S.EXPIRED if source is S.OFFER_READY else source)


def test_facade_contract_uses_the_same_statuses() -> None:
    from typing import get_args

    from src.modules.applications import facade

    assert set(get_args(facade.ApplicationStatus)) == {s.value for s in S}
    assert facade.ACTIVE_STATUSES == {s.value for s in ACTIVE_STATUSES}
