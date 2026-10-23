"""What the client may do with an application: the buttons by status and rights."""

from src.modules.applications.domain.actions import SIGN, SUBMIT, available_actions
from src.modules.applications.domain.enums import ApplicationStatus
from src.modules.clients.facade import OrgPermission

S = ApplicationStatus


def test_rights_are_named_as_clients_names_them() -> None:
    assert SUBMIT == OrgPermission.SUBMIT_APPLICATION.value
    assert SIGN == OrgPermission.SIGN.value


def test_actions_need_the_right_inside_the_company() -> None:
    everything = frozenset(OrgPermission)
    accountant = frozenset({OrgPermission.VIEW.value, OrgPermission.SUBMIT_APPLICATION.value})
    assert available_actions(S.OFFER_READY, everything) == [
        "accept_offer",
        "decline_offer",
        "cancel",
    ]
    assert available_actions(S.SIGNING, everything) == ["sign"]
    assert available_actions(S.SIGNING, accountant) == []
    assert available_actions(S.IN_REVIEW, everything) == []
