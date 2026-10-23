from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    url: str
    method: str
    headers: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class StoredObject:
    size: int
    content_type: str


class DocumentStorage(Protocol):
    """Private bucket; the browser talks to it only through short-lived URLs."""

    async def presign_upload(
        self, key: str, content_type: str, size: int, ttl_seconds: int
    ) -> PresignedUpload: ...

    async def presign_download(self, key: str, filename: str, ttl_seconds: int) -> str: ...

    async def head(self, key: str) -> StoredObject | None: ...

    async def read(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...
