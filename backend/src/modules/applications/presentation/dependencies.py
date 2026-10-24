"""Use cases for the router, the Kafka handlers, the offer expiry job and the
facade: adapters are picked here, use cases see only interfaces."""

from functools import partial
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.facades import FacadeRegistry, use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.messaging.outbox import SqlAlchemyOutboxWriter
from src.core.messaging.subscriber import HandlerContext
from src.core.uow import UnitOfWork
from src.modules.applications.application.interfaces.abs import AbsClient
from src.modules.applications.application.interfaces.contracts import (
    ContractArchive,
    ContractDocumentRepository,
    ContractRenderer,
    ContractSealer,
)
from src.modules.applications.application.interfaces.edo import EdoClient
from src.modules.applications.application.interfaces.outbox import MessageOutbox
from src.modules.applications.application.interfaces.repositories import ApplicationRepository
from src.modules.applications.application.interfaces.storage import DocumentStorage
from src.modules.applications.application.mappers.messages import PRODUCER
from src.modules.applications.application.use_cases.applications import (
    CheckCompletenessUseCase,
    GetApplicationUseCase,
    ListApplicationsUseCase,
)
from src.modules.applications.application.use_cases.cards import (
    GetCardUseCase,
    GetCompletenessUseCase,
    GetScoringInputUseCase,
    ListDocumentsUseCase,
    ListForOrganizationUseCase,
    ReadDocumentUseCase,
)
from src.modules.applications.application.use_cases.commands import (
    HandleCommandUseCase,
    SetClientStageUseCase,
)
from src.modules.applications.application.use_cases.contract_documents import (
    ContractDocuments,
    DownloadContractDocumentUseCase,
    GetContractViewUseCase,
    SealContractUseCase,
    VerifyContractDocumentUseCase,
    VerifyContractFileUseCase,
)
from src.modules.applications.application.use_cases.contracts import (
    GetContractUseCase,
    SignApplicationUseCase,
)
from src.modules.applications.application.use_cases.documents import (
    ConfirmUploadUseCase,
    DeleteDocumentUseCase,
    GetDownloadUrlUseCase,
    RequestUploadUseCase,
)
from src.modules.applications.application.use_cases.drafts import (
    CreateDraftUseCase,
    UpdateDraftUseCase,
)
from src.modules.applications.application.use_cases.expiry import ExpireOffersUseCase
from src.modules.applications.application.use_cases.offers import (
    AcceptOfferUseCase,
    DeclineOfferUseCase,
)
from src.modules.applications.application.use_cases.submission import (
    AnswerInfoRequestUseCase,
    CancelApplicationUseCase,
    SubmitApplicationUseCase,
)
from src.modules.applications.infrastructure.adapters.application_transaction import (
    SqlAlchemyApplicationTransaction,
)
from src.modules.applications.infrastructure.adapters.application_unit_of_work import (
    ApplicationUnitOfWork,
)
from src.modules.applications.infrastructure.adapters.applications_facade import (
    ApplicationsFacadeImpl,
)
from src.modules.applications.infrastructure.repositories.applications import (
    SqlAlchemyApplicationRepository,
)
from src.modules.applications.infrastructure.repositories.contract_documents import (
    SqlAlchemyContractDocumentRepository,
)
from src.modules.clients.facade import ClientsFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.products.facade import ProductsFacade

# --- facade --------------------------------------------------------------------


def applications_facade(
    session: AsyncSession, storage: DocumentStorage, facades: FacadeRegistry
) -> ApplicationsFacadeImpl:
    repository = SqlAlchemyApplicationRepository(session)
    return ApplicationsFacadeImpl(
        GetCardUseCase(repository),
        GetCompletenessUseCase(repository, facades.get(ClientsFacade, session)),
        GetScoringInputUseCase(repository),
        ListForOrganizationUseCase(repository),
        ListDocumentsUseCase(repository),
        ReadDocumentUseCase(repository, storage),
    )


# --- Kafka: the handler's transaction is committed by the core with the inbox ---


def handle_command_use_case(ctx: HandlerContext) -> HandleCommandUseCase:
    return HandleCommandUseCase(
        SqlAlchemyApplicationRepository(ctx.session),
        ctx.outbox,
        ctx.clock,
        ctx.facade(AbsClient),  # registered by applications.module.wire
    )


def set_client_stage_use_case(ctx: HandlerContext) -> SetClientStageUseCase:
    return SetClientStageUseCase(SqlAlchemyApplicationRepository(ctx.session), ctx.clock)


# --- the offer expiry job: a transaction of its own per application -----------


def expire_offers_use_case(
    session_factory: async_sessionmaker[AsyncSession], clock: Clock
) -> ExpireOffersUseCase:
    transactions = partial(SqlAlchemyApplicationTransaction, session_factory, clock)
    return ExpireOffersUseCase(transactions, clock)


# --- adapters for the router ---------------------------------------------------

CanRead = Annotated[AccessContext, Depends(get_access_context_for(Permissions.REQUESTS_READ))]
CanCreate = Annotated[AccessContext, Depends(get_access_context_for(Permissions.REQUESTS_CREATE))]
CanUpdate = Annotated[AccessContext, Depends(get_access_context_for(Permissions.REQUESTS_UPDATE))]


def client_ip(request: Request) -> str | None:
    # nginx puts the real address here; the backend itself is not exposed.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_uow(session: DbSession) -> UnitOfWork:
    return ApplicationUnitOfWork(session)


def get_repository(session: DbSession) -> ApplicationRepository:
    return SqlAlchemyApplicationRepository(session)


def get_outbox(request: Request, session: DbSession) -> MessageOutbox:
    return SqlAlchemyOutboxWriter(session, PRODUCER, request.app.state.clock)


def get_storage(request: Request) -> DocumentStorage:
    # Read per request: tests replace it with a fake after create_app().
    return request.app.state.document_storage


def get_edo(request: Request) -> EdoClient:
    return request.app.state.edo_client


def get_contract_documents_repository(session: DbSession) -> ContractDocumentRepository:
    return SqlAlchemyContractDocumentRepository(session)


def get_contract_archive(request: Request) -> ContractArchive:
    # Read per request: tests replace it with a fake after create_app().
    return request.app.state.contract_archive


def get_contract_renderer(request: Request) -> ContractRenderer:
    return request.app.state.contract_renderer


def get_contract_sealer(request: Request) -> ContractSealer:
    return request.app.state.contract_sealer


ClockDep = Annotated[Clock, Depends(get_clock)]
Uow = Annotated[UnitOfWork, Depends(get_uow)]
Repository = Annotated[ApplicationRepository, Depends(get_repository)]
Outbox = Annotated[MessageOutbox, Depends(get_outbox)]
Storage = Annotated[DocumentStorage, Depends(get_storage)]
Edo = Annotated[EdoClient, Depends(get_edo)]
Clients = Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))]
Products = Annotated[ProductsFacade, Depends(use_facade(ProductsFacade))]
Identity = Annotated[IdentityFacade, Depends(use_facade(IdentityFacade))]
ContractStore = Annotated[ContractDocumentRepository, Depends(get_contract_documents_repository)]
Archive = Annotated[ContractArchive, Depends(get_contract_archive)]
Sealer = Annotated[ContractSealer, Depends(get_contract_sealer)]
Renderer = Annotated[ContractRenderer, Depends(get_contract_renderer)]


# --- reading -------------------------------------------------------------------


def get_get_application(repository: Repository, clients: Clients) -> GetApplicationUseCase:
    return GetApplicationUseCase(repository, clients)


def get_list_applications(repository: Repository) -> ListApplicationsUseCase:
    return ListApplicationsUseCase(repository)


def get_check_completeness(repository: Repository, clients: Clients) -> CheckCompletenessUseCase:
    return CheckCompletenessUseCase(repository, clients)


def get_get_contract(
    repository: Repository, clients: Clients, products: Products, identity: Identity, edo: Edo
) -> GetContractUseCase:
    return GetContractUseCase(repository, clients, products, identity, edo)


def get_contract_documents(
    request: Request,
    uow: Uow,
    repository: Repository,
    store: ContractStore,
    products: Products,
    archive: Archive,
    sealer: Sealer,
    renderer: Renderer,
    clock: ClockDep,
) -> ContractDocuments:
    return ContractDocuments(
        uow,
        repository,
        store,
        products,
        renderer,
        sealer,
        archive,
        clock,
        request.app.state.public_base_url,
    )


Documents = Annotated[ContractDocuments, Depends(get_contract_documents)]
Contracts = Annotated[GetContractUseCase, Depends(get_get_contract)]


def get_contract_view(
    repository: Repository, contracts: Contracts, documents: Documents
) -> GetContractViewUseCase:
    return GetContractViewUseCase(repository, contracts, documents)


def get_download_contract(
    repository: Repository,
    contracts: Contracts,
    documents: Documents,
    store: ContractStore,
    archive: Archive,
) -> DownloadContractDocumentUseCase:
    return DownloadContractDocumentUseCase(repository, contracts, documents, store, archive)


def get_seal_contract(
    repository: Repository, contracts: Contracts, documents: Documents
) -> SealContractUseCase:
    return SealContractUseCase(repository, contracts, documents)


def get_verify_contract(
    repository: Repository, contracts: Contracts, store: ContractStore
) -> VerifyContractDocumentUseCase:
    return VerifyContractDocumentUseCase(repository, contracts, store)


def get_verify_contract_file(store: ContractStore, sealer: Sealer) -> VerifyContractFileUseCase:
    return VerifyContractFileUseCase(store, sealer)


def get_download_url(repository: Repository, storage: Storage) -> GetDownloadUrlUseCase:
    return GetDownloadUrlUseCase(repository, storage)


# --- draft ---------------------------------------------------------------------


def get_create_draft(
    uow: Uow,
    repository: Repository,
    outbox: Outbox,
    clients: Clients,
    products: Products,
    identity: Identity,
    clock: ClockDep,
) -> CreateDraftUseCase:
    return CreateDraftUseCase(uow, repository, outbox, clients, products, identity, clock)


def get_update_draft(
    uow: Uow, repository: Repository, outbox: Outbox, clients: Clients, clock: ClockDep
) -> UpdateDraftUseCase:
    return UpdateDraftUseCase(uow, repository, outbox, clients, clock)


# --- documents -----------------------------------------------------------------


def get_request_upload(
    uow: Uow,
    repository: Repository,
    outbox: Outbox,
    clients: Clients,
    storage: Storage,
    clock: ClockDep,
) -> RequestUploadUseCase:
    return RequestUploadUseCase(uow, repository, outbox, clients, storage, clock)


def get_confirm_upload(
    uow: Uow,
    repository: Repository,
    outbox: Outbox,
    clients: Clients,
    storage: Storage,
    clock: ClockDep,
) -> ConfirmUploadUseCase:
    return ConfirmUploadUseCase(uow, repository, outbox, clients, storage, clock)


def get_delete_document(
    uow: Uow,
    repository: Repository,
    outbox: Outbox,
    clients: Clients,
    storage: Storage,
    clock: ClockDep,
) -> DeleteDocumentUseCase:
    return DeleteDocumentUseCase(uow, repository, outbox, clients, storage, clock)


# --- submission, answers and the offer -----------------------------------------


def get_submit(
    uow: Uow,
    repository: Repository,
    outbox: Outbox,
    clients: Clients,
    identity: Identity,
    clock: ClockDep,
) -> SubmitApplicationUseCase:
    return SubmitApplicationUseCase(uow, repository, outbox, clients, identity, clock)


def get_answer_info_request(
    uow: Uow, repository: Repository, outbox: Outbox, clients: Clients, clock: ClockDep
) -> AnswerInfoRequestUseCase:
    return AnswerInfoRequestUseCase(uow, repository, outbox, clients, clock)


def get_accept_offer(
    uow: Uow, repository: Repository, outbox: Outbox, clients: Clients, clock: ClockDep
) -> AcceptOfferUseCase:
    return AcceptOfferUseCase(uow, repository, outbox, clients, clock)


def get_decline_offer(
    uow: Uow, repository: Repository, outbox: Outbox, clients: Clients, clock: ClockDep
) -> DeclineOfferUseCase:
    return DeclineOfferUseCase(uow, repository, outbox, clients, clock)


def get_sign(
    uow: Uow,
    repository: Repository,
    outbox: Outbox,
    clients: Clients,
    identity: Identity,
    edo: Edo,
    clock: ClockDep,
    store: ContractStore,
) -> SignApplicationUseCase:
    return SignApplicationUseCase(uow, repository, outbox, clients, identity, edo, clock, store)


def get_cancel(
    uow: Uow, repository: Repository, outbox: Outbox, clients: Clients, clock: ClockDep
) -> CancelApplicationUseCase:
    return CancelApplicationUseCase(uow, repository, outbox, clients, clock)


GetApplicationDep = Annotated[GetApplicationUseCase, Depends(get_get_application)]
ListApplicationsDep = Annotated[ListApplicationsUseCase, Depends(get_list_applications)]
CheckCompletenessDep = Annotated[CheckCompletenessUseCase, Depends(get_check_completeness)]
GetContractDep = Annotated[GetContractUseCase, Depends(get_get_contract)]
DownloadUrlDep = Annotated[GetDownloadUrlUseCase, Depends(get_download_url)]
CreateDraftDep = Annotated[CreateDraftUseCase, Depends(get_create_draft)]
UpdateDraftDep = Annotated[UpdateDraftUseCase, Depends(get_update_draft)]
RequestUploadDep = Annotated[RequestUploadUseCase, Depends(get_request_upload)]
ConfirmUploadDep = Annotated[ConfirmUploadUseCase, Depends(get_confirm_upload)]
DeleteDocumentDep = Annotated[DeleteDocumentUseCase, Depends(get_delete_document)]
SubmitDep = Annotated[SubmitApplicationUseCase, Depends(get_submit)]
AnswerInfoRequestDep = Annotated[AnswerInfoRequestUseCase, Depends(get_answer_info_request)]
AcceptOfferDep = Annotated[AcceptOfferUseCase, Depends(get_accept_offer)]
DeclineOfferDep = Annotated[DeclineOfferUseCase, Depends(get_decline_offer)]
SignDep = Annotated[SignApplicationUseCase, Depends(get_sign)]
ContractViewDep = Annotated[GetContractViewUseCase, Depends(get_contract_view)]
DownloadContractDep = Annotated[DownloadContractDocumentUseCase, Depends(get_download_contract)]
SealContractDep = Annotated[SealContractUseCase, Depends(get_seal_contract)]
VerifyContractDep = Annotated[VerifyContractDocumentUseCase, Depends(get_verify_contract)]
VerifyContractFileDep = Annotated[VerifyContractFileUseCase, Depends(get_verify_contract_file)]
CancelDep = Annotated[CancelApplicationUseCase, Depends(get_cancel)]
