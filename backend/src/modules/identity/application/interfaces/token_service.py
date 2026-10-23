from typing import Any, Protocol
from uuid import UUID

from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.identity.application.dto.auth import IssuedTokenDTO


class TokenService(Protocol):
    """Access tokens. Nothing is stored server-side: a token is valid until it
    expires. Other services verify it with the public keys from `jwks()`."""

    def issue(
        self,
        subject: UUID,
        permissions: list[str],
        policies: dict[str, list[str]],
    ) -> IssuedTokenDTO: ...

    def decode(self, token: str) -> OpenSubTokenDTO:
        """TokenExpiredError or InvalidTokenError if the token can't be trusted."""
        ...

    def jwks(self) -> dict[str, list[dict[str, Any]]]: ...
