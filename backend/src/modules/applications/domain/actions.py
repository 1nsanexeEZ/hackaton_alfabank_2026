"""What the current user can do with an application now: the frontend shows
only these buttons."""

from src.modules.applications.domain.enums import ApplicationStatus

S = ApplicationStatus

# Rights inside the company, as clients names them (OrgPermission): the domain
# does not import the facade of clients.
SUBMIT = "submit_application"
SIGN = "sign"

# status -> (action, right inside the company it needs)
_ACTIONS: dict[ApplicationStatus, list[tuple[str, str]]] = {
    S.DRAFT: [
        ("edit", SUBMIT),
        ("upload_document", SUBMIT),
        ("submit", SUBMIT),
        ("cancel", SUBMIT),
    ],
    S.SUBMITTED: [("cancel", SUBMIT)],
    S.INFO_REQUESTED: [
        ("upload_document", SUBMIT),
        ("answer_info_request", SUBMIT),
        ("cancel", SUBMIT),
    ],
    S.OFFER_READY: [("accept_offer", SUBMIT), ("decline_offer", SUBMIT), ("cancel", SUBMIT)],
    S.SIGNING: [("sign", SIGN)],
}


def available_actions(status: ApplicationStatus, permissions: frozenset[str]) -> list[str]:
    return [action for action, needs in _ACTIONS.get(status, []) if needs in permissions]
