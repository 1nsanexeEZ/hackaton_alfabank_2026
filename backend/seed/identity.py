"""Seed of identity: roles client/underwriter and demo accounts."""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from seed.demo_data import ACCOUNTS, COMPANIES_BY_CODE, DemoAccount
from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.modules.identity.application.interfaces.repositories import RoleRepository
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.entities import Role, normalize_role_rules
from src.modules.identity.domain.login_policy import normalize_email, normalize_phone
from src.modules.identity.domain.profile import Profile
from src.modules.identity.infrastructure.adapters.argon2_hasher import Argon2PasswordHasher
from src.modules.identity.infrastructure.repositories.account import SqlAlchemyAccountRepository
from src.modules.identity.infrastructure.repositories.role import SqlAlchemyRoleRepository

if TYPE_CHECKING:
    from seed.run import SeedContext

logger = logging.getLogger(__name__)

ORG_MEMBER = [Policies.ORG_MEMBER]


@dataclass(frozen=True, slots=True)
class RoleSpec:
    name: str
    description: str
    permissions: tuple[Permissions, ...]
    policies: dict[Permissions, list[Policies]] = field(default_factory=dict)


ROLES: tuple[RoleSpec, ...] = (
    RoleSpec(
        name="client",
        description="Клиент: заявки и компании, где он участник",
        permissions=(
            Permissions.REQUESTS_READ,
            Permissions.REQUESTS_CREATE,
            Permissions.REQUESTS_UPDATE,
            Permissions.CREDITS_READ,
            Permissions.ORGANIZATIONS_READ,
            Permissions.ORGANIZATIONS_UPDATE,
            Permissions.FEED_READ,
            Permissions.PROFILE_UPDATE,
        ),
        policies={
            Permissions.REQUESTS_READ: ORG_MEMBER,
            Permissions.REQUESTS_CREATE: ORG_MEMBER,
            Permissions.REQUESTS_UPDATE: ORG_MEMBER,
            Permissions.ORGANIZATIONS_READ: ORG_MEMBER,
            Permissions.ORGANIZATIONS_UPDATE: ORG_MEMBER,
        },
    ),
    RoleSpec(
        name="underwriter",
        description="Андеррайтер: заявки, задачи и решения всех клиентов",
        permissions=(
            Permissions.REQUESTS_READ,
            Permissions.CREDITS_READ,
            Permissions.ORGANIZATIONS_READ,
            # Without a policy: the registry check of any company.
            Permissions.ORGANIZATIONS_UPDATE,
            Permissions.TASKS_READ,
            Permissions.TASKS_UPDATE,
            Permissions.DECISIONS_READ,
            Permissions.BACKOFFICE_READ,
            Permissions.FEED_READ,
            Permissions.PROFILE_UPDATE,
        ),
    ),
)

_POSITIONS = {"director": "Директор", "accountant": "Бухгалтер", "employee": "Сотрудник"}


def position_of(account: DemoAccount) -> str | None:
    """Short job title for the profile, by the first company role."""
    if account.identity_role == "underwriter":
        return "Андеррайтер"
    if not account.memberships:
        return None
    membership = account.memberships[0]
    if membership.role == "owner":
        company = COMPANIES_BY_CODE[membership.company_code]
        return "Индивидуальный предприниматель" if company.legal_form == "IE" else "Учредитель"
    return _POSITIONS[membership.role]


async def seed(context: "SeedContext") -> None:
    """Idempotent. Roles are brought to the declared rights on every run;
    an existing account is left as is, its password is not reset."""
    # Every demo account has the same public DEMO_PASSWORD: one hash is enough.
    password_hash = Argon2PasswordHasher().hash(context.settings.demo_password)
    async with context.session_factory() as session:
        roles_repo = SqlAlchemyRoleRepository(session)
        accounts = SqlAlchemyAccountRepository(session)

        roles: dict[str, Role] = {}
        for spec in ROLES:
            roles[spec.name] = await _ensure_role(roles_repo, spec)

        created = 0
        for demo in ACCOUNTS:
            email = normalize_email(demo.email)
            phone = normalize_phone(demo.phone) if demo.phone else None
            if await accounts.login_taken(email, phone):
                continue
            await accounts.add(
                Account.register(
                    email=email,
                    phone=phone,
                    password_hash=password_hash,
                    role=roles[demo.identity_role],
                    profile=Profile(
                        last_name=demo.person.last_name,
                        first_name=demo.person.first_name,
                        middle_name=demo.person.middle_name,
                        position=position_of(demo),
                    ),
                )
            )
            created += 1

        await session.commit()
    logger.info("Demo accounts created: %d", created)


async def _ensure_role(roles: RoleRepository, spec: RoleSpec) -> Role:
    role = await roles.get_by_name(spec.name)
    if role is None:
        role = Role.create(spec.name, spec.description, spec.permissions, spec.policies)
        await roles.add(role)
        return role
    permissions, policies = normalize_role_rules(spec.permissions, spec.policies)
    # Compared first, so an unchanged role keeps its updated_at.
    if (role.description, role.permissions, role.policies) != (
        spec.description,
        permissions,
        policies,
    ):
        role.description = spec.description
        role.permissions, role.policies = permissions, policies
        await roles.save(role)
    return role
