"""Archive of contract PDFs in MinIO: its own private bucket with Object Lock.

A written object cannot be overwritten or deleted until its retention date
(governance mode, five years by default: documents are kept at least five years
after the relationship with the client ends). The browser never talks to this
bucket: the backend reads the file and gives it to the client itself.

A MinIO build without Object Lock (single drive in the old FS mode) still gets
a private bucket; the backend logs that the files are not locked.
"""

import logging
from datetime import UTC, datetime, timedelta

import aioboto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.core.exceptions.exceptions import InfrastructureError
from src.modules.applications.application.interfaces.contracts import ContractArchive

logger = logging.getLogger(__name__)

_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "path"})
RETENTION_DAYS = 5 * 365


class MinioContractArchive(ContractArchive):
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        retention_days: int = RETENTION_DAYS,
        region: str = "us-east-1",
    ) -> None:
        self._endpoint = endpoint
        self._bucket = bucket
        self._retention = timedelta(days=retention_days)
        self._locked = True
        self._session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def _client(self):  # type: ignore[no-untyped-def]
        return self._session.client("s3", endpoint_url=self._endpoint, config=_CONFIG)

    async def ensure_bucket(self) -> None:
        try:
            async with self._client() as s3:
                try:
                    await s3.head_bucket(Bucket=self._bucket)
                except ClientError:
                    try:
                        await s3.create_bucket(Bucket=self._bucket, ObjectLockEnabledForBucket=True)
                    except ClientError:
                        await s3.create_bucket(Bucket=self._bucket)
                    logger.info("Created bucket %s", self._bucket)
                try:
                    await s3.get_object_lock_configuration(Bucket=self._bucket)
                except ClientError:
                    self._locked = False
                    logger.warning(
                        "Bucket %s has no Object Lock: contracts are not locked", self._bucket
                    )
        except (BotoCoreError, ClientError) as exc:
            raise InfrastructureError("Contract archive is unavailable") from exc

    async def put(self, key: str, content: bytes) -> None:
        params: dict[str, object] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": content,
            "ContentType": "application/pdf",
        }
        if self._locked:
            params["ObjectLockMode"] = "GOVERNANCE"
            params["ObjectLockRetainUntilDate"] = datetime.now(UTC) + self._retention
        try:
            async with self._client() as s3:
                await s3.put_object(**params)
        except (BotoCoreError, ClientError) as exc:
            raise InfrastructureError("Contract archive is unavailable") from exc

    async def read(self, key: str) -> bytes:
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                async with response["Body"] as body:
                    return await body.read()
        except (BotoCoreError, ClientError) as exc:
            raise InfrastructureError("Contract archive is unavailable") from exc
