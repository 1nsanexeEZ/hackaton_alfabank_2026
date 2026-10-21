from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.applications.domain.application import CreditApplication
from src.applications.domain.statuses import FINAL_STATUSES
from src.applications.domain.value_objects import ApplicationNumber
from src.applications.infrastructure.mappers import apply, new_record, to_domain
from src.applications.infrastructure.models import NUMBER_SEQUENCE, ApplicationRecord
from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_access_context
from src.core.exceptions.exceptions import NotFoundError

_FINAL = [status.value for status in FINAL_STATUSES]


class SqlAlchemyApplicationRepository:
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
    ) -> list[CreditApplication]:
        stmt = select(ApplicationRecord)
        if access is not None:
            stmt = apply_access_context(stmt, ApplicationRecord, access)
        if organization_id is not None:
            stmt = stmt.where(ApplicationRecord.organization_id == organization_id)
        if statuses:
            stmt = stmt.where(ApplicationRecord.status.in_(list(statuses)))
        stmt = stmt.order_by(ApplicationRecord.updated_at.desc(), ApplicationRecord.id)
        records = (await self._session.scalars(stmt.limit(limit).offset(offset))).all()
        return [to_domain(record) for record in records]

    async def record_signature_details(
        self,
        application_id: UUID,
        ip: str | None,
        user_agent: str | None,
        edo_document_id: str | None,
    ) -> None:
        signature = self._records[application_id].signature
        if signature is None:
            raise RuntimeError("Application is not signed")
        signature.ip = ip[:64] if ip else None
        signature.user_agent = user_agent[:512] if user_agent else None
        signature.edo_document_id = edo_document_id
        await self._session.flush()

    def _remember(self, application: CreditApplication, record: ApplicationRecord) -> None:
        self._records[application.id] = record
        application.version = record.version
