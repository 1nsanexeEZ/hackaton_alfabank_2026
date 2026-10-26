"""Documents of an application. The browser uploads and downloads by presigned
URLs, the backend never streams the bytes."""

from uuid import UUID, uuid4

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import InfrastructureError, NotFoundError, ValidationError
from src.core.uow import UnitOfWork
from src.modules.applications.application.dto.applications import DocumentDTO
from src.modules.applications.application.dto.views import DocumentUploadDTO
from src.modules.applications.application.interfaces.outbox import MessageOutbox
from src.modules.applications.application.interfaces.repositories import ApplicationRepository
from src.modules.applications.application.interfaces.storage import DocumentStorage
from src.modules.applications.application.mappers.dto import document_dto
from src.modules.applications.application.use_cases.common import get_writable, save
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.enrichment.facade import EnrichmentFacade

UPLOAD_URL_TTL_SECONDS = 300
DOWNLOAD_URL_TTL_SECONDS = 60


# The document the cash flow forecast reads; its file is checked on confirm.
STATEMENT = "bank_statement"


class RequestUploadUseCase:
    """Announce a file and get a presigned URL: the browser PUTs it straight
    to the storage, then confirms."""

    def __init__(
        self,
        uow: UnitOfWork,
        repository: ApplicationRepository,
        outbox: MessageOutbox,
        clients: ClientsFacade,
        storage: DocumentStorage,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clients = clients
        self._storage = storage
        self._clock = clock

    async def execute(
        self,
        access: AccessContext,
        application_id: UUID,
        document_type: str,
        filename: str,
        content_type: str,
        size_bytes: int,
    ) -> DocumentUploadDTO:
        application = await get_writable(
            self._repository,
            self._clients,
            access,
            application_id,
            OrgPermission.SUBMIT_APPLICATION,
        )
        document = application.add_document(
            document_id=uuid4(),
            document_type=document_type,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            uploaded_by=access.user_id,
            now=self._clock.now(),
        )
        upload = await self._storage.presign_upload(
            document.s3_key, content_type, size_bytes, UPLOAD_URL_TTL_SECONDS
        )
        await save(self._uow, self._repository, self._outbox, application)
        return DocumentUploadDTO(document_dto(document), upload)


class ConfirmUploadUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repository: ApplicationRepository,
        outbox: MessageOutbox,
        clients: ClientsFacade,
        storage: DocumentStorage,
        clock: Clock,
        enrichment: EnrichmentFacade | None = None,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clients = clients
        self._storage = storage
        self._clock = clock
        self._enrichment = enrichment

    async def execute(
        self, access: AccessContext, application_id: UUID, document_id: UUID
    ) -> DocumentDTO:
        """A bank statement is checked by the parser of the cash flow forecast: a file it
        cannot read is 422 `statement_invalid` with the line, the document stays waiting
        for a file."""
        application = await get_writable(
            self._repository,
            self._clients,
            access,
            application_id,
            OrgPermission.SUBMIT_APPLICATION,
        )
        document = application.document(document_id)
        stored = await self._storage.head(document.s3_key)
        if stored is None:
            raise ValidationError(
                "The file has not reached the storage yet", details={"code": "upload_missing"}
            )
        application.confirm_document(
            document_id, stored.size, stored.content_type, self._clock.now()
        )
        # After the size and type: a wrong file is `upload_mismatch`, not a bad statement.
        if document.type == STATEMENT and self._enrichment is not None:
            check = self._enrichment.check_statement(await self._storage.read(document.s3_key))
            if not check.valid:
                raise ValidationError(
                    check.message or "The bank statement cannot be read",
                    details={"code": "statement_invalid", "line": check.line},
                )
        await save(self._uow, self._repository, self._outbox, application)
        return document_dto(document)


class DeleteDocumentUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repository: ApplicationRepository,
        outbox: MessageOutbox,
        clients: ClientsFacade,
        storage: DocumentStorage,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clients = clients
        self._storage = storage
        self._clock = clock

    async def execute(self, access: AccessContext, application_id: UUID, document_id: UUID) -> None:
        application = await get_writable(
            self._repository,
            self._clients,
            access,
            application_id,
            OrgPermission.SUBMIT_APPLICATION,
        )
        document = application.remove_document(document_id, self._clock.now())
        await save(self._uow, self._repository, self._outbox, application)
        try:
            await self._storage.delete(document.s3_key)
        except InfrastructureError:
            pass  # an orphan object in a private bucket is harmless


class GetDownloadUrlUseCase:
    def __init__(self, repository: ApplicationRepository, storage: DocumentStorage) -> None:
        self._repository = repository
        self._storage = storage

    async def execute(self, access: AccessContext, application_id: UUID, document_id: UUID) -> str:
        application = await self._repository.get(application_id, access)
        document = application.document(document_id)
        if not document.is_uploaded:
            raise NotFoundError("Document is not uploaded yet")
        return await self._storage.presign_download(
            document.s3_key, document.filename, DOWNLOAD_URL_TTL_SECONDS
        )
