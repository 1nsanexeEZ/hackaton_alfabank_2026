"""Identity rules without a database or HTTP."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.modules.identity.domain import exceptions as errors
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.entities import Consent, Role, normalize_role_rules
from src.modules.identity.domain.login_policy import Login, normalize_phone, parse_login
from src.modules.identity.domain.profile import Profile
from src.modules.identity.infrastructure.exception_handler import RESPONSES

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def make_account(email: str | None = "a@b.test", phone: str | None = None) -> Account:
    return Account.register(
        email=email,
        phone=phone,
        password_hash="hash",
        role=Role.create("client", "", [Permissions.PROFILE_UPDATE], {}),
        profile=Profile(last_name="Иванов", first_name="Иван"),
    )


# --- login ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "login"),
    [
        ("  Owner@Romashka.TEST ", Login(email="owner@romashka.test")),
        ("8 (999) 123-45-67", Login(phone="+79991234567")),
        ("+7 999 123 45 67", Login(phone="+79991234567")),
        ("not a login", None),
    ],
)
def test_parse_login(raw: str, login: Login | None) -> None:
    assert parse_login(raw) == login


def test_short_phone_is_rejected() -> None:
    with pytest.raises(ValueError, match="10-15 digits"):
        normalize_phone("12-34")


# --- roles ---------------------------------------------------------------------------------


def test_role_rules_are_deduplicated() -> None:
    permissions, policies = normalize_role_rules(
        [Permissions.ACCOUNTS_READ, Permissions.ACCOUNTS_READ],
        {Permissions.ACCOUNTS_READ: [Policies.NOT_DELETED, Policies.NOT_DELETED]},
    )
    assert permissions == ["accounts.read"]
    assert policies == {"accounts.read": ["not_deleted"]}


def test_policies_need_a_granted_permission() -> None:
    with pytest.raises(errors.OrphanedPoliciesError, match=r"\['accounts.read'\]"):
        normalize_role_rules([], {Permissions.ACCOUNTS_READ: [Policies.NOT_DELETED]})


def test_taking_a_permission_away_drops_its_policies() -> None:
    role = Role.create(
        "auditor",
        "",
        [Permissions.ACCOUNTS_READ, Permissions.ROLES_READ],
        {Permissions.ACCOUNTS_READ: [Policies.NOT_DELETED]},
    )

    role.change_rules([Permissions.ROLES_READ], None)

    assert role.permissions == ["roles.read"]
    assert role.policies == {}


# --- accounts and profiles -----------------------------------------------------------------


def test_account_needs_a_login() -> None:
    with pytest.raises(errors.LoginRequiredError):
        make_account(email=None, phone=None)
    account = make_account()
    with pytest.raises(errors.LoginRequiredError):
        account.change_login(None, None)


def test_deletion_keeps_the_first_moment() -> None:
    account = make_account()
    account.mark_deleted(NOW)
    account.mark_deleted(NOW + timedelta(days=1))
    assert account.is_deleted and account.deleted_at == NOW


def test_profile_names_cannot_be_cleared() -> None:
    profile = Profile(last_name="Иванов", first_name="Иван", middle_name="Иванович")
    with pytest.raises(errors.EmptyNameError, match="first_name can't be empty"):
        profile.apply_changes({"first_name": None})

    profile.apply_changes({"middle_name": None, "position": "Директор"})

    assert profile == Profile(last_name="Иванов", first_name="Иван", position="Директор")
    assert profile.full_name == "Иванов Иван"


# --- consents ------------------------------------------------------------------------------


def test_credit_bureau_consent_runs_out_in_six_months() -> None:
    consent = Consent.give(uuid4(), "credit_bureau_personal", NOW, ip=None, user_agent=None)

    assert consent.valid_until == datetime(2027, 4, 21, 12, 0, tzinfo=UTC)
    assert consent.text_version == "bki-fl-2026-10"
    assert consent.is_active(NOW)
    assert not consent.is_active(datetime(2027, 4, 21, 12, 0, tzinfo=UTC))


def test_personal_data_consent_lasts_until_revoked() -> None:
    consent = Consent.give(uuid4(), "personal_data", NOW, ip="10.0.0.1", user_agent="x" * 600)

    assert consent.valid_until is None
    assert consent.user_agent == "x" * 512
    assert consent.is_active(NOW + timedelta(days=3650))

    consent.revoke(NOW)
    assert not consent.is_active(NOW)


# --- errors --------------------------------------------------------------------------------


def _subclasses(cls: type[errors.IdentityError]) -> set[type[errors.IdentityError]]:
    found = set(cls.__subclasses__())
    for sub in list(found):
        found |= _subclasses(sub)
    return found


def test_every_identity_error_has_a_response() -> None:
    assert _subclasses(errors.IdentityError) <= set(RESPONSES)
