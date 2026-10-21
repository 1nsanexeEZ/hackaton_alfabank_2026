"""Documents in MinIO (S3 API). The bucket is private; the browser uploads
and downloads by presigned URLs, the backend never streams the bytes.

Presigned URLs are signed for the public endpoint (what the browser sees,
through nginx), while HEAD/GET from the backend go to the internal one.
"""

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import aioboto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.applications.application.ports import PresignedUpload, StoredObject
from src.core.exceptions.exceptions import InfrastructureError

logger = logging.getLogger(__name__)

_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "path"})


class MinioDocumentStorage:
    def __init__(
        self,
        endpoint: str,
        public_endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ) -> None:
        self._endpoint = endpoint
        self._public_endpoint = public_endpoint
        self._bucket = bucket
        self._session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def _client(self, public: bool = False):  # type: ignore[no-untyped-def]
        endpoint = self._public_endpoint if public else self._endpoint
        return self._session.client("s3", endpoint_url=endpoint, config=_CONFIG)

    async def ensure_bucket(self) -> None:
        try:
            async with self._client() as s3:
                try:
                    await s3.head_bucket(Bucket=self._bucket)
                except ClientError:
                    await s3.create_bucket(Bucket=self._bucket)
                    logger.info("Created bucket %s", self._bucket)
        except (BotoCoreError, ClientError) as exc:
            raise InfrastructureError("Document storage is unavailable") from exc

    async def presign_upload(
        self, key: str, content_type: str, size: int, ttl_seconds: int
    ) -> PresignedUpload:
        async with self._client(public=True) as s3:
            url = await s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=ttl_seconds,
            )
        return PresignedUpload(
            url=url,
            method="PUT",
            headers={"Content-Type": content_type},
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )

    async def presign_download(self, key: str, filename: str, ttl_seconds: int) -> str:
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        async with self._client(public=True) as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ResponseContentDisposition": disposition,
                },
                ExpiresIn=ttl_seconds,
            )

    async def head(self, key: str) -> StoredObject | None:
        try:
            async with self._client() as s3:
                response = await s3.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise InfrastructureError("Document storage is unavailable") from exc
        except BotoCoreError as exc:
            raise InfrastructureError("Document storage is unavailable") from exc
        return StoredObject(
            size=int(response["ContentLength"]),
            content_type=response.get("ContentType", "application/octet-stream"),
        )

    async def read(self, key: str) -> bytes:
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                async with response["Body"] as body:
                    return await body.read()
        except (BotoCoreError, ClientError) as exc:
            raise InfrastructureError("Document storage is unavailable") from exc

    async def delete(self, key: str) -> None:
        try:
            async with self._client() as s3:
                await s3.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise InfrastructureError("Document storage is unavailable") from exc
