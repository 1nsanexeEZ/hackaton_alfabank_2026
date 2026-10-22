from fastapi import APIRouter

from seed.demo_data import DemoAccount
from src.core.exceptions.exceptions import NotFoundError, UnauthorizedError
from src.modules.identity.dependencies import AuthServiceDep, DemoLoginServiceDep, Tokens
from src.modules.identity.models import Account
from src.modules.identity.schemas import (
    DemoAccountRead,
    DemoLoginRequest,
    JwksResponse,
    LoginRequest,
    TokenResponse,
)

router = APIRouter(tags=["auth"])


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    responses={401: {"description": UnauthorizedError.default_message}},
)
async def login(data: LoginRequest, service: AuthServiceDep) -> TokenResponse:
    """Exchange email or phone + password for an access token. No refresh:
    log in again when the token expires."""
    issued = await service.login(data)
    return TokenResponse(access_token=issued.access_token, expires_in=issued.expires_in)


@router.post(
    "/auth/demo-login",
    response_model=TokenResponse,
    responses={404: {"description": NotFoundError.default_message}},
)
async def demo_login(data: DemoLoginRequest, service: DemoLoginServiceDep) -> TokenResponse:
    """One-click login into a demo account, without a password. Only with
    DEMO_LOGIN_ENABLED=true (off on a public stand) and only for the accounts
    from `GET /auth/demo-accounts`, otherwise 404."""
    issued = await service.login(data.login)
    return TokenResponse(access_token=issued.access_token, expires_in=issued.expires_in)


@router.get(
    "/auth/demo-accounts",
    response_model=list[DemoAccountRead],
    responses={404: {"description": NotFoundError.default_message}},
)
async def demo_accounts(service: DemoLoginServiceDep) -> list[DemoAccountRead]:
    """Demo accounts for `POST /auth/demo-login`. 404 without DEMO_LOGIN_ENABLED=true."""
    return [_demo_account(demo, account) for demo, account in await service.list_accounts()]


def _demo_account(demo: DemoAccount, account: Account) -> DemoAccountRead:
    profile = account.profile
    names = (profile.last_name, profile.first_name, profile.middle_name)
    return DemoAccountRead(
        login=demo.email,
        phone=account.phone,
        role=account.role.name,
        caption=demo.caption,
        full_name=" ".join(name for name in names if name),
    )


@router.get("/.well-known/jwks.json", response_model=JwksResponse)
async def jwks(tokens: Tokens) -> dict:
    """Public keys to verify access tokens without calling identity."""
    return tokens.jwks()
