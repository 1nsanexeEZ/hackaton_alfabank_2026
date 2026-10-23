from src.core.uow import UnitOfWork
from src.modules.identity.application.dto.auth import (
    CredentialsDTO,
    DemoAccountDTO,
    IssuedTokenDTO,
)
from src.modules.identity.application.interfaces.demo_accounts import DemoAccountCatalog
from src.modules.identity.application.interfaces.password_hasher import PasswordHasher
from src.modules.identity.application.interfaces.repositories import AccountRepository
from src.modules.identity.application.interfaces.token_service import TokenService
from src.modules.identity.domain.account import Account
from src.modules.identity.domain.exceptions import (
    DemoAccountNotFoundError,
    InvalidCredentialsError,
)
from src.modules.identity.domain.login_policy import parse_login


async def find_active_by_login(accounts: AccountRepository, raw: str) -> Account | None:
    """Email in any case or phone in any format (`8 (999) 123-45-67`)."""
    login = parse_login(raw)
    return None if login is None else await accounts.get_active_by_login(login)


def issue_token(tokens: TokenService, account: Account) -> IssuedTokenDTO:
    return tokens.issue(
        subject=account.id,
        permissions=list(account.role.permissions),
        policies=dict(account.role.policies),
    )


class LoginUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        accounts: AccountRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
    ) -> None:
        self._uow = uow
        self._accounts = accounts
        self._hasher = hasher
        self._tokens = tokens

    async def execute(self, data: CredentialsDTO) -> IssuedTokenDTO:
        async with self._uow:
            account = await find_active_by_login(self._accounts, data.login)
            if account is None:
                self._hasher.verify_dummy(data.password)
                raise InvalidCredentialsError()
            if not self._hasher.verify(account.password_hash, data.password):
                raise InvalidCredentialsError()

            if self._hasher.needs_rehash(account.password_hash):
                account.set_password_hash(self._hasher.hash(data.password))
                await self._accounts.save(account)
                await self._uow.commit()

        return issue_token(self._tokens, account)


class DemoLoginUseCase:
    """One-click login into a demo account, without a password. Accounts outside
    the demo catalog are never reachable this way."""

    def __init__(
        self, accounts: AccountRepository, catalog: DemoAccountCatalog, tokens: TokenService
    ) -> None:
        self._accounts = accounts
        self._catalog = catalog
        self._tokens = tokens

    async def execute(self, login: str) -> IssuedTokenDTO:
        account = await find_active_by_login(self._accounts, login)
        if account is None or account.email is None or not self._catalog.contains(account.email):
            raise DemoAccountNotFoundError()
        return issue_token(self._tokens, account)


class ListDemoAccountsUseCase:
    def __init__(self, accounts: AccountRepository, catalog: DemoAccountCatalog) -> None:
        self._accounts = accounts
        self._catalog = catalog

    async def execute(self) -> list[DemoAccountDTO]:
        """Demo accounts that exist, in the catalog's order."""
        entries = self._catalog.list()
        found = {
            account.email: account
            for account in await self._accounts.list_active_by_emails(
                [entry.email for entry in entries]
            )
        }
        return [
            DemoAccountDTO(
                login=entry.email,
                phone=account.phone,
                role=account.role.name,
                caption=entry.caption,
                full_name=account.profile.full_name,
            )
            for entry in entries
            if (account := found.get(entry.email)) is not None
        ]
