from datetime import timedelta

import pytest

from src.core.exceptions.exceptions import ValidationError
from src.modules.clients.domain.rights import (
    Authority,
    MemberRole,
    OrgPermission,
    PowerOfAttorney,
    ordered,
    permissions_of,
)
from tests.clients.unit.factories import NOW, poa

P = OrgPermission
R = MemberRole
A = Authority

BASE_HEAD = {P.VIEW, P.SUBMIT_APPLICATION, P.MANAGE_MEMBERS, P.EDIT_FINANCIALS}
SIGN_POA = poa(P.SIGN)
SUBMIT_POA = poa(P.SUBMIT_APPLICATION)
FULL_POA = poa(P.SUBMIT_APPLICATION, P.SIGN)
EXPIRED_POA = poa(
    P.SIGN, issued_at=NOW.date() - timedelta(days=400), valid_until=NOW.date() - timedelta(days=1)
)


@pytest.mark.parametrize(
    "role,authority,power_of_attorney,expected",
    [
        # owner / director: everything, sign only with confirmed authority
        (R.OWNER, A.REGISTRY, None, BASE_HEAD | {P.SIGN}),
        (R.DIRECTOR, A.REGISTRY, None, BASE_HEAD | {P.SIGN}),
        (R.DIRECTOR, A.UNCONFIRMED, None, BASE_HEAD),
        (R.OWNER, A.UNCONFIRMED, None, BASE_HEAD),
        (R.DIRECTOR, A.POWER_OF_ATTORNEY, SIGN_POA, BASE_HEAD | {P.SIGN}),
        (R.DIRECTOR, A.POWER_OF_ATTORNEY, SUBMIT_POA, BASE_HEAD),
        (R.DIRECTOR, A.POWER_OF_ATTORNEY, EXPIRED_POA, BASE_HEAD),
        # accountant: no member management, sign only by a valid power of attorney
        (R.ACCOUNTANT, A.UNCONFIRMED, None, {P.VIEW, P.SUBMIT_APPLICATION, P.EDIT_FINANCIALS}),
        (R.ACCOUNTANT, A.REGISTRY, None, {P.VIEW, P.SUBMIT_APPLICATION, P.EDIT_FINANCIALS}),
        (
            R.ACCOUNTANT,
            A.POWER_OF_ATTORNEY,
            SIGN_POA,
            {P.VIEW, P.SUBMIT_APPLICATION, P.EDIT_FINANCIALS, P.SIGN},
        ),
        (
            R.ACCOUNTANT,
            A.POWER_OF_ATTORNEY,
            EXPIRED_POA,
            {P.VIEW, P.SUBMIT_APPLICATION, P.EDIT_FINANCIALS},
        ),
        # employee: view, the rest only by a power of attorney
        (R.EMPLOYEE, A.UNCONFIRMED, None, {P.VIEW}),
        (R.EMPLOYEE, A.REGISTRY, None, {P.VIEW}),
        (R.EMPLOYEE, A.POWER_OF_ATTORNEY, SUBMIT_POA, {P.VIEW, P.SUBMIT_APPLICATION}),
        (R.EMPLOYEE, A.POWER_OF_ATTORNEY, SIGN_POA, {P.VIEW, P.SIGN}),
        (R.EMPLOYEE, A.POWER_OF_ATTORNEY, FULL_POA, {P.VIEW, P.SUBMIT_APPLICATION, P.SIGN}),
        (R.EMPLOYEE, A.POWER_OF_ATTORNEY, EXPIRED_POA, {P.VIEW}),
    ],
)
def test_rights_table(
    role: MemberRole,
    authority: Authority,
    power_of_attorney: PowerOfAttorney | None,
    expected: set[OrgPermission],
) -> None:
    assert permissions_of(role, authority, power_of_attorney, NOW) == frozenset(expected)


def test_nobody_manages_members_or_financials_by_power_of_attorney() -> None:
    for role in (R.ACCOUNTANT, R.EMPLOYEE):
        granted = permissions_of(role, A.POWER_OF_ATTORNEY, FULL_POA, NOW)
        assert P.MANAGE_MEMBERS not in granted
    assert P.EDIT_FINANCIALS not in permissions_of(R.EMPLOYEE, A.POWER_OF_ATTORNEY, FULL_POA, NOW)


def test_power_of_attorney_validity_by_now() -> None:
    document = poa(P.SIGN, issued_at=NOW.date(), valid_until=NOW.date() + timedelta(days=10))
    assert document.is_valid(NOW)
    assert document.is_valid(NOW + timedelta(days=10))  # the last day still counts
    assert not document.is_valid(NOW + timedelta(days=11))
    assert document.is_expired(NOW + timedelta(days=11))
    assert not document.is_valid(NOW - timedelta(days=1))  # not issued yet
    assert not document.is_expired(NOW - timedelta(days=1))
    assert document.grants(P.SIGN, NOW) and not document.grants(P.SUBMIT_APPLICATION, NOW)


def test_expired_power_of_attorney_stops_signing() -> None:
    document = poa(P.SIGN, valid_until=NOW.date() + timedelta(days=5))
    assert P.SIGN in permissions_of(R.ACCOUNTANT, A.POWER_OF_ATTORNEY, document, NOW)
    later = NOW + timedelta(days=6)
    assert P.SIGN not in permissions_of(R.ACCOUNTANT, A.POWER_OF_ATTORNEY, document, later)


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"number": "  "}, "invalid"),
        ({"number": "x" * 65}, "invalid"),
        ({"valid_until": NOW.date() - timedelta(days=31)}, "before_issue"),
        ({"scope": frozenset()}, "empty"),
        ({"scope": frozenset({P.MANAGE_MEMBERS})}, "not_delegable"),
        ({"scope": frozenset({P.SIGN, P.EDIT_FINANCIALS})}, "not_delegable"),
    ],
)
def test_power_of_attorney_validation(kwargs: dict, code: str) -> None:
    values = {
        "number": "77 АА 1234567",
        "issued_at": NOW.date() - timedelta(days=30),
        "valid_until": NOW.date() + timedelta(days=30),
        "scope": frozenset({P.SIGN}),
        **kwargs,
    }
    with pytest.raises(ValidationError) as error:
        PowerOfAttorney(**values)
    assert error.value.details is not None and error.value.details["code"] == code


def test_ordered_follows_the_table() -> None:
    assert ordered(frozenset({P.SIGN, P.VIEW, P.EDIT_FINANCIALS})) == [
        P.VIEW,
        P.SIGN,
        P.EDIT_FINANCIALS,
    ]
