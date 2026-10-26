from datetime import date, timedelta
from uuid import uuid4

import pytest

from src.core.exceptions.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.modules.clients.domain.enums import Authority, MemberRole, OrgPermission, TaxRegime
from src.modules.clients.domain.events import (
    MemberAdded,
    MemberRemoved,
    MemberRoleChanged,
    OrganizationVerificationMismatch,
    OrganizationVerified,
)
from src.modules.clients.domain.member import Actor
from src.modules.clients.domain.organization import months_between
from src.modules.clients.domain.value_objects import (
    Discrepancy,
    PersonName,
    Requisites,
    VerificationResult,
)
from tests.clients.unit.factories import (
    BANK,
    NOW,
    add,
    head_of,
    organization,
    poa,
    stranger_name,
    with_head,
)

P = OrgPermission
R = MemberRole


def details_code(error: pytest.ExceptionInfo) -> str:
    return error.value.details["code"]


# --- registration ------------------------------------------------------------


def test_registration_date_cannot_be_in_the_future() -> None:
    with pytest.raises(ValidationError) as error:
        organization(registered_at=NOW.date() + timedelta(days=1))
    assert details_code(error) == "in_future"


def test_patent_is_for_entrepreneurs_only() -> None:
    assert organization("ivanov", tax_regime=TaxRegime.PATENT).tax_regime is TaxRegime.PATENT
    with pytest.raises(ValidationError) as error:
        organization("romashka", tax_regime=TaxRegime.PATENT)
    assert error.value.details == {"field": "tax_regime", "code": "not_allowed"}


@pytest.mark.parametrize("kwargs", [{"name": " "}, {"employees_count": -1}])
def test_registration_validation(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        organization(**kwargs)


def test_requisites_cannot_be_replaced() -> None:
    org = organization("romashka")
    other = organization("vector").requisites
    with pytest.raises(AttributeError):
        org.requisites = other  # type: ignore[misc]
    assert org.requisites.inn.value == "7701158817"


def test_business_age_in_full_months() -> None:
    org = organization(registered_at=date(2020, 10, 21))
    assert org.business_age_months(NOW) == 72
    assert organization(registered_at=date(2020, 10, 22)).business_age_months(NOW) == 71
    assert months_between(date(2026, 1, 31), date(2026, 2, 28)) == 0
    assert months_between(date(2026, 1, 31), date(2026, 3, 1)) == 1
    assert months_between(date(2026, 5, 1), date(2026, 4, 1)) == 0


# --- adding members and authority --------------------------------------------


def test_head_matching_the_registry_gets_authority_by_registry() -> None:
    org, head_id = with_head("romashka")
    member = org.member(head_id)
    assert member.authority is Authority.REGISTRY
    assert org.can(head_id, P.SIGN, NOW)


def test_director_not_in_the_registry_stays_unconfirmed() -> None:
    """S-3: Petrov says he is the director of Vector, the registry says Sidorov."""
    org = organization("vector")
    petrov = uuid4()
    member = org.add_member(
        BANK, petrov, R.DIRECTOR, NOW, person=PersonName("Петров", "Пётр", "Петрович")
    )
    assert member.authority is Authority.UNCONFIRMED
    assert org.can(petrov, P.MANAGE_MEMBERS, NOW)
    assert org.can(petrov, P.SUBMIT_APPLICATION, NOW)
    assert not org.can(petrov, P.SIGN, NOW)


def test_accountant_never_gets_registry_authority() -> None:
    org, _ = with_head("romashka")
    accountant = uuid4()
    member = org.add_member(BANK, accountant, R.ACCOUNTANT, NOW, person=head_of("romashka"))
    assert member.authority is Authority.UNCONFIRMED


def test_first_member_must_manage_members() -> None:
    org = organization("romashka")
    with pytest.raises(ValidationError) as error:
        org.add_member(BANK, uuid4(), R.ACCOUNTANT, NOW, person=stranger_name())
    assert details_code(error) == "manager_required"
    assert org.members == ()


def test_account_is_a_member_once() -> None:
    org, head_id = with_head("romashka")
    with pytest.raises(ConflictError) as error:
        org.add_member(BANK, head_id, R.EMPLOYEE, NOW)
    assert details_code(error) == "already_member"


def test_only_a_manager_adds_members() -> None:
    org, head_id = with_head("romashka")
    accountant = add(org, R.ACCOUNTANT)

    new_id = uuid4()
    with pytest.raises(PermissionDeniedError) as error:
        org.add_member(Actor.member(accountant), new_id, R.EMPLOYEE, NOW)
    assert error.value.details == {
        "code": "org_permission_required",
        "permission": "manage_members",
    }
    with pytest.raises(NotFoundError):
        org.add_member(Actor.member(uuid4()), new_id, R.EMPLOYEE, NOW)

    member = org.add_member(Actor.member(head_id), new_id, R.EMPLOYEE, NOW)
    assert member.added_by == head_id and member.added_at == NOW


def test_member_events() -> None:
    org, head_id = with_head("romashka")
    actor = Actor.member(head_id)
    employee = uuid4()
    org.add_member(actor, employee, R.EMPLOYEE, NOW)
    org.change_role(actor, employee, R.ACCOUNTANT, NOW)
    org.change_role(actor, employee, R.ACCOUNTANT, NOW)  # same role: nothing happens
    org.remove_member(actor, employee, NOW)

    events = org.pull_events()
    assert [type(e) for e in events] == [MemberAdded, MemberRoleChanged, MemberRemoved]
    assert events[0] == MemberAdded(
        occurred_at=NOW, organization_id=org.id, account_id=employee, role="employee"
    )
    assert isinstance(events[1], MemberRoleChanged)
    assert (events[1].role, events[1].previous_role) == ("accountant", "employee")
    assert org.pull_events() == []
    assert not org.is_member(employee)


# --- the last manager --------------------------------------------------------


def test_last_manager_cannot_be_removed() -> None:
    org, head_id = with_head("romashka")
    add(org, R.ACCOUNTANT)
    with pytest.raises(ConflictError) as error:
        org.remove_member(Actor.member(head_id), head_id, NOW)
    assert details_code(error) == "last_manager"
    assert org.is_member(head_id)


def test_last_manager_cannot_be_demoted() -> None:
    org, head_id = with_head("romashka")
    with pytest.raises(ConflictError) as error:
        org.change_role(BANK, head_id, R.ACCOUNTANT, NOW)
    assert details_code(error) == "last_manager"
    assert org.member(head_id).role is R.DIRECTOR
    assert org.pull_events() == []


def test_a_manager_may_leave_when_another_one_stays() -> None:
    org, head_id = with_head("romashka")
    owner = add(org, R.OWNER)
    org.remove_member(Actor.member(head_id), head_id, NOW)
    assert org.members_with(P.MANAGE_MEMBERS, NOW) == [owner]


def test_unknown_member() -> None:
    org, head_id = with_head("romashka")
    with pytest.raises(NotFoundError):
        org.remove_member(Actor.member(head_id), uuid4(), NOW)
    with pytest.raises(NotFoundError):
        org.change_role(Actor.member(head_id), uuid4(), R.EMPLOYEE, NOW)


def test_role_change_keeps_authority() -> None:
    org, head_id = with_head("romashka")
    accountant = add(org, R.ACCOUNTANT)
    member = org.change_role(Actor.member(head_id), accountant, R.DIRECTOR, NOW)
    # A promoted director is not confirmed by the registry: no signing.
    assert member.authority is Authority.UNCONFIRMED
    assert org.can(accountant, P.MANAGE_MEMBERS, NOW)
    assert not org.can(accountant, P.SIGN, NOW)


# --- entrepreneur ------------------------------------------------------------


def test_entrepreneur_owner_is_the_entrepreneur() -> None:
    org = organization("ivanov")
    with pytest.raises(ValidationError) as error:
        org.add_member(BANK, uuid4(), R.OWNER, NOW, person=stranger_name())
    assert details_code(error) == "owner_must_be_entrepreneur"

    owner = uuid4()
    member = org.add_member(BANK, owner, R.OWNER, NOW, person=head_of("ivanov"))
    assert member.authority is Authority.REGISTRY
    assert org.can(owner, P.SIGN, NOW)


def test_entrepreneur_has_exactly_one_owner() -> None:
    org, owner = with_head("ivanov")
    with pytest.raises(ConflictError) as error:
        org.add_member(BANK, uuid4(), R.OWNER, NOW, person=head_of("ivanov"))
    assert details_code(error) == "owner_exists"

    accountant = add(org, R.ACCOUNTANT)
    for account_id, role in ((owner, R.ACCOUNTANT), (accountant, R.OWNER)):
        with pytest.raises(ConflictError) as error:
            org.change_role(Actor.member(owner), account_id, role, NOW)
        assert details_code(error) == "entrepreneur_owner_fixed"
    with pytest.raises(ConflictError):
        org.remove_member(Actor.member(owner), owner, NOW)


def test_entrepreneur_has_no_director() -> None:
    org, owner = with_head("ivanov")
    with pytest.raises(ValidationError):
        org.add_member(Actor.member(owner), uuid4(), R.DIRECTOR, NOW)
    employee = add(org, R.EMPLOYEE)
    with pytest.raises(ValidationError):
        org.change_role(Actor.member(owner), employee, R.DIRECTOR, NOW)


@pytest.mark.parametrize("code", ["romashka", "vector"])
def test_legal_entity_may_have_several_owners_and_a_director(code: str) -> None:
    org, _ = with_head(code)
    add(org, R.OWNER)
    add(org, R.OWNER)
    assert len(org.members_with(P.MANAGE_MEMBERS, NOW)) == 3


def test_joint_stock_company_works_like_an_llc() -> None:
    company = organization("romashka").requisites
    requisites = Requisites(company.inn, company.ogrn, company.legal_form.JSC, company.kpp)
    org = organization("romashka", requisites=requisites)
    director = uuid4()
    org.add_member(BANK, director, R.DIRECTOR, NOW, person=head_of("romashka"))
    assert org.can(director, P.SIGN, NOW)


# --- rights checks -----------------------------------------------------------


def test_ensure_can_hides_the_company_from_strangers() -> None:
    org, _ = with_head("romashka")
    with pytest.raises(NotFoundError):
        org.ensure_can(uuid4(), P.VIEW, NOW)
    assert org.permissions_of(uuid4(), NOW) == frozenset()


def test_accountant_submits_but_does_not_sign() -> None:
    """S-8 in the domain: the accountant prepares, the director signs."""
    org, head_id = with_head("romashka")
    accountant = add(org, R.ACCOUNTANT)
    org.ensure_can(accountant, P.SUBMIT_APPLICATION, NOW)
    org.ensure_can(accountant, P.EDIT_FINANCIALS, NOW)
    with pytest.raises(PermissionDeniedError):
        org.ensure_can(accountant, P.SIGN, NOW)
    with pytest.raises(PermissionDeniedError):
        org.ensure_can(accountant, P.MANAGE_MEMBERS, NOW)
    org.ensure_can(head_id, P.SIGN, NOW)
    assert org.members_with(P.SIGN, NOW) == [head_id]
    assert set(org.members_with(None, NOW)) == {head_id, accountant}


def test_registry_status_does_not_block_submission() -> None:
    org, head_id = with_head("zakat")
    assert org.registry_status.value == "liquidating"
    org.ensure_can(head_id, P.SUBMIT_APPLICATION, NOW)


# --- power of attorney -------------------------------------------------------


def test_power_of_attorney_lets_the_accountant_sign_until_it_expires() -> None:
    org, head_id = with_head("romashka")
    accountant = add(org, R.ACCOUNTANT)
    document = poa(P.SIGN, valid_until=NOW.date() + timedelta(days=30))

    member = org.grant_power_of_attorney(Actor.member(head_id), accountant, document, NOW)

    assert member.authority is Authority.POWER_OF_ATTORNEY
    assert org.can(accountant, P.SIGN, NOW)
    assert not org.can(accountant, P.SIGN, NOW + timedelta(days=31))
    assert org.members_with(P.SIGN, NOW + timedelta(days=31)) == [head_id]


def test_employee_submits_by_power_of_attorney() -> None:
    org, head_id = with_head("romashka")
    employee = uuid4()
    org.add_member(
        Actor.member(head_id),
        employee,
        R.EMPLOYEE,
        NOW,
        power_of_attorney=poa(P.SUBMIT_APPLICATION),
    )
    assert org.member(employee).authority is Authority.POWER_OF_ATTORNEY
    assert org.can(employee, P.SUBMIT_APPLICATION, NOW)
    assert not org.can(employee, P.SIGN, NOW)


def test_unconfirmed_director_cannot_issue_power_of_attorney() -> None:
    org = organization("vector")
    petrov = uuid4()
    org.add_member(BANK, petrov, R.DIRECTOR, NOW, person=PersonName("Петров", "Пётр"))
    accountant = add(org, R.ACCOUNTANT)
    for target in (accountant, petrov):
        with pytest.raises(PermissionDeniedError) as error:
            org.grant_power_of_attorney(Actor.member(petrov), target, poa(P.SIGN), NOW)
        assert details_code(error) == "cannot_issue_power_of_attorney"
    with pytest.raises(PermissionDeniedError):
        org.add_member(
            Actor.member(petrov), uuid4(), R.EMPLOYEE, NOW, power_of_attorney=poa(P.SIGN)
        )
    assert not org.can(petrov, P.SIGN, NOW)


def test_accountant_cannot_issue_power_of_attorney() -> None:
    org, _ = with_head("romashka")
    accountant = add(org, R.ACCOUNTANT)
    employee = add(org, R.EMPLOYEE)
    with pytest.raises(PermissionDeniedError):
        org.grant_power_of_attorney(Actor.member(accountant), employee, poa(P.SIGN), NOW)
    with pytest.raises(NotFoundError):
        org.grant_power_of_attorney(Actor.member(uuid4()), employee, poa(P.SIGN), NOW)


def test_power_of_attorney_rules() -> None:
    org, head_id = with_head("romashka")
    accountant = add(org, R.ACCOUNTANT)
    with pytest.raises(ValidationError) as error:
        org.grant_power_of_attorney(Actor.member(head_id), head_id, poa(P.SIGN), NOW)
    assert details_code(error) == "self_power_of_attorney"

    expired = poa(
        P.SIGN,
        issued_at=NOW.date() - timedelta(days=60),
        valid_until=NOW.date() - timedelta(days=1),
    )
    with pytest.raises(ValidationError) as error:
        org.grant_power_of_attorney(Actor.member(head_id), accountant, expired, NOW)
    assert details_code(error) == "expired"
    with pytest.raises(NotFoundError):
        org.grant_power_of_attorney(Actor.member(head_id), uuid4(), poa(P.SIGN), NOW)


def test_one_power_of_attorney_at_a_time() -> None:
    org, head_id = with_head("romashka")
    head = Actor.member(head_id)
    employee = add(org, R.EMPLOYEE)
    org.grant_power_of_attorney(head, employee, poa(P.SIGN), NOW)
    with pytest.raises(ConflictError) as error:
        org.grant_power_of_attorney(head, employee, poa(P.SUBMIT_APPLICATION, number="2"), NOW)
    assert details_code(error) == "power_of_attorney_exists"
    # An expired one is replaced.
    later = NOW + timedelta(days=400)
    org.grant_power_of_attorney(
        head,
        employee,
        poa(
            P.SUBMIT_APPLICATION,
            number="2",
            issued_at=later.date(),
            valid_until=later.date() + timedelta(days=30),
        ),
        later,
    )
    assert org.permissions_of(employee, later) == frozenset({P.VIEW, P.SUBMIT_APPLICATION})


def test_number_is_not_another_members_one() -> None:
    org, head_id = with_head("romashka")
    head = Actor.member(head_id)
    accountant = add(org, R.ACCOUNTANT)
    employee = add(org, R.EMPLOYEE)
    org.grant_power_of_attorney(head, accountant, poa(P.SIGN, number="77 АА 1234567"), NOW)
    with pytest.raises(ConflictError) as error:
        org.grant_power_of_attorney(head, employee, poa(P.SIGN, number="77аа1234567"), NOW)
    assert details_code(error) == "number_taken"
    with pytest.raises(ConflictError):
        org.add_member(head, uuid4(), R.EMPLOYEE, NOW, power_of_attorney=poa(P.SIGN))


def test_revoked_power_of_attorney_gives_nothing() -> None:
    org, head_id = with_head("romashka")
    employee = add(org, R.EMPLOYEE)
    org.grant_power_of_attorney(
        Actor.member(head_id), employee, poa(P.SUBMIT_APPLICATION, P.SIGN), NOW
    )
    accountant = add(org, R.ACCOUNTANT)
    with pytest.raises(PermissionDeniedError):
        org.revoke_power_of_attorney(Actor.member(accountant), employee, NOW)

    member = org.revoke_power_of_attorney(Actor.member(head_id), employee, NOW)

    assert member.power_of_attorney is None
    assert member.authority is Authority.UNCONFIRMED
    assert org.permissions_of(employee, NOW) == frozenset({P.VIEW})
    with pytest.raises(NotFoundError) as error:
        org.revoke_power_of_attorney(BANK, employee, NOW)
    assert details_code(error) == "power_of_attorney_not_found"
    # Revoked, it can be issued anew.
    org.grant_power_of_attorney(BANK, employee, poa(P.SIGN), NOW)
    assert org.can(employee, P.SIGN, NOW)


# --- verification ------------------------------------------------------------


def test_verification_events() -> None:
    org = organization("vector")
    org.record_verification(VerificationResult.verified(NOW), NOW)
    discrepancies = (Discrepancy("head_name", "Петров П. П.", "Сидоров С. С."),)
    org.record_verification(VerificationResult.mismatch(NOW, discrepancies), NOW)
    org.record_verification(VerificationResult(), NOW)
    events = org.pull_events()
    assert [type(e) for e in events] == [OrganizationVerified, OrganizationVerificationMismatch]
    assert isinstance(events[1], OrganizationVerificationMismatch)
    assert events[1].discrepancies == discrepancies
