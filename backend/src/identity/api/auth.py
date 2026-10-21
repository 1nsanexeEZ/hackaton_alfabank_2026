from fastapi import APIRouter

from src.core.exceptions.exceptions import UnauthorizedError
from src.identity.dependencies import AuthServiceDep, Tokens
from src.identity.schemas import JwksResponse, LoginRequest, TokenResponse

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


@router.get("/.well-known/jwks.json", response_model=JwksResponse)
async def jwks(tokens: Tokens) -> dict:
    """Public keys to verify access tokens without calling identity."""
    return tokens.jwks()
