"""The contract as PDF: the draft the client signs and the copy the bank seals.

A document is made when it is first needed — the contract screen, the download
or the signature — and kept in an archive that does not let it change. Each
step goes into the signing log of the contract.
"""

import asyncio
import hashlib
import logging
from dataclasses import replace
from datetime import datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import ConflictError, NotFoundError
from src.core.uow import UnitOfWork
from src.modules.applications.application.dto.contract_documents import (
    BankCertificateDTO,
    BankSealDTO,
    ClientSignatureDTO,
    ContractPrintDTO,
    ContractVerificationDTO,
    DocumentFileDTO,
    EsignRulesDTO,
    FileSignatureDTO,
    FileVerificationDTO,
    SigningEventDTO,
    VerifiedSignatureDTO,
)
from src.modules.applications.application.dto.views import ContractDocumentDTO, ContractDTO
from src.modules.applications.application.interfaces.contracts import (
    ContractArchive,
    ContractDocumentRepository,
    ContractRenderer,
    ContractSealer,
)
from src.modules.applications.application.interfaces.repositories import (
    ApplicationRepository,
    SignatureDetails,
)
from src.modules.applications.application.use_cases.contracts import (
    GetContractUseCase,
    ensure_contract,
)
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.contract_documents import (
    BankSeal,
    ContractDocument,
    ContractDocumentKind,
    SigningEvent,
    SigningEventKind,
    chain_is_intact,
    deal_uid,
)
from src.modules.applications.domain.esign_rules import (
    ESIGN_RULES,
    ESIGN_RULES_TITLE,
    ESIGN_RULES_VERSION,
)
from src.modules.applications.domain.value_objects import Signature
from src.modules.products.facade import ProductsFacade

BANK_ACTOR = "Банк, автоматически"
# The bank's key is issued by the demo CA of the stand, it is not a qualified one.
DEMO_KEY = True

logger = logging.getLogger(__name__)


def filename(number: str, kind: ContractDocumentKind) -> str:
    suffix = " (проект)" if kind is ContractDocumentKind.DRAFT else ""
    return f"Договор {number}{suffix}.pdf"


def short_name(full_name: str) -> str:
    """«Смирнова Анна Сергеевна» → «Смирнова А. С.»"""
    last, *rest = full_name.split()
    return " ".join([last, *(f"{part[0]}." for part in rest)])


class ContractDocuments:
    """Makes the documents of a contract when they are due and keeps them in the archive."""

    def __init__(
        self,
        uow: UnitOfWork,
        applications: ApplicationRepository,
        documents: ContractDocumentRepository,
        products: ProductsFacade,
        renderer: ContractRenderer,
        sealer: ContractSealer,
        archive: ContractArchive,
        clock: Clock,
        public_base_url: str,
    ) -> None:
        self._uow = uow
        self._applications = applications
        self._documents = documents
        self._products = products
        self._renderer = renderer
        self._sealer = sealer
        self._archive = archive
        self._clock = clock
        self._public_base_url = public_base_url.rstrip("/")

    def verify_url(self, document_id: UUID) -> str:
        return f"{self._public_base_url}/verify/{document_id}"

    def describe(self, number: str, document: ContractDocument) -> ContractDocumentDTO:
        return ContractDocumentDTO(
            id=document.id,
            kind=cast(Literal["draft", "signed"], document.kind.value),
            status="ready",
            sha256=document.sha256,
            created_at=document.created_at,
            filename=filename(number, document.kind),
            verify_url=self.verify_url(document.id)
            if document.kind is ContractDocumentKind.SIGNED
            else None,
        )

    async def current(
        self, application: CreditApplication, contract: ContractDTO
    ) -> ContractDocument:
        """The draft while the client has not signed, the sealed copy after."""
        if application.signature is None:
            return await self._draft(application, contract)
        return await self._sealed(application, contract, application.signature)

    async def _draft(
        self, application: CreditApplication, contract: ContractDTO
    ) -> ContractDocument:
        existing = await self._documents.for_offer(
            application.id, ContractDocumentKind.DRAFT, contract.offer_hash
        )
        if existing is not None:
            return existing
        document_id, now = uuid4(), self._clock.now()
        printed = await self._print(
            application, contract, document_id, ContractDocumentKind.DRAFT, now, None, None
        )
        pdf = await asyncio.to_thread(self._renderer.render, printed)
        return await self._store(
            application.id,
            contract.offer_hash,
            document_id,
            ContractDocumentKind.DRAFT,
            pdf,
            now,
            None,
            SigningEventKind.DRAFT_ISSUED,
            {"offer_hash": contract.offer_hash},
        )

    async def _sealed(
        self, application: CreditApplication, contract: ContractDTO, signature: Signature
    ) -> ContractDocument:
        existing = await self._documents.for_offer(
            application.id, ContractDocumentKind.SIGNED, contract.offer_hash
        )
        if existing is not None:
            return existing
        details = await self._applications.signature_details(application.id)
        client = client_signature(contract, signature, details)
        certificate = self._sealer.certificate()
        document_id, now = uuid4(), self._clock.now()
        planned = BankSealDTO(certificate.subject, certificate, now, None)
        printed = await self._print(
            application, contract, document_id, ContractDocumentKind.SIGNED, now, client, planned
        )
        pdf = await asyncio.to_thread(self._renderer.render, printed)
        sealed = await self._sealer.seal(pdf)
        seal = BankSeal(
            signer=certificate.subject,
            certificate_serial=certificate.serial,
            certificate_issuer=certificate.issuer,
            valid_from=certificate.valid_from,
            valid_to=certificate.valid_to,
            signed_at=sealed.signed_at,
            timestamp_at=sealed.timestamp_at,
        )
        return await self._store(
            application.id,
            contract.offer_hash,
            document_id,
            ContractDocumentKind.SIGNED,
            sealed.content,
            sealed.signed_at,
            seal,
            SigningEventKind.BANK_SEALED,
            {
                "certificate_serial": certificate.serial,
                "timestamp_at": sealed.timestamp_at.isoformat() if sealed.timestamp_at else None,
            },
        )

    async def _print(
        self,
        application: CreditApplication,
        contract: ContractDTO,
        document_id: UUID,
        kind: ContractDocumentKind,
        now: datetime,
        client: ClientSignatureDTO | None,
        seal: BankSealDTO | None,
    ) -> ContractPrintDTO:
        product = await self._products.get_product(application.product_code)
        events = [event_dto(event) for event in await self._documents.events(application.id)]
        if seal is not None:
            events.append(
                SigningEventDTO(
                    now,
                    SigningEventKind.BANK_SEALED.value,
                    BANK_ACTOR,
                    "Договор подписан усиленной электронной подписью Банка, "
                    f"сертификат {seal.certificate.serial}",
                    "",
                )
            )
        return ContractPrintDTO(
            document_id=document_id,
            kind=cast(Literal["draft", "signed"], kind.value),
            uid=deal_uid(application.id),
            verify_url=self.verify_url(document_id),
            contract=contract,
            product_name=product.name,
            purpose=application.request.purpose,
            issued_at=now,
            client_signature=client,
            bank_seal=seal,
            events=tuple(events),
        )

    async def _store(
        self,
        application_id: UUID,
        offer_hash: str,
        document_id: UUID,
        kind: ContractDocumentKind,
        pdf: bytes,
        at: datetime,
        seal: BankSeal | None,
        event_kind: SigningEventKind,
        event_details: dict[str, object],
    ) -> ContractDocument:
        sha256 = hashlib.sha256(pdf).hexdigest()
        document = ContractDocument(
            id=document_id,
            application_id=application_id,
            kind=kind,
            offer_hash=offer_hash,
            sha256=sha256,
            size=len(pdf),
            storage_key=f"{application_id}/{document_id}.pdf",
            created_at=at,
            seal=seal,
        )
        await self._archive.put(document.storage_key, pdf)
        try:
            async with self._uow:
                await self._documents.add(document)
                events = await self._documents.events(application_id)
                await self._documents.add_event(
                    SigningEvent.after(
                        events[-1] if events else None,
                        application_id,
                        at,
                        event_kind,
                        BANK_ACTOR,
                        {"document_id": str(document_id), "sha256": sha256, **event_details},
                    )
                )
                await self._uow.commit()
        except ConflictError:
            # Made by a parallel request a moment earlier: that one is the document.
            existing = await self._documents.for_offer(application_id, kind, offer_hash)
            if existing is None:
                raise
            return existing
        return document


def client_signature(
    contract: ContractDTO, signature: Signature, details: SignatureDetails | None
) -> ClientSignatureDTO:
    signer = next((s for s in contract.signers if s.account_id == signature.signed_by), None)
    authority = signer.authority if signer else "power_of_attorney"
    if str(contract.borrower.legal_form) == "IE":
        role = "индивидуальный предприниматель"
    elif authority == "registry":
        role = "генеральный директор"
    else:
        role = "представитель по доверенности"
    return ClientSignatureDTO(
        signer=signer.name if signer else "Представитель заёмщика",
        role=role,
        authority=authority,
        signed_at=signature.signed_at,
        ip=details.ip if details else None,
        method="password",
        rules_version=details.rules_version if details else None,
        document_hash=details.document_hash if details else None,
        edo_document_id=signature.edo_document_id or (details.edo_document_id if details else None),
    )


def event_dto(event: SigningEvent) -> SigningEventDTO:
    details = event.details
    if event.kind is SigningEventKind.DRAFT_ISSUED:
        text = f"Сформирован проект договора, SHA-256 {str(details.get('sha256', ''))[:16]}…"
    elif event.kind is SigningEventKind.CLIENT_SIGNED:
        text = "Договор подписан простой электронной подписью заёмщика"
        if details.get("document_hash"):
            text += f", проект SHA-256 {str(details['document_hash'])[:16]}…"
        if details.get("rules_version"):
            text += f", Правила ред. {details['rules_version']}"
    else:
        text = (
            "Договор подписан усиленной электронной подписью Банка, "
            f"сертификат {details.get('certificate_serial', '')}"
        )
    return SigningEventDTO(event.at, event.kind.value, event.actor, text, event.hash)


class GetContractViewUseCase:
    """The contract with its current PDF; a document that fails to be made
    does not hide the contract, it shows as `failed`."""

    def __init__(
        self,
        repository: ApplicationRepository,
        contracts: GetContractUseCase,
        documents: ContractDocuments,
    ) -> None:
        self._repository = repository
        self._contracts = contracts
        self._documents = documents

    async def execute(self, access: AccessContext, application_id: UUID) -> ContractDTO:
        application = await self._repository.get(application_id, access)
        ensure_contract(application)
        contract = await self._contracts.for_application(application)
        kind: Literal["draft", "signed"] = "draft" if application.signature is None else "signed"
        try:
            document = self._documents.describe(
                contract.number, await self._documents.current(application, contract)
            )
        except Exception:  # noqa: BLE001 — the contract itself must still open
            document = ContractDocumentDTO(None, kind, "failed", None, None, None, None)
        return replace(contract, uid=deal_uid(application.id), document=document)


class SealContractUseCase:
    """Right after the client's signature: the sealed copy with the bank's
    signature. Best effort — if it fails now, the contract screen makes it later."""

    def __init__(
        self,
        repository: ApplicationRepository,
        contracts: GetContractUseCase,
        documents: ContractDocuments,
    ) -> None:
        self._repository = repository
        self._contracts = contracts
        self._documents = documents

    async def execute(self, application_id: UUID) -> None:
        try:
            application = await self._repository.get(application_id)
            contract = await self._contracts.for_application(application)
            await self._documents.current(application, contract)
        except Exception:  # noqa: BLE001 — the signature is valid without the copy
            logger.exception("Sealed contract of %s is not made yet", application_id)


class DownloadContractDocumentUseCase:
    def __init__(
        self,
        repository: ApplicationRepository,
        contracts: GetContractUseCase,
        documents: ContractDocuments,
        store: ContractDocumentRepository,
        archive: ContractArchive,
    ) -> None:
        self._repository = repository
        self._contracts = contracts
        self._documents = documents
        self._store = store
        self._archive = archive

    async def execute(
        self, access: AccessContext, application_id: UUID, kind: ContractDocumentKind | None
    ) -> DocumentFileDTO:
        application = await self._repository.get(application_id, access)
        ensure_contract(application)
        contract = await self._contracts.for_application(application)
        document = await self._store.latest(application.id, kind)
        if document is None:
            # Not made yet (the contract screen was never opened): make the current one.
            await self._documents.current(application, contract)
            document = await self._store.latest(application.id, kind)
        if document is None:
            raise ConflictError(
                "The document is not ready yet", details={"code": "document_pending"}
            )
        content = await self._archive.read(document.storage_key)
        return DocumentFileDTO(
            content=content,
            filename=filename(contract.number, document.kind),
            kind=cast(Literal["draft", "signed"], document.kind.value),
            sha256=document.sha256,
        )


class VerifyContractDocumentUseCase:
    """The public page of the QR code: who signed the document and when."""

    def __init__(
        self,
        repository: ApplicationRepository,
        contracts: GetContractUseCase,
        store: ContractDocumentRepository,
    ) -> None:
        self._repository = repository
        self._contracts = contracts
        self._store = store

    async def execute(self, document_id: UUID) -> ContractVerificationDTO:
        document = await self._store.get(document_id)
        if document is None:
            raise NotFoundError(
                "No such document in the archive", details={"code": "document_not_found"}
            )
        application = await self._repository.get(document.application_id)
        contract = await self._contracts.for_application(application)
        signatures: list[VerifiedSignatureDTO] = []
        signature = application.signature
        if signature is not None and document.kind is ContractDocumentKind.SIGNED:
            details = await self._repository.signature_details(application.id)
            client = client_signature(contract, signature, details)
            signatures.append(
                VerifiedSignatureDTO(
                    party="client",
                    type="simple",
                    signer=short_name(client.signer),
                    role=client.role,
                    authority=client.authority,
                    signed_at=client.signed_at,
                    method="password",
                    rules_version=client.rules_version,
                    timestamp_at=None,
                    certificate=None,
                )
            )
        if document.seal is not None:
            seal = document.seal
            signatures.append(
                VerifiedSignatureDTO(
                    party="bank",
                    type="advanced",
                    signer=seal.signer,
                    role=None,
                    authority=None,
                    signed_at=seal.signed_at,
                    method="pades",
                    rules_version=None,
                    timestamp_at=seal.timestamp_at,
                    certificate=BankCertificateDTO(
                        subject=seal.signer,
                        serial=seal.certificate_serial,
                        issuer=seal.certificate_issuer,
                        valid_from=seal.valid_from,
                        valid_to=seal.valid_to,
                    ),
                )
            )
        return ContractVerificationDTO(
            document_id=document.id,
            number=contract.number,
            uid=deal_uid(application.id),
            kind=cast(Literal["draft", "signed"], document.kind.value),
            sha256=document.sha256,
            created_at=document.created_at,
            borrower=contract.borrower.name,
            signatures=tuple(signatures),
            log_intact=chain_is_intact(await self._store.events(application.id)),
            demo=DEMO_KEY,
        )


class VerifyContractFileUseCase:
    """A file someone has: is it the sealed copy from the archive, untouched."""

    def __init__(self, store: ContractDocumentRepository, sealer: ContractSealer) -> None:
        self._store = store
        self._sealer = sealer

    async def execute(self, content: bytes) -> FileVerificationDTO:
        document = await self._store.by_sha256(hashlib.sha256(content).hexdigest())
        check = await self._sealer.check(content)
        problems: list[str] = []
        if document is None:
            problems.append("not_in_archive")
        elif document.kind is ContractDocumentKind.DRAFT:
            problems.append("draft_not_signed")
        if not check.present:
            problems.append("no_signature")
        elif not check.intact:
            problems.append("signature_broken")
        elif not check.trusted:
            problems.append("untrusted_certificate")
        return FileVerificationDTO(
            valid=not problems,
            document_id=document.id if document else None,
            matches_archive=document is not None,
            signature=FileSignatureDTO(
                present=check.present,
                intact=check.intact,
                trusted=check.trusted,
                signer=check.signer,
                signed_at=check.signed_at,
                timestamp_at=check.timestamp_at,
            ),
            problems=tuple(problems),
        )


def esign_rules() -> EsignRulesDTO:
    return EsignRulesDTO(
        version=ESIGN_RULES_VERSION,
        title=ESIGN_RULES_TITLE,
        effective_from=ESIGN_RULES_VERSION,
        paragraphs=ESIGN_RULES,
    )
