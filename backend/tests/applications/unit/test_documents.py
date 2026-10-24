from typing import Any
from uuid import uuid4

import pytest

from src.core.exceptions.exceptions import ConflictError, NotFoundError, ValidationError
from src.modules.applications.domain.entities import MAX_DOCUMENT_SIZE
from src.modules.applications.domain.enums import ApplicationStatus, DocumentStatus
from tests.applications.unit.factories import APPLICANT_ID, NOW, draft, in_status

S = ApplicationStatus


def announce(application, **overrides: Any):  # type: ignore[no-untyped-def]
    values: dict[str, Any] = {
        "document_id": uuid4(),
        "document_type": "bank_statement",
        "filename": "../../etc/passwd.csv",
        "content_type": "text/csv",
        "size_bytes": 2048,
        "uploaded_by": APPLICANT_ID,
        "now": NOW,
    }
    values.update(overrides)
    return application.add_document(**values)


def test_announced_document_waits_for_upload() -> None:
    application = draft()
    document = announce(application)
    assert document.status is DocumentStatus.PENDING_UPLOAD
    # the key is built by the server, the client's file name never gets into it
    assert document.s3_key == f"applications/{application.id}/{document.id}"
    assert "passwd" not in document.s3_key
    assert application.uploaded_documents() == []


def test_confirmed_upload_counts() -> None:
    application = draft()
    document = announce(application)
    application.confirm_document(document.id, 2048, "text/csv", NOW)
    assert document.status is DocumentStatus.UPLOADED and document.uploaded_at == NOW
    assert application.uploaded_documents("bank_statement") == [document]


@pytest.mark.parametrize(
    "size,content_type", [(2047, "text/csv"), (2048, "application/pdf")], ids=["size", "type"]
)
def test_upload_must_match_the_announcement(size: int, content_type: str) -> None:
    application = draft()
    document = announce(application)
    with pytest.raises(ValidationError) as error:
        application.confirm_document(document.id, size, content_type, NOW)
    assert error.value.details == {"code": "upload_mismatch"}
    assert document.status is DocumentStatus.PENDING_UPLOAD


def test_confirm_twice() -> None:
    application = draft()
    document = announce(application)
    application.confirm_document(document.id, 2048, "text/csv", NOW)
    with pytest.raises(ConflictError):
        application.confirm_document(document.id, 2048, "text/csv", NOW)


def test_confirm_unknown_document() -> None:
    with pytest.raises(NotFoundError):
        draft().confirm_document(uuid4(), 1, "text/csv", NOW)


@pytest.mark.parametrize(
    "document_type,content_type,allowed",
    [
        ("bank_statement", "text/csv", True),
        ("bank_statement", "application/vnd.ms-excel", True),
        ("bank_statement", "application/pdf", False),
        ("financial_statement", "application/pdf", True),
        ("financial_statement", "image/png", True),
        ("financial_statement", "image/jpeg", True),
        ("financial_statement", "text/html", False),
        ("beneficiary_contract", "application/pdf", True),
        ("beneficiary_contract", "image/jpeg", True),
        ("beneficiary_contract", "image/png", True),
        ("beneficiary_contract", "text/csv", False),
        ("other", "application/x-msdownload", False),
    ],
)
def test_content_types(document_type: str, content_type: str, allowed: bool) -> None:
    application = draft()
    if allowed:
        announce(application, document_type=document_type, content_type=content_type)
    else:
        with pytest.raises(ValidationError) as error:
            announce(application, document_type=document_type, content_type=content_type)
        assert error.value.details["code"] == "content_type_not_allowed"


@pytest.mark.parametrize("size", [0, -1, MAX_DOCUMENT_SIZE + 1])
def test_size_limits(size: int) -> None:
    with pytest.raises(ValidationError) as error:
        announce(draft(), size_bytes=size)
    assert error.value.details["code"] == "bad_size"


def test_max_size_is_accepted() -> None:
    announce(draft(), size_bytes=MAX_DOCUMENT_SIZE)


@pytest.mark.parametrize("filename", ["", "   ", "a" * 256])
def test_filename(filename: str) -> None:
    with pytest.raises(ValidationError):
        announce(draft(), filename=filename)


def test_unexpected_document_type() -> None:
    with pytest.raises(ValidationError) as error:
        announce(draft(), document_type="passport", content_type="application/pdf")
    assert error.value.details["code"] == "unexpected_document"


@pytest.mark.parametrize(
    "status",
    [s for s in S if s not in (S.DRAFT, S.INFO_REQUESTED)],
    ids=lambda s: s.value,
)
def test_no_uploads_outside_draft_and_info_request(status: ApplicationStatus) -> None:
    with pytest.raises(ConflictError) as error:
        announce(in_status(status))
    assert error.value.details["code"] == "not_editable"


def test_remove_in_draft_only() -> None:
    application = draft()
    document = announce(application)
    application.remove_document(document.id, NOW)
    assert application.documents == []

    submitted = in_status(S.SUBMITTED)
    with pytest.raises(ConflictError):
        submitted.remove_document(submitted.documents[0].id, NOW)


def test_during_info_request_only_its_documents_are_removable() -> None:
    application = in_status(S.INFO_REQUESTED)
    original, attached = application.documents
    with pytest.raises(ConflictError):
        application.remove_document(original.id, NOW)
    application.remove_document(attached.id, NOW)
    assert application.documents == [original]
