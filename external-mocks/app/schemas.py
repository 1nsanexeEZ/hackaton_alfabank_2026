"""Схемы тел POST-запросов. Формат ответов намеренно «чужой» и собирается вручную в data.py."""

from __future__ import annotations

from pydantic import BaseModel


class BkiRequest(BaseModel):
    inn: str
    consent_at: str | None = None
    request_id: str | None = None


class PersonBkiRequest(BaseModel):
    """Кредитный отчёт физлица (руководителя). `company_inn` — компания, от имени которой
    запрашивают: по нему мок подбирает сценарий демо-руководителя."""

    last_name: str
    first_name: str
    middle_name: str | None = None
    company_inn: str | None = None
    consent_at: str | None = None
    request_id: str | None = None


class AbsRequest(BaseModel):
    application_id: str
    account: str
    amount_kop: int


class EdoRequest(BaseModel):
    document_hash: str
    signer: str
