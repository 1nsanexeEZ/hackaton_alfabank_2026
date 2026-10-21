from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.exceptions.exceptions import NotFoundError, UnauthorizedError
from src.core.infrastructure.database.session import DbSession
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.core.security import bearer_security
from src.identity.passwords import PasswordHasher
from src.identity.repositories import AccountRepository, RoleRepository
from src.identity.services import AccountService, AuthService, DemoLoginService, RoleService
from src.identity.token_adapter import TokenAdapter


def get_token_adapter(request: Request) -> TokenAdapter:
    return request.app.state.token_adapter


def get_password_hasher(request: Request) -> PasswordHasher:
    return request.app.state.password_hasher


Tokens = Annotated[TokenAdapter, Depends(get_token_adapter)]
Hasher = Annotated[PasswordHasher, Depends(get_password_hasher)]


def get_current_request_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_security)],
    tokens: Tokens,
) -> OpenSubTokenDTO:
    """Real implementation of src.core.access.dependencies.get_current_token,
    wired in create_app() via dependency_overrides."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError()
    return tokens.decode(credentials.credentials)


def get_auth_service(session: DbSession, hasher: Hasher, tokens: Tokens) -> AuthService:
    return AuthService(session, AccountRepository(session), hasher, tokens)


def get_demo_login_service(
    request: Request, session: DbSession, tokens: Tokens
) -> DemoLoginService:
    # Without DEMO_LOGIN_ENABLED the routes answer 404, as if they didn't exist.
    if not request.app.state.settings.demo_login_enabled:
        raise NotFoundError()
    return DemoLoginService(AccountRepository(session), tokens)


def get_account_service(session: DbSession, hasher: Hasher) -> AccountService:
    return AccountService(session, AccountRepository(session), RoleRepository(session), hasher)


def get_role_service(session: DbSession) -> RoleService:
    return RoleService(session, RoleRepository(session))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
DemoLoginServiceDep = Annotated[DemoLoginService, Depends(get_demo_login_service)]
AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]
