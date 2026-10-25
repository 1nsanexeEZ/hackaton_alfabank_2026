from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.market.application.interfaces.repositories import KeyRateRepository
from src.modules.market.domain.enums import RateSource
from src.modules.market.domain.key_rate import KeyRate
from src.modules.market.infrastructure.database.models import KeyRateRecord


def _to_domain(record: KeyRateRecord) -> KeyRate:
    return KeyRate(
        effective_from=record.effective_from,
        value=Decimal(str(record.value)),
        source=RateSource(record.source),
        decided_on=record.decided_on,
        note=record.note,
        created_by=record.created_by,
        created_at=record.created_at,
        announced_at=record.announced_at,
    )


class SqlAlchemyKeyRateRepository(KeyRateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def on(self, day: date) -> KeyRate | None:
        stmt = (
            select(KeyRateRecord)
            .where(KeyRateRecord.effective_from <= day)
            .order_by(KeyRateRecord.effective_from.desc())
            .limit(1)
        )
        record = (await self._session.scalars(stmt)).one_or_none()
        return None if record is None else _to_domain(record)

    async def get(self, effective_from: date) -> KeyRate | None:
        record = await self._session.get(KeyRateRecord, effective_from)
        return None if record is None else _to_domain(record)

    async def list_all(self) -> list[KeyRate]:
        stmt = select(KeyRateRecord).order_by(KeyRateRecord.effective_from.desc())
        return [_to_domain(record) for record in await self._session.scalars(stmt)]

    async def add(self, rate: KeyRate) -> None:
        self._session.add(
            KeyRateRecord(
                effective_from=rate.effective_from,
                value=rate.value,
                decided_on=rate.decided_on,
                source=rate.source.value,
                note=rate.note,
                created_by=rate.created_by,
                created_at=rate.created_at,
                announced_at=rate.announced_at,
            )
        )
        await self._session.flush()

    async def remove(self, rate: KeyRate) -> None:
        record = await self._session.get(KeyRateRecord, rate.effective_from)
        if record is not None:
            await self._session.delete(record)
            await self._session.flush()
