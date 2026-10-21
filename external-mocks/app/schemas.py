"""Схемы тел POST-запросов. Формат ответов намеренно «чужой» и собирается вручную в data.py."""

from __future__ import annotations

from pydantic import BaseModel


class BkiRequest(BaseModel):
    inn: str
    consent_at: str | None = None
    request_id: str | None = None


class AbsRequest(BaseModel):
    application_id: str
    account: str
    amount_kop: int


class EdoRequest(BaseModel):
    document_hash: str
    signer: str
