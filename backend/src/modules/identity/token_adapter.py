import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from jwt.algorithms import RSAAlgorithm

from src.core.exceptions.exceptions import UnauthorizedError
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.identity.keys import SigningKeys

ALGORITHM = "RS256"


@dataclass(frozen=True)
class IssuedToken:
    access_token: str
    expires_at: datetime
    expires_in: int


class TokenAdapter:
    """Issues and verifies access JWTs (RS256).

    Only access tokens, nothing is stored server-side: a token is valid until
    `exp`. Other services verify it with the public key from JWKS.
    """

    def __init__(self, keys: SigningKeys, issuer: str, audience: str, ttl: timedelta) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience
        self._ttl = ttl

    def issue(
        self,
        subject: UUID,
        permissions: list[str],
        policies: dict[str, list[str]],
    ) -> IssuedToken:
        issued_at = datetime.now(UTC).replace(microsecond=0)
        expires_at = issued_at + self._ttl
        payload: dict[str, Any] = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(subject),
            "iat": issued_at,
            "exp": expires_at,
            "permissions": permissions,
            "policies": policies,
        }
        token = jwt.encode(
            payload, self._keys.private_key, algorithm=ALGORITHM, headers={"kid": self._keys.kid}
        )
        return IssuedToken(
            access_token=token,
            expires_at=expires_at,
            expires_in=int(self._ttl.total_seconds()),
        )

    def decode(self, token: str) -> OpenSubTokenDTO:
        try:
            payload = jwt.decode(
                token,
                self._keys.public_key,
                algorithms=[ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
            return OpenSubTokenDTO(
                subject=UUID(payload["sub"]),
                permissions=payload.get("permissions", []),
                policies=payload.get("policies", {}),
                issued_at=datetime.fromtimestamp(payload["iat"], UTC),
                expires_at=datetime.fromtimestamp(payload["exp"], UTC),
            )
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedError("Token expired") from exc
        except (jwt.InvalidTokenError, ValueError) as exc:
            raise UnauthorizedError("Invalid token") from exc

    def jwks(self) -> dict[str, list[dict[str, Any]]]:
        jwk = json.loads(RSAAlgorithm.to_jwk(self._keys.public_key))
        jwk.update({"kid": self._keys.kid, "use": "sig", "alg": ALGORITHM})
        return {"keys": [jwk]}
