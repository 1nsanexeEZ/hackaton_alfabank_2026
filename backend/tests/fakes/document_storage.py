from datetime import UTC, datetime, timedelta

from src.applications.application.ports import PresignedUpload, StoredObject


class FakeDocumentStorage:
    """In-memory bucket. `put` plays the browser uploading by the presigned URL."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []

    def put(self, key: str, content: bytes, content_type: str) -> None:
        self.objects[key] = (content, content_type)

    async def presign_upload(
        self, key: str, content_type: str, size: int, ttl_seconds: int
    ) -> PresignedUpload:
        return PresignedUpload(
            url=f"http://storage.test/credit-documents/{key}?X-Amz-Signature=fake",
            method="PUT",
            headers={"Content-Type": content_type},
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )

    async def presign_download(self, key: str, filename: str, ttl_seconds: int) -> str:
        return f"http://storage.test/credit-documents/{key}?download=1"

    async def head(self, key: str) -> StoredObject | None:
        if key not in self.objects:
            return None
        content, content_type = self.objects[key]
        return StoredObject(size=len(content), content_type=content_type)

    async def read(self, key: str) -> bytes:
        return self.objects[key][0]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.deleted.append(key)
