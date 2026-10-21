from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.access_context import AccessContext
from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.core.exceptions.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)
from src.identity.models import Account, Profile, Role
from src.identity.passwords import PasswordHasher
from src.identity.repositories import AccountRepository, RoleRepository
from src.identity.schemas import (
    AccountCreate,
    AccountUpdate,
    LoginRequest,
    ProfileUpdate,
    RoleCreate,
    RoleUpdate,
    normalize_phone,
)
from src.identity.token_adapter import IssuedToken, TokenAdapter

INVALID_CREDENTIALS = "Invalid login or password"


async def find_active_by_login(accounts: AccountRepository, login: str) -> Account | None:
    """Email in any case or phone in any format (`8 (999) 123-45-67`)."""
    login = login.strip()
    if "@" in login:
        return await accounts.get_active_by_email(login.lower())
    try:
        phone = normalize_phone(login)
    except ValueError:
        return None
    return await accounts.get_active_by_phone(phone)


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        accounts: AccountRepository,
        hasher: PasswordHasher,
        tokens: TokenAdapter,
    ) -> None:
        self._session = session
        self._accounts = accounts
        self._hasher = hasher
        self._tokens = tokens

    async def login(self, data: LoginRequest) -> IssuedToken:
        password = data.password.get_secret_value()
        account = await find_active_by_login(self._accounts, data.login)
        if account is None:
            self._hasher.verify_dummy(password)
            raise UnauthorizedError(INVALID_CREDENTIALS)
        if not self._hasher.verify(account.password_hash, password):
            raise UnauthorizedError(INVALID_CREDENTIALS)

        if self._hasher.needs_rehash(account.password_hash):
            account.password_hash = self._hasher.hash(password)
            await self._session.commit()

        return self._tokens.issue(
            subject=account.id,
            permissions=list(account.role.permissions),
            policies=dict(account.role.policies),
        )


def normalize_role_rules(
    permissions: Sequence[Permissions],
    policies: dict[Permissions, list[Policies]],
) -> tuple[list[str], dict[str, list[str]]]:
    """Dedupe and check that policies are attached only to granted permissions."""
    granted = list(dict.fromkeys(p.value for p in permissions))
    orphaned = sorted(p.value for p in policies if p.value not in granted)
    if orphaned:
        raise BadRequestError(f"Policies set for permissions the role doesn't have: {orphaned}")
    rules = {
        permission.value: list(dict.fromkeys(policy.value for policy in attached))
        for permission, attached in policies.items()
    }
    return granted, rules


class RoleService:
    def __init__(self, session: AsyncSession, roles: RoleRepository) -> None:
        self._session = session
        self._roles = roles

    async def list(self, access: AccessContext) -> Sequence[Role]:
        return await self._roles.list(access)

    async def get(self, access: AccessContext, role_id: UUID) -> Role:
        role = await self._roles.get(access, role_id)
        if role is None:
            raise NotFoundError("Role not found")
        return role

    async def create(self, data: RoleCreate) -> Role:
        if await self._roles.get_by_name(data.name) is not None:
            raise ConflictError(f"Role {data.name!r} already exists")
        permissions, policies = normalize_role_rules(data.permissions, data.policies)
        role = Role(
            name=data.name,
            description=data.description,
            permissions=permissions,
            policies=policies,
        )
        self._roles.add(role)
        await self._session.commit()
        return role

    async def update(self, access: AccessContext, role_id: UUID, data: RoleUpdate) -> Role:
        role = await self.get(access, role_id)
        if data.name is not None and data.name != role.name:
            if await self._roles.get_by_name(data.name) is not None:
                raise ConflictError(f"Role {data.name!r} already exists")
            role.name = data.name
        if data.description is not None:
            role.description = data.description
        if data.permissions is not None or data.policies is not None:
            permissions = (
                data.permissions
                if data.permissions is not None
                else [Permissions(p) for p in role.permissions]
            )
            policies = (
                data.policies
                if data.policies is not None
                else {
                    Permissions(k): [Policies(p) for p in v]
                    for k, v in role.policies.items()
                    if Permissions(k) in permissions
                }
            )
            role.permissions, role.policies = normalize_role_rules(permissions, policies)
        await self._session.commit()
        return role

    async def delete(self, access: AccessContext, role_id: UUID) -> None:
        role = await self.get(access, role_id)
        if await self._roles.is_in_use(role.id):
            raise ConflictError("Role is assigned to accounts")
        await self._roles.delete(role)
        await self._session.commit()


class AccountService:
    def __init__(
        self,
        session: AsyncSession,
        accounts: AccountRepository,
        roles: RoleRepository,
        hasher: PasswordHasher,
    ) -> None:
        self._session = session
        self._accounts = accounts
        self._roles = roles
        self._hasher = hasher

    async def list(self, access: AccessContext, limit: int, offset: int) -> Sequence[Account]:
        return await self._accounts.list(access, limit, offset)

    async def get(self, access: AccessContext, account_id: UUID) -> Account:
        account = await self._accounts.get(access, account_id)
        if account is None:
            raise NotFoundError("Account not found")
        return account

    async def create(self, data: AccountCreate) -> Account:
        role = await self._get_role(data.role_id)
        if await self._accounts.login_taken(data.email, data.phone):
            raise ConflictError("Email or phone is already taken")
        account = Account(
            email=data.email,
            phone=data.phone,
            password_hash=self._hasher.hash(data.password.get_secret_value()),
            role=role,
            profile=Profile(**data.profile.model_dump()),
        )
        self._accounts.add(account)
        await self._session.commit()
        return account

    async def update(self, access: AccessContext, account_id: UUID, data: AccountUpdate) -> Account:
        account = await self.get(access, account_id)
        if account.is_deleted:
            raise NotFoundError("Account not found")
        changes = data.model_dump(exclude_unset=True, exclude={"password", "profile"})

        if "email" in changes or "phone" in changes:
            email = changes.get("email", account.email)
            phone = changes.get("phone", account.phone)
            if email is None and phone is None:
                raise BadRequestError("Either email or phone is required")
            if await self._accounts.login_taken(
                email if "email" in changes else None,
                phone if "phone" in changes else None,
                exclude_id=account.id,
            ):
                raise ConflictError("Email or phone is already taken")
            account.email, account.phone = email, phone
        if changes.get("role_id") is not None:
            account.role = await self._get_role(changes["role_id"])
        if data.password is not None:
            account.password_hash = self._hasher.hash(data.password.get_secret_value())
        if data.profile is not None:
            _apply_profile(account.profile, data.profile)

        await self._session.commit()
        return account

    async def delete(self, access: AccessContext, account_id: UUID) -> None:
        account = await self.get(access, account_id)
        if account.id == access.user_id:
            raise BadRequestError("You can't delete your own account")
        if not account.is_deleted:
            account.mark_deleted()
            await self._session.commit()

    async def me(self, user_id: UUID) -> Account:
        account = await self._accounts.get_active_by_id(user_id)
        if account is None:
            raise UnauthorizedError("Account not found")
        return account

    async def update_my_profile(self, user_id: UUID, data: ProfileUpdate) -> Account:
        account = await self.me(user_id)
        _apply_profile(account.profile, data)
        await self._session.commit()
        return account

    async def _get_role(self, role_id: UUID) -> Role:
        role = await self._roles.get_by_id(role_id)
        if role is None:
            raise BadRequestError("Role not found")
        return role


def _apply_profile(profile: Profile, data: ProfileUpdate) -> None:
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field in ("last_name", "first_name"):
            raise BadRequestError(f"{field} can't be empty")
        setattr(profile, field, value)
