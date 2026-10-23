from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.domain.clock import FrozenClock
from src.modules.identity.facade import AccountRefDTO, IdentityFacade
from src.modules.identity.infrastructure.adapters.argon2_hasher import Argon2PasswordHasher
from src.modules.identity.infrastructure.adapters.identity_facade import IdentityFacadeImpl
from src.modules.identity.infrastructure.repositories.account import SqlAlchemyAccountRepository
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD
from tests.identity.conftest import DEMO_PASSWORD

HASHER = Argon2PasswordHasher()


@pytest.fixture
async def session(seeded: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with seeded() as session:
        yield session


@pytest.fixture
def facade(session: AsyncSession) -> IdentityFacadeImpl:
    return IdentityFacadeImpl(session, HASHER, FrozenClock())


async def test_find_by_phone_as_people_type_it(facade: IdentityFacadeImpl) -> None:
    found = await facade.find_by_login("8 (999) 000-00-01")

    assert found is not None
    assert found == AccountRefDTO(
        id=found.id,
        email="owner@romashka.test",
        phone="+79990000001",
        role_name="client",
        last_name="Смирнова",
        first_name="Анна",
        middle_name="Сергеевна",
        position="Директор",
    )


async def test_find_by_email_in_any_case(facade: IdentityFacadeImpl) -> None:
    by_phone = await facade.find_by_login("+7 999 000-00-01")
    by_email = await facade.find_by_login("  Owner@ROMASHKA.test ")

    assert by_phone is not None and by_email is not None
    assert by_email.id == by_phone.id


@pytest.mark.parametrize("login", ["nobody@bank.test", "+79990009999", "not a phone"])
async def test_unknown_login_is_none(facade: IdentityFacadeImpl, login: str) -> None:
    assert await facade.find_by_login(login) is None


async def test_get_account(facade: IdentityFacadeImpl) -> None:
    underwriter = await facade.find_by_login("underwriter@bank.test")
    assert underwriter is not None

    assert await facade.get_account(underwriter.id) == underwriter
    assert underwriter.role_name == "underwriter"
    assert underwriter.middle_name is None
    assert underwriter.position == "Андеррайтер"
    assert await facade.get_account(uuid4()) is None


async def test_verify_password(facade: IdentityFacadeImpl) -> None:
    account = await facade.find_by_login("ivanov@ip.test")
    assert account is not None

    assert await facade.verify_password(account.id, DEMO_PASSWORD) is True
    assert await facade.verify_password(account.id, "Wrong-password-1") is False
    assert await facade.verify_password(uuid4(), DEMO_PASSWORD) is False


async def test_deleted_account_is_invisible(
    facade: IdentityFacadeImpl, session: AsyncSession
) -> None:
    account = await facade.find_by_login("owner@zakat.test")
    assert account is not None
    accounts = SqlAlchemyAccountRepository(session)
    stored = await accounts.get_active_by_id(account.id)
    assert stored is not None
    stored.mark_deleted(FrozenClock().now())
    await accounts.save(stored)
    await session.commit()

    assert await facade.get_account(account.id) is None
    assert await facade.find_by_login("owner@zakat.test") is None
    assert await facade.verify_password(account.id, DEMO_PASSWORD) is False


def test_facade_is_wired_into_the_app(client: TestClient) -> None:
    app = client.app

    async def check() -> tuple[AccountRefDTO | None, bool]:
        async with app.state.session_factory() as session:  # type: ignore[attr-defined]
            identity = app.state.facades.get(IdentityFacade, session)  # type: ignore[attr-defined]
            admin = await identity.find_by_login(ADMIN_EMAIL.upper())
            assert admin is not None
            return admin, await identity.verify_password(admin.id, ADMIN_PASSWORD)

    admin, password_ok = client.portal.call(check)  # type: ignore[union-attr]

    assert admin is not None and admin.role_name == "admin"
    assert password_ok
