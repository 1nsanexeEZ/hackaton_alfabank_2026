from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.application.interfaces.repositories import TicketStore
from src.modules.notifications.domain.feed import Recipient
from src.modules.notifications.domain.viewers import StreamGrant
from src.modules.notifications.infrastructure.database.models import StreamTicket
from src.modules.notifications.infrastructure.repositories.mappers import aware


class SqlAlchemyTicketStore(TicketStore):
    # Used and expired tickets are kept this long, then removed on the next issue.
    RETENTION_SECONDS = 3600

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        ticket_hash: str,
        account_id: UUID,
        roles: Sequence[str],
        expires_at: datetime,
        now: datetime,
    ) -> None:
        cutoff = datetime.fromtimestamp(now.timestamp() - self.RETENTION_SECONDS, UTC)
        await self._session.execute(delete(StreamTicket).where(StreamTicket.expires_at < cutoff))
        self._session.add(
            StreamTicket(
                ticket_hash=ticket_hash,
                account_id=account_id,
                roles=list(roles),
                expires_at=expires_at,
                created_at=now,
            )
        )
        await self._session.flush()

    async def redeem(self, ticket_hash: str, now: datetime) -> StreamGrant | None:
        row = (
            await self._session.scalars(
                select(StreamTicket).where(StreamTicket.ticket_hash == ticket_hash)
            )
        ).one_or_none()
        if row is None or row.used_at is not None or aware(row.expires_at) <= now:
            return None
        # Conditional update: of two concurrent connections only one wins the ticket.
        result = await self._session.execute(
            update(StreamTicket)
            .where(StreamTicket.id == row.id, StreamTicket.used_at.is_(None))
            .values(used_at=now)
        )
        if getattr(result, "rowcount", 0) != 1:
            return None
        recipients = (Recipient.account(row.account_id),) + tuple(
            Recipient.role(role) for role in row.roles or ()
        )
        return StreamGrant(account_id=row.account_id, recipients=recipients)
