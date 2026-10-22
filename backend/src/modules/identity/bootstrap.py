import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.access.permissions import Permissions
from src.modules.identity.models import Account, Profile, Role
from src.modules.identity.passwords import PasswordHasher
from src.modules.identity.repositories import AccountRepository, RoleRepository

logger = logging.getLogger(__name__)

ADMIN_ROLE = "admin"


async def bootstrap_admin(
    session_factory: async_sessionmaker[AsyncSession],
    hasher: PasswordHasher,
    email: str,
    password: str,
) -> None:
    """Make sure the `admin` role and one admin account exist. Idempotent: an
    existing account is left as is, its password is not reset."""
    email = email.lower()
    async with session_factory() as session:
        roles = RoleRepository(session)
        accounts = AccountRepository(session)

        role = await roles.get_by_name(ADMIN_ROLE)
        if role is None:
            role = Role(
                name=ADMIN_ROLE,
                description="Full access",
                permissions=[Permissions.ADMIN.value],
                policies={},
            )
            roles.add(role)

        if await accounts.get_active_by_email(email) is None:
            accounts.add(
                Account(
                    email=email,
                    password_hash=hasher.hash(password),
                    role=role,
                    profile=Profile(last_name="Admin", first_name="Admin"),
                )
            )
            logger.info("Bootstrap admin account %s created", email)

        await session.commit()
