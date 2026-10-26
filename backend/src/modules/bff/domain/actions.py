"""What the client can do with an application and what waits for them on the
dashboard. The commands themselves live in the applications module; the names
match its `available_actions`."""

from src.modules.bff.domain.enums import TodoKind

# Rights inside the company, as clients names them (OrgPermission): the domain
# does not import the facade of clients.
SUBMIT = "submit_application"
SIGN = "sign"

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


# projector's action_required -> (todo kind, title, right inside the company it needs)
_TODO: dict[str, tuple[TodoKind, str, str]] = {
    "info": ("info_requested", "Банку нужны данные по заявке {number}", SUBMIT),
    "offer": ("offer_ready", "Готово решение по заявке {number}", SUBMIT),
    "sign": ("signing", "Подпишите договор по заявке {number}", SIGN),
}


def todo_for(
    action_required: str, number: str, permissions: frozenset[str] | None = None
) -> tuple[TodoKind, str] | None:
    """With `permissions` — only what the member may do: without a power of attorney
    an employee is not asked to sign."""
    if action_required not in _TODO:
        return None
    kind, title, needs = _TODO[action_required]
    if permissions is not None and needs not in permissions:
        return None
    return kind, title.format(number=number)


# Until the decision the bank can still check the head's own credit history, if
# the head gives their consent; the item is shown to the head only.
CONSENT_PENDING_STATUSES: frozenset[str] = frozenset({"submitted", "in_review", "info_requested"})


def consent_todo(number: str) -> tuple[TodoKind, str]:
    return (
        "consent_required",
        f"Дайте согласие на проверку вашей кредитной истории по заявке {number}",
    )
