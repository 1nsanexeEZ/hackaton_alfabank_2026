"""What the client can do with an application and what waits for them on the
dashboard. The commands themselves live in the applications module; the names
match its `available_actions`."""

from typing import Literal

from src.modules.clients.facade import OrgPermission

SUBMIT = OrgPermission.SUBMIT_APPLICATION.value
SIGN = OrgPermission.SIGN.value

# status -> (action, right inside the company it needs)
_ACTIONS: dict[str, list[tuple[str, str]]] = {
    "draft": [
        ("edit", SUBMIT),
        ("upload_document", SUBMIT),
        ("submit", SUBMIT),
        ("cancel", SUBMIT),
    ],
    "submitted": [("cancel", SUBMIT)],
    "info_requested": [
        ("upload_document", SUBMIT),
        ("answer_info_request", SUBMIT),
        ("cancel", SUBMIT),
    ],
    "offer_ready": [("accept_offer", SUBMIT), ("decline_offer", SUBMIT), ("cancel", SUBMIT)],
    "signing": [("sign", SIGN)],
}


def available_actions(status: str, permissions: frozenset[str]) -> list[str]:
    return [action for action, needs in _ACTIONS.get(status, []) if needs in permissions]


TodoKind = Literal["info_requested", "offer_ready", "signing", "consent_required"]

# projector's action_required -> (todo kind, title)
_TODO: dict[str, tuple[TodoKind, str]] = {
    "info": ("info_requested", "Банку нужны данные по заявке {number}"),
    "offer": ("offer_ready", "Готово решение по заявке {number}"),
    "sign": ("signing", "Подпишите договор по заявке {number}"),
}


def todo_for(action_required: str, number: str) -> tuple[TodoKind, str] | None:
    if action_required not in _TODO:
        return None
    kind, title = _TODO[action_required]
    return kind, title.format(number=number)


# Until the decision the bank can still check the head's own credit history, if
# the head gives their consent; the item is shown to the head only.
CONSENT_PENDING_STATUSES: frozenset[str] = frozenset({"submitted", "in_review", "info_requested"})


def consent_todo(number: str) -> tuple[TodoKind, str]:
    return (
        "consent_required",
        f"Дайте согласие на проверку вашей кредитной истории по заявке {number}",
    )
