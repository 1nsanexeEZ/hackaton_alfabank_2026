from typing import Any

from fastapi import APIRouter

from src.core.exceptions.exceptions import NotFoundError, UnauthorizedError
from src.modules.identity.presentation.dependencies import (
    DemoLoginDep,
    ListDemoAccountsDep,
    LoginDep,
    Tokens,
)
from src.modules.identity.presentation.schemas.auth import (
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
async def login(data: LoginRequest, use_case: LoginDep) -> TokenResponse:
    """Exchange email or phone + password for an access token. No refresh:
    log in again when the token expires."""
    return TokenResponse.from_dto(await use_case.execute(data.to_dto()))


@router.post(
    "/auth/demo-login",
    response_model=TokenResponse,
    responses={404: {"description": NotFoundError.default_message}},
)
async def demo_login(data: DemoLoginRequest, use_case: DemoLoginDep) -> TokenResponse:
    """One-click login into a demo account, without a password. Only with
    DEMO_LOGIN_ENABLED=true (off on a public stand) and only for the accounts
    from `GET /auth/demo-accounts`, otherwise 404."""
    return TokenResponse.from_dto(await use_case.execute(data.login))


@router.get(
    "/auth/demo-accounts",
    response_model=list[DemoAccountRead],
    responses={404: {"description": NotFoundError.default_message}},
)
async def demo_accounts(use_case: ListDemoAccountsDep) -> list[DemoAccountRead]:
    """Demo accounts for `POST /auth/demo-login`. 404 without DEMO_LOGIN_ENABLED=true."""
    return [DemoAccountRead.model_validate(account) for account in await use_case.execute()]


@router.get("/.well-known/jwks.json", response_model=JwksResponse)
async def jwks(tokens: Tokens) -> dict[str, Any]:
    """Public keys to verify access tokens without calling identity."""
    return tokens.jwks()
