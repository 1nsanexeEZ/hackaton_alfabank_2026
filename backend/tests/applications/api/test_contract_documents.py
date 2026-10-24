import hashlib
from typing import Any
from uuid import UUID, uuid4

from src.modules.applications.infrastructure.database.models import SignatureRecord
from tests.applications.api.conftest import PASSWORD, World
from tests.applications.api.test_submit_and_sign import to_offer


def signing(world: World) -> str:
    """An application whose offer the director has just accepted."""
    application = world.submit(world.ready())
    to_offer(world, application["id"])
    accepted = world.client.post(
        f"/applications/{application['id']}/offer/accept", headers=world.headers(world.director)
    )
    assert accepted.status_code == 200, accepted.text
    return application["id"]


def contract(world: World, application_id: str) -> dict[str, Any]:
    response = world.client.get(
        f"/applications/{application_id}/contract", headers=world.headers(world.director)
    )
    assert response.status_code == 200, response.text
    return response.json()


def download(world: World, application_id: str, kind: str | None = None) -> bytes:
    response = world.client.get(
        f"/applications/{application_id}/contract/document",
        params={"kind": kind} if kind else None,
        headers=world.headers(world.director),
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment; filename*=UTF-8''")
    return response.content


def sign(world: World, application_id: str, **fields: Any) -> Any:
    seen = contract(world, application_id)
    rules = world.client.get("/esign/rules").json()
    body = {
        "password": PASSWORD,
        "offer_hash": seen["offer_hash"],
        "document_hash": seen["document"]["sha256"],
        "rules_version": rules["version"],
        **fields,
    }
    return world.client.post(
        f"/applications/{application_id}/sign",
        json=body,
        headers={**world.headers(world.director), "X-Real-IP": "203.0.113.7"},
    )


def test_the_contract_comes_with_its_draft_pdf(world: World) -> None:
    application_id = signing(world)

    body = contract(world, application_id)

    draft = body["document"]
    assert draft["kind"] == "draft" and draft["status"] == "ready"
    assert draft["verify_url"] is None
    assert draft["filename"] == f"Договор {body['number']} (проект).pdf"
    assert body["uid"].startswith(application_id) and len(body["uid"]) == 38
    pdf = download(world, application_id)
    assert pdf.startswith(b"%PDF-")
    assert hashlib.sha256(pdf).hexdigest() == draft["sha256"]
    # the same draft on the next look: the archive keeps one per offer
    assert contract(world, application_id)["document"]["id"] == draft["id"]


def test_signing_seals_the_contract_and_anyone_can_check_it(world: World) -> None:
    application_id = signing(world)
    draft = contract(world, application_id)["document"]

    signed = sign(world, application_id)

    assert signed.status_code == 200, signed.text
    document = contract(world, application_id)["document"]
    assert document["kind"] == "signed" and document["status"] == "ready"
    assert document["verify_url"].endswith(f"/verify/{document['id']}")
    pdf = download(world, application_id)
    assert hashlib.sha256(pdf).hexdigest() == document["sha256"]
    assert hashlib.sha256(download(world, application_id, "draft")).hexdigest() == draft["sha256"]

    check = world.client.get(f"/contracts/verify/{document['id']}")  # no login
    assert check.status_code == 200, check.text
    page = check.json()
    assert page["kind"] == "signed" and page["log_intact"] is True and page["demo"] is True
    client, bank = page["signatures"]
    assert client["party"] == "client" and client["type"] == "simple"
    assert client["rules_version"] and client["signer"] and client["authority"]
    assert bank["party"] == "bank" and bank["type"] == "advanced"
    assert bank["timestamp_at"] and bank["certificate"]["issuer"]

    async def stored() -> SignatureRecord | None:
        async with world.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
            return await session.get(SignatureRecord, UUID(application_id))

    record = world.run(stored)
    assert record is not None
    assert (
        record.document_hash == draft["sha256"] and record.rules_version == client["rules_version"]
    )


def test_a_file_is_checked_against_the_archive_and_the_signature(world: World) -> None:
    application_id = signing(world)
    draft_pdf = download(world, application_id)
    assert sign(world, application_id).status_code == 200
    sealed = download(world, application_id, "signed")

    def check(content: bytes) -> dict[str, Any]:
        response = world.client.post(
            "/contracts/verify", files={"file": ("contract.pdf", content, "application/pdf")}
        )
        assert response.status_code == 200, response.text
        return response.json()

    good = check(sealed)
    assert good["valid"] is True and good["matches_archive"] is True and good["problems"] == []
    assert good["signature"]["intact"] and good["signature"]["trusted"]

    assert check(draft_pdf)["problems"] == ["draft_not_signed", "no_signature"]

    tampered = bytearray(sealed)
    tampered[len(sealed) // 3] ^= 0x01
    bad = check(bytes(tampered))
    assert bad["valid"] is False and "not_in_archive" in bad["problems"]

    not_pdf = world.client.post(
        "/contracts/verify", files={"file": ("x.pdf", b"hello", "application/pdf")}
    )
    assert not_pdf.status_code == 422 and not_pdf.json()["details"] == {"code": "not_a_pdf"}


def test_a_changed_draft_or_old_rules_are_not_signed(world: World) -> None:
    application_id = signing(world)

    changed = sign(world, application_id, document_hash="0" * 64)
    old_rules = sign(world, application_id, rules_version="2000-01-01")

    assert changed.status_code == 422 and changed.json()["details"]["code"] == "document_changed"
    assert old_rules.status_code == 422 and old_rules.json()["details"]["code"] == "rules_outdated"
    assert contract(world, application_id)["status"] == "unsigned"


def test_rules_of_electronic_interaction_are_public(world: World) -> None:
    rules = world.client.get("/esign/rules")

    assert rules.status_code == 200
    body = rules.json()
    assert body["version"] and body["paragraphs"]
    assert any("63-ФЗ" in paragraph for paragraph in body["paragraphs"])


def test_unknown_document_and_early_download(world: World) -> None:
    missing = world.client.get(f"/contracts/verify/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["details"] == {"code": "document_not_found"}

    application = world.submit(world.ready())
    early = world.client.get(
        f"/applications/{application['id']}/contract/document",
        headers=world.headers(world.director),
    )
    assert early.status_code == 409
    assert early.json()["details"] == {"code": "contract_not_ready"}
