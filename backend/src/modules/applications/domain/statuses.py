"""The only allowed transitions of the business status of an application."""

from src.core.exceptions.exceptions import InvalidStatusTransitionError
from src.modules.applications.domain.enums import ApplicationStatus

S = ApplicationStatus

TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    S.DRAFT: frozenset({S.SUBMITTED, S.CANCELLED}),
    S.SUBMITTED: frozenset({S.IN_REVIEW, S.CANCELLED}),
    S.IN_REVIEW: frozenset({S.INFO_REQUESTED, S.OFFER_READY, S.REJECTED}),
    # REJECTED here: the process gives up when the client never answers.
    S.INFO_REQUESTED: frozenset({S.IN_REVIEW, S.REJECTED, S.CANCELLED}),
    S.OFFER_READY: frozenset({S.SIGNING, S.OFFER_DECLINED, S.EXPIRED, S.CANCELLED}),
    S.SIGNING: frozenset({S.SIGNED}),
    S.SIGNED: frozenset({S.DISBURSED}),
    S.DISBURSED: frozenset(),
    S.REJECTED: frozenset(),
    S.OFFER_DECLINED: frozenset(),
    S.EXPIRED: frozenset(),
    S.CANCELLED: frozenset(),
}

FINAL_STATUSES: frozenset[ApplicationStatus] = frozenset(
    status for status, targets in TRANSITIONS.items() if not targets
)
# Not final: the company may not open a second one on the same product.
ACTIVE_STATUSES: frozenset[ApplicationStatus] = frozenset(TRANSITIONS) - FINAL_STATUSES


def can_transition(source: ApplicationStatus, target: ApplicationStatus) -> bool:
    return target in TRANSITIONS[source]


def ensure_transition(source: ApplicationStatus, target: ApplicationStatus) -> None:
    if not can_transition(source, target):
        raise InvalidStatusTransitionError(
            f"Application cannot go from {source.value} to {target.value}",
            details={"from": source.value, "to": target.value},
        )
