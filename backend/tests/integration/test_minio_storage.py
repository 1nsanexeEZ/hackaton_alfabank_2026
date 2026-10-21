"""Presigned upload and download against a real MinIO (Docker)."""

from collections.abc import Iterator

import httpx
import pytest

from src.applications.infrastructure.storage import MinioDocumentStorage

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def minio_endpoint() -> Iterator[str]:
    from testcontainers.community.minio import MinioContainer

    with MinioContainer() as minio:
        yield f"http://{minio.get_config()['endpoint']}"


async def test_browser_flow_through_presigned_urls(minio_endpoint: str) -> None:
    storage = MinioDocumentStorage(
        endpoint=minio_endpoint,
        public_endpoint=minio_endpoint,
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="credit-documents",
    )
    await storage.ensure_bucket()
    await storage.ensure_bucket()  # idempotent

    key = "applications/a/b"
    content = b"date;amount\n2026-01-05;150000.00\n"
    assert await storage.head(key) is None

    upload = await storage.presign_upload(key, "text/csv", len(content), 300)
    async with httpx.AsyncClient() as browser:
        put = await browser.put(upload.url, content=content, headers=upload.headers)
        assert put.status_code == 200, put.text

        stored = await storage.head(key)
        assert stored is not None
        assert (stored.size, stored.content_type) == (len(content), "text/csv")
        assert await storage.read(key) == content

        download = await browser.get(await storage.presign_download(key, "выписка.csv", 60))
        assert download.status_code == 200
        assert download.content == content
        assert "attachment" in download.headers["content-disposition"]

        # a URL signed for text/csv does not accept another content type
        forged = await browser.put(
            upload.url, content=b"MZ", headers={"Content-Type": "application/x-msdownload"}
        )
        assert forged.status_code == 403

    await storage.delete(key)
    assert await storage.head(key) is None
