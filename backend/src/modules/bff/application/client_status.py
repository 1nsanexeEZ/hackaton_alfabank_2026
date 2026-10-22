"""Application status in the frontend's terms
(`frontend/src/entities/application/model/status.ts`).

The backend keeps fewer statuses than the screen shows: `in_review` splits by
the process stage, `offer_ready` by the kind of the offer, and a signed and a
disbursed loan read the same to the client."""

from decimal import Decimal
from typing import Literal

ClientStatus = Literal[
    "draft",
    "submitted",
    "checking",
    "scoring",
    "info_requested",
    "approved",
    "counter_offer",
    "rejected",
    "signing",
    "issued",
    "cancelled",
    "declined",
    "expired",
]

_BY_STATUS: dict[str, ClientStatus] = {
    "draft": "draft",
    "submitted": "submitted",
    "info_requested": "info_requested",
    "signing": "signing",
    "signed": "issued",
    "disbursed": "issued",
    "rejected": "rejected",
    "offer_declined": "declined",
    "expired": "expired",
    "cancelled": "cancelled",
}

# Process stages (client_stage of the workflow nodes) where the bank already
# weighs the risk: «Оцениваем залог», «Оцениваем заявку», «Подбираем условия»,
# «Заявка у специалиста». The earlier ones still check the data.
_SCORING_STAGE_MARKERS = ("оцени", "подбира", "специалист")


def review_status(client_stage: str | None) -> ClientStatus:
    stage = (client_stage or "").lower()
    return "scoring" if any(marker in stage for marker in _SCORING_STAGE_MARKERS) else "checking"


def client_status(status: str, client_stage: str | None, offer_kind: str | None) -> ClientStatus:
    if status == "in_review":
        return review_status(client_stage)
    if status == "offer_ready":
        return "counter_offer" if offer_kind == "counter" else "approved"
    # A status added later shows as "in progress" until it is mapped here.
    return _BY_STATUS.get(status, "checking")


def offer_kind_of_row(amount: Decimal | None, offer_amount: Decimal | None) -> str | None:
    """A projector row carries the offered sum, not the kind of the offer: a
    counter offer is the one that changed the requested amount."""
    if offer_amount is None:
        return None
    return "counter" if amount is not None and offer_amount != amount else "as_requested"
