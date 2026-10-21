from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OpenSubTokenDTO(BaseModel):
    """Verified access-token payload, as every module sees it.

    `permissions` and `policies` are a snapshot of the account's role at the
    moment the token was issued; role changes apply once the token expires.
    """

    model_config = ConfigDict(frozen=True)

    subject: UUID
    permissions: list[str] = Field(default_factory=list)
    policies: dict[str, list[str]] = Field(default_factory=dict)
    issued_at: datetime
    expires_at: datetime
