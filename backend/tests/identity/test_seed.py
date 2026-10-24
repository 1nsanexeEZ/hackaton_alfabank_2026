from typing import TypeAlias

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seed import identity
from seed.demo_data import ACCOUNTS
from src.modules.identity.infrastructure.adapters.argon2_hasher import Argon2PasswordHasher
from src.modules.identity.infrastructure.database.models import (
    AccountModel,
    ProfileModel,
    RoleModel,
)
from tests.identity.conftest import DEMO_PASSWORD, seed_context

Sessions: TypeAlias = async_sessionmaker[AsyncSession]

CLIENT_PERMISSIONS = [
    "requests.read",
    "requests.create",
    "requests.update",
    "credits.read",
    "organizations.read",
    "organizations.update",
    "feed.read",
    "profile.update",
    "support.read",
    "support.create",
]
CLIENT_POLICIES = {
    "requests.read": ["org_member"],
    "requests.create": ["org_member"],
    "requests.update": ["org_member"],
    "organizations.read": ["org_member"],
    "organizations.update": ["org_member"],
    "support.read": ["own_only"],
    "support.create": ["own_only"],
}
UNDERWRITER_PERMISSIONS = [
    "requests.read",
    "credits.read",
    "organizations.read",
    "organizations.update",
    "tasks.read",
    "tasks.update",
    "decisions.read",
    "scoring.read",
    "backoffice.read",
    "feed.read",
    "profile.update",
    "profile.update_name",
    "support.manage",
]


async def roles_by_name(sessions: Sessions) -> dict[str, RoleModel]:
    async with sessions() as session:
        return {role.name: role for role in (await session.scalars(select(RoleModel))).all()}


async def accounts_by_email(sessions: Sessions) -> dict[str | None, AccountModel]:
    async with sessions() as session:
        accounts = (await session.scalars(select(AccountModel))).unique().all()
    assert len({account.email for account in accounts}) == len(accounts), "duplicate emails"
    return {account.email: account for account in accounts}


async def snapshot(sessions: Sessions) -> tuple[list[tuple], list[tuple]]:
    roles = await roles_by_name(sessions)
    accounts = await accounts_by_email(sessions)
    return (
        sorted(
            (r.id, r.name, r.description, r.permissions, r.policies, r.updated_at)
            for r in roles.values()
        ),
        sorted(
            (a.id, a.email, a.phone, a.role_id, a.password_hash, a.updated_at)
            for a in accounts.values()
        ),
    )


async def test_roles_have_exactly_the_declared_rights(seeded: Sessions) -> None:
    roles = await roles_by_name(seeded)

    assert set(roles) == {"client", "underwriter"}
    assert roles["client"].permissions == CLIENT_PERMISSIONS
    assert roles["client"].policies == CLIENT_POLICIES
    assert roles["underwriter"].permissions == UNDERWRITER_PERMISSIONS
    # The underwriter sees every client: no row-level policies.
    assert roles["underwriter"].policies == {}


async def test_demo_accounts_follow_demo_data(seeded: Sessions) -> None:
    accounts = await accounts_by_email(seeded)
    hasher = Argon2PasswordHasher()

    assert set(accounts) == {demo.email for demo in ACCOUNTS}
    for demo in ACCOUNTS:
        account = accounts[demo.email]
        assert account.phone == demo.phone
        assert account.role.name == demo.identity_role
        assert (
            account.profile.last_name,
            account.profile.first_name,
            account.profile.middle_name,
        ) == (demo.person.last_name, demo.person.first_name, demo.person.middle_name)
        assert hasher.verify(account.password_hash, DEMO_PASSWORD), demo.email


async def test_positions_are_short_titles(seeded: Sessions) -> None:
    accounts = await accounts_by_email(seeded)
    positions = {email: account.profile.position for email, account in accounts.items()}

    assert positions["owner@romashka.test"] == "Директор"
    assert positions["accountant@romashka.test"] == "Бухгалтер"
    assert positions["ivanov@ip.test"] == "Индивидуальный предприниматель"
    assert positions["petrov@vector.test"] == "Директор"
    assert positions["underwriter@bank.test"] == "Андеррайтер"


async def test_second_run_changes_nothing(seeded: Sessions) -> None:
    before = await snapshot(seeded)

    await identity.seed(seed_context(seeded))

    assert await snapshot(seeded) == before


async def test_edited_role_is_brought_back_to_the_declared_rights(seeded: Sessions) -> None:
    async with seeded() as session:
        role = (await session.scalars(select(RoleModel).where(RoleModel.name == "client"))).one()
        role.permissions = ["requests.read", "accounts.read"]
        role.policies = {}
        await session.commit()

    await identity.seed(seed_context(seeded))

    client = (await roles_by_name(seeded))["client"]
    assert client.permissions == CLIENT_PERMISSIONS
    assert client.policies == CLIENT_POLICIES


async def test_existing_account_keeps_its_password(seeded: Sessions) -> None:
    hasher = Argon2PasswordHasher()
    async with seeded() as session:
        account = (
            (
                await session.scalars(
                    select(AccountModel).where(AccountModel.email == "owner@romashka.test")
                )
            )
            .unique()
            .one()
        )
        account.password_hash = hasher.hash("Changed-password-1")
        await session.commit()

    await identity.seed(seed_context(seeded))

    account = (await accounts_by_email(seeded))["owner@romashka.test"]
    assert hasher.verify(account.password_hash, "Changed-password-1")


async def test_taken_login_is_skipped(session_factory: Sessions) -> None:
    """Someone already has the demo phone: the seed leaves it alone instead of
    failing the startup on the unique index."""
    async with session_factory() as session:
        role = RoleModel(name="manager", permissions=[], policies={})
        session.add(
            AccountModel(
                email="someone@example.com",
                phone="+79990000001",
                password_hash=Argon2PasswordHasher().hash("Some-password-1"),
                role=role,
                profile=ProfileModel(last_name="Иной", first_name="Иван"),
            )
        )
        await session.commit()

    await identity.seed(seed_context(session_factory))

    accounts = await accounts_by_email(session_factory)
    demo_emails = {demo.email for demo in ACCOUNTS}
    assert set(accounts) == demo_emails - {"owner@romashka.test"} | {"someone@example.com"}
    assert accounts["someone@example.com"].phone == "+79990000001"
