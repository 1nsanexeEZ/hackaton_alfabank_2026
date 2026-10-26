from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_access_context
from src.core.exceptions.exceptions import NotFoundError
from src.modules.applications.application.interfaces.repositories import (
    ApplicationRepository,
    SignatureDetails,
)
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.enums import ApplicationStatus
from src.modules.applications.domain.statuses import FINAL_STATUSES
from src.modules.applications.domain.value_objects import ApplicationNumber, DecidedBy
from src.modules.applications.infrastructure.database.models import (
    NUMBER_SEQUENCE,
    ApplicationRecord,
    SignatureRecord,
)
from src.modules.applications.infrastructure.repositories.mappers import (
    apply,
    new_record,
    to_domain,
)

_FINAL = [status.value for status in FINAL_STATUSES]


def _filtered[S: Select[Any]](
    stmt: S,
    access: AccessContext | None,
    organization_id: UUID | None,
    statuses: Sequence[str] | None,
    decided_by: DecidedBy | None,
) -> S:
    if access is not None:
        stmt = apply_access_context(stmt, ApplicationRecord, access)  # type: ignore[assignment]
    if organization_id is not None:
        stmt = stmt.where(ApplicationRecord.organization_id == organization_id)
    if statuses:
        stmt = stmt.where(ApplicationRecord.status.in_(list(statuses)))
    if decided_by is not None:
        stmt = stmt.where(ApplicationRecord.decided_by == decided_by)
    return stmt


class SqlAlchemyApplicationRepository(ApplicationRepository):
    """Keeps the rows it loaded, so `save` updates them in place and the
    `version` column guards against a concurrent writer."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._records: dict[UUID, ApplicationRecord] = {}

    async def next_number(self, year: int) -> ApplicationNumber:
        if self._session.bind.dialect.name == "postgresql":
            sequence = await self._session.scalar(select(NUMBER_SEQUENCE.next_value()))
        else:  # tests on SQLite: no sequences, no concurrency
            count = await self._session.scalar(select(func.count()).select_from(ApplicationRecord))
            sequence = (count or 0) + 1
        return ApplicationNumber.issue(year, int(sequence or 0))

    async def add(self, application: CreditApplication) -> None:
        record = new_record(application)
        self._session.add(record)
        await self._session.flush()
        self._remember(application, record)

    async def get(
        self, application_id: UUID, access: AccessContext | None = None
    ) -> CreditApplication:
        stmt = select(ApplicationRecord).where(ApplicationRecord.id == application_id)
        if access is not None:
            stmt = apply_access_context(stmt, ApplicationRecord, access)
        record = (await self._session.scalars(stmt)).one_or_none()
        if record is None:
            raise NotFoundError("Application not found")
        application = to_domain(record)
        self._records[application.id] = record
        return application

    async def save(self, application: CreditApplication) -> None:
        record = self._records.get(application.id)
        if record is None:
            raise RuntimeError("Save only an application loaded by this repository")
        apply(application, record)
        await self._session.flush()
        self._remember(application, record)

    async def find_active(
        self, organization_id: UUID, product_code: str, exclude_id: UUID | None = None
    ) -> UUID | None:
        stmt = select(ApplicationRecord.id).where(
            ApplicationRecord.organization_id == organization_id,
            ApplicationRecord.product_code == product_code,
            ApplicationRecord.status.not_in(_FINAL),
        )
        if exclude_id is not None:
            stmt = stmt.where(ApplicationRecord.id != exclude_id)
        return (await self._session.scalars(stmt.limit(1))).first()

    async def search(
        self,
        access: AccessContext | None,
        organization_id: UUID | None,
        statuses: Sequence[str] | None,
        limit: int,
        offset: int,
        decided_by: DecidedBy | None = None,
    ) -> list[CreditApplication]:
        stmt = _filtered(select(ApplicationRecord), access, organization_id, statuses, decided_by)
        stmt = stmt.order_by(ApplicationRecord.updated_at.desc(), ApplicationRecord.id)
        records = (await self._session.scalars(stmt.limit(limit).offset(offset))).all()
        return [to_domain(record) for record in records]

    async def count(
        self,
        access: AccessContext | None,
        organization_id: UUID | None,
        statuses: Sequence[str] | None,
        decided_by: DecidedBy | None = None,
    ) -> int:
        stmt = _filtered(
            select(func.count(ApplicationRecord.id)).select_from(ApplicationRecord),
            access,
            organization_id,
            statuses,
            decided_by,
        )
        return int(await self._session.scalar(stmt) or 0)

    async def set_client_stage(
        self, application_id: UUID, client_stage: str, now: datetime
    ) -> bool:
        # Core UPDATE: the ORM version column is not bumped, so the label never
        # makes a concurrent command or a client action retry.
        stmt = (
            update(ApplicationRecord)
            .where(
                ApplicationRecord.id == application_id,
                ApplicationRecord.status.not_in(_FINAL),
                ApplicationRecord.client_stage.is_distinct_from(client_stage),
            )
            .values(client_stage=client_stage, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)

    async def offers_expired_by(self, moment: datetime, limit: int) -> list[UUID]:
        stmt = (
            select(ApplicationRecord.id)
            .where(
                ApplicationRecord.status == ApplicationStatus.OFFER_READY.value,
                ApplicationRecord.offer_expires_at <= moment,
            )
            .order_by(ApplicationRecord.offer_expires_at)
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

    async def record_signature_details(
        self,
        application_id: UUID,
        ip: str | None,
        user_agent: str | None,
        edo_document_id: str | None,
        document_hash: str | None = None,
        rules_version: str | None = None,
    ) -> None:
        signature = self._records[application_id].signature
        if signature is None:
            raise RuntimeError("Application is not signed")
        signature.ip = ip[:64] if ip else None
        signature.user_agent = user_agent[:512] if user_agent else None
        signature.edo_document_id = edo_document_id
        signature.document_hash = document_hash
        signature.rules_version = rules_version
        await self._session.flush()

    async def signature_details(self, application_id: UUID) -> SignatureDetails | None:
        row = await self._session.get(SignatureRecord, application_id)
        if row is None:
            return None
        return SignatureDetails(
            ip=row.ip,
            user_agent=row.user_agent,
            edo_document_id=row.edo_document_id,
            document_hash=row.document_hash,
            rules_version=row.rules_version,
        )

    def _remember(self, application: CreditApplication, record: ApplicationRecord) -> None:
        self._records[application.id] = record
        application.version = record.version
