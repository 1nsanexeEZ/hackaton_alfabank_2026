"""Use cases for the routers: adapters are picked here, use cases see only interfaces."""

from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import NotFoundError, UnauthorizedError
from src.core.facades import use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.core.security import bearer_security
from src.core.uow import SqlAlchemyUnitOfWork, UnitOfWork
from src.modules.clients.facade import ClientsFacade
from src.modules.identity.application.interfaces.demo_accounts import DemoAccountCatalog
from src.modules.identity.application.interfaces.password_hasher import PasswordHasher
from src.modules.identity.application.interfaces.repositories import (
    AccountRepository,
    ConsentRepository,
    RoleRepository,
)
from src.modules.identity.application.interfaces.token_service import TokenService
from src.modules.identity.application.use_cases.accounts import (
    CreateAccountUseCase,
    DeleteAccountUseCase,
    GetAccountUseCase,
    ListAccountsUseCase,
    UpdateAccountUseCase,
)
from src.modules.identity.application.use_cases.auth import (
    DemoLoginUseCase,
    ListDemoAccountsUseCase,
    LoginUseCase,
)
from src.modules.identity.application.use_cases.consents import (
    GiveConsentsUseCase,
    ListMyConsentsUseCase,
    RevokeConsentUseCase,
)
from src.modules.identity.application.use_cases.me import GetMeUseCase, UpdateMyProfileUseCase
from src.modules.identity.application.use_cases.organization_consents import (
    GiveOrganizationConsentsUseCase,
    ListOrganizationConsentsUseCase,
    RevokeOrganizationConsentUseCase,
)
from src.modules.identity.application.use_cases.roles import (
    CreateRoleUseCase,
    DeleteRoleUseCase,
    GetRoleUseCase,
    ListRolesUseCase,
    UpdateRoleUseCase,
)
from src.modules.identity.infrastructure.adapters.seed_demo_accounts import SeedDemoAccountCatalog
from src.modules.identity.infrastructure.repositories.account import SqlAlchemyAccountRepository
from src.modules.identity.infrastructure.repositories.consent import SqlAlchemyConsentRepository
from src.modules.identity.infrastructure.repositories.role import SqlAlchemyRoleRepository

# --- adapters ------------------------------------------------------------------------------


def get_token_service(request: Request) -> TokenService:
    return request.app.state.token_adapter


def get_password_hasher(request: Request) -> PasswordHasher:
    return request.app.state.password_hasher


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_uow(session: DbSession) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def get_account_repository(session: DbSession) -> AccountRepository:
    return SqlAlchemyAccountRepository(session)


def get_role_repository(session: DbSession) -> RoleRepository:
    return SqlAlchemyRoleRepository(session)


def get_consent_repository(session: DbSession) -> ConsentRepository:
    return SqlAlchemyConsentRepository(session)


def get_demo_account_catalog(request: Request) -> DemoAccountCatalog:
    # Without DEMO_LOGIN_ENABLED the routes answer 404, as if they didn't exist.
    settings = request.app.state.settings
    if not settings.demo_login_enabled:
        raise NotFoundError()
    return SeedDemoAccountCatalog(settings.bootstrap_admin_email)


Tokens = Annotated[TokenService, Depends(get_token_service)]
Hasher = Annotated[PasswordHasher, Depends(get_password_hasher)]
ClockDep = Annotated[Clock, Depends(get_clock)]
Uow = Annotated[UnitOfWork, Depends(get_uow)]
Accounts = Annotated[AccountRepository, Depends(get_account_repository)]
Roles = Annotated[RoleRepository, Depends(get_role_repository)]
Consents = Annotated[ConsentRepository, Depends(get_consent_repository)]
DemoCatalog = Annotated[DemoAccountCatalog, Depends(get_demo_account_catalog)]
# Rights inside a company are kept by clients.
Clients = Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))]


def get_current_request_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_security)],
    tokens: Tokens,
) -> OpenSubTokenDTO:
    """Real implementation of src.core.access.dependencies.get_current_token,
    wired in module.wire() via dependency_overrides."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError()
    return tokens.decode(credentials.credentials)


# --- auth ----------------------------------------------------------------------------------


def get_login(uow: Uow, accounts: Accounts, hasher: Hasher, tokens: Tokens) -> LoginUseCase:
    return LoginUseCase(uow, accounts, hasher, tokens)


def get_demo_login(accounts: Accounts, catalog: DemoCatalog, tokens: Tokens) -> DemoLoginUseCase:
    return DemoLoginUseCase(accounts, catalog, tokens)


def get_list_demo_accounts(accounts: Accounts, catalog: DemoCatalog) -> ListDemoAccountsUseCase:
    return ListDemoAccountsUseCase(accounts, catalog)


# --- roles ---------------------------------------------------------------------------------


def get_list_roles(roles: Roles) -> ListRolesUseCase:
    return ListRolesUseCase(roles)


def get_get_role(roles: Roles) -> GetRoleUseCase:
    return GetRoleUseCase(roles)


def get_create_role(uow: Uow, roles: Roles) -> CreateRoleUseCase:
    return CreateRoleUseCase(uow, roles)


def get_update_role(uow: Uow, roles: Roles) -> UpdateRoleUseCase:
    return UpdateRoleUseCase(uow, roles)


def get_delete_role(uow: Uow, roles: Roles) -> DeleteRoleUseCase:
    return DeleteRoleUseCase(uow, roles)


# --- accounts ------------------------------------------------------------------------------


def get_list_accounts(accounts: Accounts) -> ListAccountsUseCase:
    return ListAccountsUseCase(accounts)


def get_get_account(accounts: Accounts) -> GetAccountUseCase:
    return GetAccountUseCase(accounts)


def get_create_account(
    uow: Uow, accounts: Accounts, roles: Roles, hasher: Hasher
) -> CreateAccountUseCase:
    return CreateAccountUseCase(uow, accounts, roles, hasher)


def get_update_account(
    uow: Uow, accounts: Accounts, roles: Roles, hasher: Hasher
) -> UpdateAccountUseCase:
    return UpdateAccountUseCase(uow, accounts, roles, hasher)


def get_delete_account(uow: Uow, accounts: Accounts, clock: ClockDep) -> DeleteAccountUseCase:
    return DeleteAccountUseCase(uow, accounts, clock)


# --- me ------------------------------------------------------------------------------------


def get_get_me(accounts: Accounts) -> GetMeUseCase:
    return GetMeUseCase(accounts)


def get_update_my_profile(uow: Uow, accounts: Accounts) -> UpdateMyProfileUseCase:
    return UpdateMyProfileUseCase(uow, accounts)


def get_list_my_consents(
    accounts: Accounts, consents: Consents, clock: ClockDep
) -> ListMyConsentsUseCase:
    return ListMyConsentsUseCase(accounts, consents, clock)


def get_give_consents(
    uow: Uow, accounts: Accounts, consents: Consents, clock: ClockDep
) -> GiveConsentsUseCase:
    return GiveConsentsUseCase(uow, accounts, consents, clock)


def get_revoke_consent(
    uow: Uow, accounts: Accounts, consents: Consents, clock: ClockDep
) -> RevokeConsentUseCase:
    return RevokeConsentUseCase(uow, accounts, consents, clock)


# --- company consents ----------------------------------------------------------------------


def get_list_organization_consents(
    accounts: Accounts, consents: Consents, clients: Clients, clock: ClockDep
) -> ListOrganizationConsentsUseCase:
    return ListOrganizationConsentsUseCase(accounts, consents, clients, clock)


def get_give_organization_consents(
    uow: Uow, accounts: Accounts, consents: Consents, clients: Clients, clock: ClockDep
) -> GiveOrganizationConsentsUseCase:
    return GiveOrganizationConsentsUseCase(uow, accounts, consents, clients, clock)


def get_revoke_organization_consent(
    uow: Uow, accounts: Accounts, consents: Consents, clients: Clients, clock: ClockDep
) -> RevokeOrganizationConsentUseCase:
    return RevokeOrganizationConsentUseCase(uow, accounts, consents, clients, clock)


LoginDep = Annotated[LoginUseCase, Depends(get_login)]
DemoLoginDep = Annotated[DemoLoginUseCase, Depends(get_demo_login)]
ListDemoAccountsDep = Annotated[ListDemoAccountsUseCase, Depends(get_list_demo_accounts)]
ListRolesDep = Annotated[ListRolesUseCase, Depends(get_list_roles)]
GetRoleDep = Annotated[GetRoleUseCase, Depends(get_get_role)]
CreateRoleDep = Annotated[CreateRoleUseCase, Depends(get_create_role)]
UpdateRoleDep = Annotated[UpdateRoleUseCase, Depends(get_update_role)]
DeleteRoleDep = Annotated[DeleteRoleUseCase, Depends(get_delete_role)]
ListAccountsDep = Annotated[ListAccountsUseCase, Depends(get_list_accounts)]
GetAccountDep = Annotated[GetAccountUseCase, Depends(get_get_account)]
CreateAccountDep = Annotated[CreateAccountUseCase, Depends(get_create_account)]
UpdateAccountDep = Annotated[UpdateAccountUseCase, Depends(get_update_account)]
DeleteAccountDep = Annotated[DeleteAccountUseCase, Depends(get_delete_account)]
GetMeDep = Annotated[GetMeUseCase, Depends(get_get_me)]
UpdateMyProfileDep = Annotated[UpdateMyProfileUseCase, Depends(get_update_my_profile)]
ListMyConsentsDep = Annotated[ListMyConsentsUseCase, Depends(get_list_my_consents)]
GiveConsentsDep = Annotated[GiveConsentsUseCase, Depends(get_give_consents)]
RevokeConsentDep = Annotated[RevokeConsentUseCase, Depends(get_revoke_consent)]
ListOrganizationConsentsDep = Annotated[
    ListOrganizationConsentsUseCase, Depends(get_list_organization_consents)
]
GiveOrganizationConsentsDep = Annotated[
    GiveOrganizationConsentsUseCase, Depends(get_give_organization_consents)
]
RevokeOrganizationConsentDep = Annotated[
    RevokeOrganizationConsentUseCase, Depends(get_revoke_organization_consent)
]
