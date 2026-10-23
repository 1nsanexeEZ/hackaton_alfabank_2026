import logging

from src.core.access.permissions import Permissions
from src.core.uow import UnitOfWork
from src.modules.identity.application.interfaces.password_hasher import PasswordHasher
from src.modules.identity.application.interfaces.repositories import (
    AccountRepository,
    RoleRepository,
)
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.entities import Role
from src.modules.identity.domain.login_policy import Login, normalize_email
from src.modules.identity.domain.profile import Profile

logger = logging.getLogger(__name__)

ADMIN_ROLE = "admin"


class BootstrapAdminUseCase:
    """Make sure the `admin` role and one admin account exist. Idempotent: an
    existing account is left as is, its password is not reset."""

    def __init__(
        self,
        uow: UnitOfWork,
        accounts: AccountRepository,
        roles: RoleRepository,
        hasher: PasswordHasher,
    ) -> None:
        self._uow = uow
        self._accounts = accounts
        self._roles = roles
        self._hasher = hasher

    async def execute(self, email: str, password: str) -> None:
        email = normalize_email(email)
        async with self._uow:
            role = await self._roles.get_by_name(ADMIN_ROLE)
            if role is None:
                role = Role.create(ADMIN_ROLE, "Full access", [Permissions.ADMIN], {})
                await self._roles.add(role)

            if await self._accounts.get_active_by_login(Login(email=email)) is None:
                await self._accounts.add(
                    Account.register(
                        email=email,
                        phone=None,
                        password_hash=self._hasher.hash(password),
                        role=role,
                        profile=Profile(last_name="Admin", first_name="Admin"),
                    )
                )
                logger.info("Bootstrap admin account %s created", email)

            await self._uow.commit()
