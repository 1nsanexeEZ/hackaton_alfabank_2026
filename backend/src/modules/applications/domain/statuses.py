"""Business status of an application and the only allowed transitions."""

from enum import StrEnum

from src.core.exceptions.exceptions import InvalidStatusTransitionError


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    INFO_REQUESTED = "info_requested"
    OFFER_READY = "offer_ready"
    SIGNING = "signing"
    SIGNED = "signed"
    DISBURSED = "disbursed"
    REJECTED = "rejected"
    OFFER_DECLINED = "offer_declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


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
