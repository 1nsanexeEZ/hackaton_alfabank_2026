import pytest

from tests.applications.api.conftest import World

STATEMENT = b"date;amount\n2026-01-05;150000.00\n"


def test_presigned_upload_and_confirm(world: World) -> None:
    application = world.create()
    headers = world.headers(world.director)
    announced = world.client.post(
        f"/applications/{application['id']}/documents",
        json={
            "type": "bank_statement",
            "filename": "выписка.csv",
            "content_type": "text/csv",
            "size_bytes": len(STATEMENT),
        },
        headers=headers,
    )
    assert announced.status_code == 201
    body = announced.json()
    document = body["document"]
    assert document["status"] == "pending_upload"
    assert body["upload"]["method"] == "PUT"
    assert body["upload"]["headers"] == {"Content-Type": "text/csv"}
    assert document["id"] in body["upload"]["url"]

    confirm_url = f"/applications/{application['id']}/documents/{document['id']}/confirm"
    not_yet = world.client.post(confirm_url, headers=headers)
    assert not_yet.status_code == 422
    assert not_yet.json()["details"]["code"] == "upload_missing"

    world.storage.put(f"applications/{application['id']}/{document['id']}", STATEMENT, "text/csv")
    confirmed = world.client.post(confirm_url, headers=headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "uploaded"


def test_stored_file_must_match(world: World) -> None:
    application = world.create()
    headers = world.headers(world.director)
    document = world.client.post(
        f"/applications/{application['id']}/documents",
        json={
            "type": "bank_statement",
            "filename": "s.csv",
            "content_type": "text/csv",
            "size_bytes": 5,
        },
        headers=headers,
    ).json()["document"]
    # the browser sent something else than announced
    world.storage.put(
        f"applications/{application['id']}/{document['id']}",
        b"MZ\x90\x00\x03",
        "application/x-msdownload",
    )
    response = world.client.post(
        f"/applications/{application['id']}/documents/{document['id']}/confirm", headers=headers
    )
    assert response.status_code == 422
    assert response.json()["details"] == {"code": "upload_mismatch"}


def test_disallowed_files(world: World) -> None:
    application = world.create()
    url = f"/applications/{application['id']}/documents"
    headers = world.headers(world.director)
    pdf_statement = world.client.post(
        url,
        json={
            "type": "bank_statement",
            "filename": "s.pdf",
            "content_type": "application/pdf",
            "size_bytes": 10,
        },
        headers=headers,
    )
    assert pdf_statement.status_code == 422
    huge = world.client.post(
        url,
        json={
            "type": "other",
            "filename": "big.pdf",
            "content_type": "application/pdf",
            "size_bytes": 21 * 1024 * 1024,
        },
        headers=headers,
    )
    assert huge.status_code == 422
    bad_type = world.client.post(
        url,
        json={
            "type": "../etc",
            "filename": "x.pdf",
            "content_type": "application/pdf",
            "size_bytes": 10,
        },
        headers=headers,
    )
    assert bad_type.status_code == 422


def test_download_and_delete(world: World) -> None:
    application = world.create()
    document = world.upload(application)
    headers = world.headers(world.director)
    base = f"/applications/{application['id']}/documents/{document['id']}"

    download = world.client.get(f"{base}/download", headers=headers)
    assert download.status_code == 200
    assert "download=1" in download.json()["url"]
    assert world.client.get(f"{base}/download", headers=world.underwriter()).status_code == 200
    assert (
        world.client.get(f"{base}/download", headers=world.headers(world.petrov)).status_code == 404
    )

    assert world.client.delete(base, headers=headers).status_code == 204
    key = f"applications/{application['id']}/{document['id']}"
    assert key in world.storage.deleted
    card = world.client.get(f"/applications/{application['id']}", headers=headers).json()
    assert card["documents"] == []


def test_no_document_changes_after_submit(world: World) -> None:
    application = world.submit(world.ready())
    headers = world.headers(world.director)
    document_id = application["documents"][0]["id"]
    response = world.client.delete(
        f"/applications/{application['id']}/documents/{document_id}", headers=headers
    )
    assert response.status_code == 409
    announce = world.client.post(
        f"/applications/{application['id']}/documents",
        json={
            "type": "other",
            "filename": "x.pdf",
            "content_type": "application/pdf",
            "size_bytes": 10,
        },
        headers=headers,
    )
    assert announce.status_code == 409


def _announce(world: World, application: dict, content: bytes) -> str:
    document = world.client.post(
        f"/applications/{application['id']}/documents",
        json={
            "type": "bank_statement",
            "filename": "s.csv",
            "content_type": "text/csv",
            "size_bytes": len(content),
        },
        headers=world.headers(world.director),
    ).json()["document"]
    world.storage.put(f"applications/{application['id']}/{document['id']}", content, "text/csv")
    return f"/applications/{application['id']}/documents/{document['id']}/confirm"


@pytest.mark.parametrize(
    "content,line",
    [
        (b"date;amount\n2026-01-05;150000.00\n05.01.2026;1 500,00\n", 3),
        (b"date,amount\n2026-01-05,150000.00\n", 1),
        (b"day;sum\n2026-01-05;150000.00\n", 1),
        (b"date;amount\n", None),
    ],
)
def test_broken_statement_is_refused_with_the_line(
    world: World, content: bytes, line: int | None
) -> None:
    """The parser of the cash flow forecast reads the file on confirm: a file it cannot read
    is 422, the document still waits for a file."""
    application = world.create()
    response = world.client.post(
        _announce(world, application, content), headers=world.headers(world.director)
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["details"] == {"code": "statement_invalid", "line": line}
    assert body["message"]
    documents = world.client.get(
        f"/applications/{application['id']}", headers=world.headers(world.director)
    ).json()["documents"]
    assert [d["status"] for d in documents] == ["pending_upload"]
