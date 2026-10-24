"""Public part of the contracts: the rules of electronic interaction and the
check of a signed contract by its QR code or by the file. No login: the page
opens from a QR code on paper or in a PDF someone was sent."""

from uuid import UUID

from fastapi import APIRouter, UploadFile

from src.core.exceptions.exceptions import PayloadTooLargeError, ValidationError
from src.modules.applications.application.use_cases.contract_documents import esign_rules
from src.modules.applications.presentation.dependencies import (
    VerifyContractDep,
    VerifyContractFileDep,
)
from src.modules.applications.presentation.schemas.contracts import (
    ContractVerificationOut,
    EsignRulesOut,
    FileVerificationOut,
)

router = APIRouter(tags=["contracts"])

MAX_FILE_SIZE = 10 * 1024 * 1024


@router.get("/esign/rules", response_model=EsignRulesOut)
async def rules() -> EsignRulesOut:
    """Rules of electronic interaction: what the client accepts when it signs
    (`version` goes into `POST /applications/{id}/sign` as `rules_version`)."""
    return EsignRulesOut.model_validate(esign_rules())


@router.get("/contracts/verify/{document_id}", response_model=ContractVerificationOut)
async def verify(document_id: UUID, use_case: VerifyContractDep) -> ContractVerificationOut:
    """The document by the QR code: who signed it and when, whether the signing
    log is intact. 404 `document_not_found`."""
    return ContractVerificationOut.model_validate(await use_case.execute(document_id))


@router.post("/contracts/verify", response_model=FileVerificationOut)
async def verify_file(file: UploadFile, use_case: VerifyContractFileDep) -> FileVerificationOut:
    """A PDF someone has: the bank's signature intact and trusted, the file
    the same as the sealed copy in the archive. Up to 10 MB."""
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise PayloadTooLargeError("The file is over 10 MB", details={"code": "file_too_large"})
    if not content.startswith(b"%PDF-"):
        raise ValidationError("The file is not a PDF", details={"code": "not_a_pdf"})
    return FileVerificationOut.model_validate(await use_case.execute(content))
