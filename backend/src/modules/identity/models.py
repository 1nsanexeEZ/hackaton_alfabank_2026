from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.infrastructure.database.base import Base, JSONType
from src.core.infrastructure.database.mixins import (
    DeletedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    # ["accounts.read", ...]
    permissions: Mapped[list[str]] = mapped_column(JSONType, default=list)
    # {"accounts.read": ["not_deleted"], "accounts.create": []}
    policies: Mapped[dict[str, list[str]]] = mapped_column(JSONType, default=dict)

    # passive_deletes: the DB's ON DELETE RESTRICT guards role removal, the ORM
    # must not try to load the collection on delete.
    accounts: Mapped[list["Account"]] = relationship(
        back_populates="role", lazy="raise", passive_deletes=True
    )


class Account(UUIDPrimaryKeyMixin, TimestampMixin, DeletedMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="has_login"),
        # Unique among live accounts only, so a deleted account doesn't block its email/phone.
        Index(
            "uq_accounts_email_active",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_accounts_phone_active",
            "phone",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), index=True)

    role: Mapped[Role] = relationship(back_populates="accounts", lazy="joined")
    profile: Mapped["Profile"] = relationship(
        back_populates="account",
        lazy="joined",
        cascade="all, delete-orphan",
    )


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    last_name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(150))

    account: Mapped[Account] = relationship(back_populates="profile", lazy="raise")


class Consent(UUIDPrimaryKeyMixin, Base):
    """A personal consent of the account's owner (152-FZ, 218-FZ). Rows are never
    rewritten: a new consent is a new row, a revocation only sets `revoked_at`."""

    __tablename__ = "identity_consents"
    __table_args__ = (Index("ix_identity_consents_account_type", "account_id", "type"),)

    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(32))
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # None — valid until revoked.
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Edition of the consent text the person was shown.
    text_version: Mapped[str] = mapped_column(String(32))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
