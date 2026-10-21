"""SQLAlchemy models of applications. Tables are prefixed with `applications_`."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Sequence,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from src.core.infrastructure.database.base import Base, JSONType
from src.core.infrastructure.database.mixins import (
    OrganizationOwnedMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)

# Numbers КР-<year>-<NNNNNN>; on SQLite (tests) the repository counts rows instead.
NUMBER_SEQUENCE = Sequence("applications_number_seq", metadata=Base.metadata)

FINAL_STATUSES_SQL = "('disbursed', 'rejected', 'offer_declined', 'expired', 'cancelled')"


class ApplicationRecord(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, VersionMixin, Base):
    __tablename__ = "applications_applications"
    __table_args__ = (
        Index("ix_applications_applications_org_status", "organization_id", "status"),
        # Second line of defence for "one active application per product".
        Index(
            "uq_applications_applications_active_product",
            "organization_id",
            "product_code",
            unique=True,
            postgresql_where=text(f"status NOT IN {FINAL_STATUSES_SQL}"),
            sqlite_where=text(f"status NOT IN {FINAL_STATUSES_SQL}"),
        ),
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        # Optimistic locking: UPDATE ... WHERE version = :loaded, a stale writer
        # gets StaleDataError (409 for the client, a retry for a Kafka handler).
        return {"version_id_col": cls.__table__.c.version}

    number: Mapped[str] = mapped_column(String(32), unique=True)
    applicant_account_id: Mapped[UUID]
    product_code: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    client_stage: Mapped[str | None] = mapped_column(String(255))
    product_terms: Mapped[dict[str, Any]] = mapped_column(JSONType)
    request: Mapped[dict[str, Any]] = mapped_column(JSONType)
    product_fields: Mapped[dict[str, Any]] = mapped_column(JSONType)
    collateral: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    consents: Mapped[dict[str, Any]] = mapped_column(JSONType)
    org_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    offer: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    decision_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    documents: Mapped[list["DocumentRecord"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DocumentRecord.created_at",
    )
    info_requests: Mapped[list["InfoRequestRecord"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="InfoRequestRecord.created_at"
    )
    history: Mapped[list["StatusHistoryRecord"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="StatusHistoryRecord.id"
    )
    signature: Mapped["SignatureRecord | None"] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class DocumentRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "applications_documents"

    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications_applications.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    s3_key: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(32))
    uploaded_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    info_request_id: Mapped[UUID | None]
    review_comment: Mapped[str | None] = mapped_column(Text)

    application: Mapped[ApplicationRecord] = relationship(back_populates="documents")


class InfoRequestRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "applications_info_requests"

    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications_applications.id", ondelete="CASCADE"), index=True
    )
    requested_fields: Mapped[list[str]] = mapped_column(JSONType)
    requested_documents: Mapped[list[str]] = mapped_column(JSONType)
    comment: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_by: Mapped[UUID | None]


class StatusHistoryRecord(Base):
    __tablename__ = "applications_status_history"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications_applications.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[UUID | None]
    reason: Mapped[str | None] = mapped_column(Text)


class SignatureRecord(Base):
    """Simulated signature: who, when, from where and what exactly was signed."""

    __tablename__ = "applications_signatures"

    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications_applications.id", ondelete="CASCADE"), primary_key=True
    )
    signed_by: Mapped[UUID]
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    offer_hash: Mapped[str] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    edo_document_id: Mapped[str | None] = mapped_column(String(128))
