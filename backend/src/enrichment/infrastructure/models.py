"""SQLAlchemy-модели enrichment. Таблицы с префиксом `enrichment_`."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.core.infrastructure.database.base import Base, JSONType


class EnrichmentSnapshotRecord(Base):
    __tablename__ = "enrichment_snapshots"
    __table_args__ = (Index("ix_enrichment_snapshots_application", "application_id", "started_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    application_id: Mapped[UUID] = mapped_column(Uuid)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    inn: Mapped[str] = mapped_column(String(12))
    requested_by_command: Mapped[UUID] = mapped_column(Uuid, unique=True)
    requested_sources: Mapped[list[str]] = mapped_column(JSONType)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class SourceResultRecord(Base):
    __tablename__ = "enrichment_source_results"

    snapshot_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("enrichment_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONType, default=None)
    error_kind: Mapped[str | None] = mapped_column(String(32), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
