from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.applications.application.interfaces.contracts import ContractDocumentRepository
from src.modules.applications.domain.contract_documents import (
    BankSeal,
    ContractDocument,
    ContractDocumentKind,
    SigningEvent,
    SigningEventKind,
)
from src.modules.applications.infrastructure.database.models import (
    ContractDocumentRecord,
    ContractEventRecord,
)


class SqlAlchemyContractDocumentRepository(ContractDocumentRepository):
    """Rows are only added: a document or a log entry never changes after it is written."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest(
        self, application_id: UUID, kind: ContractDocumentKind | None = None
    ) -> ContractDocument | None:
        query = select(ContractDocumentRecord).where(
            ContractDocumentRecord.application_id == application_id
        )
        if kind is not None:
            query = query.where(ContractDocumentRecord.kind == kind.value)
        query = query.order_by(ContractDocumentRecord.created_at.desc()).limit(1)
        row = await self._session.scalar(query)
        return _document(row) if row else None

    async def for_offer(
        self, application_id: UUID, kind: ContractDocumentKind, offer_hash: str
    ) -> ContractDocument | None:
        row = await self._session.scalar(
            select(ContractDocumentRecord).where(
                ContractDocumentRecord.application_id == application_id,
                ContractDocumentRecord.kind == kind.value,
                ContractDocumentRecord.offer_hash == offer_hash,
            )
        )
        return _document(row) if row else None

    async def get(self, document_id: UUID) -> ContractDocument | None:
        row = await self._session.get(ContractDocumentRecord, document_id)
        return _document(row) if row else None

    async def by_sha256(self, sha256: str) -> ContractDocument | None:
        row = await self._session.scalar(
            select(ContractDocumentRecord).where(ContractDocumentRecord.sha256 == sha256)
        )
        return _document(row) if row else None

    async def add(self, document: ContractDocument) -> None:
        self._session.add(
            ContractDocumentRecord(
                id=document.id,
                application_id=document.application_id,
                kind=document.kind.value,
                offer_hash=document.offer_hash,
                sha256=document.sha256,
                size=document.size,
                storage_key=document.storage_key,
                created_at=document.created_at,
                seal=_seal_out(document.seal) if document.seal else None,
            )
        )
        await self._session.flush()

    async def events(self, application_id: UUID) -> list[SigningEvent]:
        rows = await self._session.scalars(
            select(ContractEventRecord)
            .where(ContractEventRecord.application_id == application_id)
            .order_by(ContractEventRecord.seq)
        )
        return [
            SigningEvent(
                application_id=row.application_id,
                seq=row.seq,
                at=row.at,
                kind=SigningEventKind(row.kind),
                actor=row.actor,
                details=row.details,
                prev_hash=row.prev_hash,
                hash=row.hash,
            )
            for row in rows
        ]

    async def add_event(self, event: SigningEvent) -> None:
        self._session.add(
            ContractEventRecord(
                application_id=event.application_id,
                seq=event.seq,
                at=event.at,
                kind=event.kind.value,
                actor=event.actor,
                details=event.details,
                prev_hash=event.prev_hash,
                hash=event.hash,
            )
        )
        await self._session.flush()


def _document(row: ContractDocumentRecord) -> ContractDocument:
    return ContractDocument(
        id=row.id,
        application_id=row.application_id,
        kind=ContractDocumentKind(row.kind),
        offer_hash=row.offer_hash,
        sha256=row.sha256,
        size=row.size,
        storage_key=row.storage_key,
        created_at=row.created_at,
        seal=_seal_in(row.seal) if row.seal else None,
    )


def _seal_out(seal: BankSeal) -> dict[str, Any]:
    return {
        "signer": seal.signer,
        "certificate_serial": seal.certificate_serial,
        "certificate_issuer": seal.certificate_issuer,
        "valid_from": seal.valid_from.isoformat(),
        "valid_to": seal.valid_to.isoformat(),
        "signed_at": seal.signed_at.isoformat(),
        "timestamp_at": seal.timestamp_at.isoformat() if seal.timestamp_at else None,
    }


def _seal_in(data: dict[str, Any]) -> BankSeal:
    timestamp = data.get("timestamp_at")
    return BankSeal(
        signer=data["signer"],
        certificate_serial=data["certificate_serial"],
        certificate_issuer=data["certificate_issuer"],
        valid_from=datetime.fromisoformat(data["valid_from"]),
        valid_to=datetime.fromisoformat(data["valid_to"]),
        signed_at=datetime.fromisoformat(data["signed_at"]),
        timestamp_at=datetime.fromisoformat(timestamp) if timestamp else None,
    )
