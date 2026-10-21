from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class TimestampMixin:
    # Python-side defaults: values are known right after flush, so async code
    # never has to refresh the row to read them.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeletedMixin:
    """Soft delete. Backs the `not_deleted` policy."""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    @classmethod
    def entity_is_not_deleted(cls) -> ColumnElement[bool]:
        return cls.deleted_at.is_(None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def mark_deleted(self) -> None:
        self.deleted_at = utcnow()


class OwnableMixin:
    """Row belongs to an account. Backs the `own_only` policy.

    No foreign key on purpose: modules own their tables, the account lives in identity.
    """

    owner_id: Mapped[UUID] = mapped_column(index=True)

    @classmethod
    def user_is_owner(cls, user_id: UUID) -> ColumnElement[bool]:
        return cls.owner_id == user_id
