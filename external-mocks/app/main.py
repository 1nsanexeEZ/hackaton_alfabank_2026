"""Сервис external-mocks: ЕГРЮЛ/ЕГРИП, ФНС «Прозрачный бизнес», БКИ, АБС (выдача), ЭДО (подписание).

Настоящий HTTP-сервис с «чужим» форматом ответов — бэкенд ходит в него через адаптеры,
а не перекладывает поля 1:1. Все операции АБС и ЭДО помечены `simulated: true`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException

from app.chaos import chaos_middleware
from app.config import get_settings
from app.data import bki_response, egrul_response, fns_response, get_company
from app.schemas import AbsRequest, BkiRequest, EdoRequest

app = FastAPI(title="external-mocks", version="0.1.0")
app.middleware("http")(chaos_middleware)

_NOT_FOUND = "Организация с таким ИНН не найдена в реестре"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/egrul/{inn}")
async def egrul(inn: str) -> dict:
    company = get_company(inn)
    if company is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return egrul_response(company)


@app.get("/fns/{inn}")
async def fns(inn: str) -> dict:
    company = get_company(inn)
    if company is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return fns_response(company)


@app.post("/bki/report")
async def bki(req: BkiRequest) -> dict:
    if not req.consent_at:
        raise HTTPException(status_code=400, detail="Требуется согласие субъекта (consent_at)")
    company = get_company(req.inn)
    if company is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if req.inn in get_settings().bki_always_fail_inns:
        raise HTTPException(status_code=503, detail="Бюро кредитных историй недоступно")
    return bki_response(company)


@app.post("/abs/disbursements")
async def abs_disbursement(req: AbsRequest) -> dict:
    return {
        "operation_id": str(uuid.uuid4()),
        "application_id": req.application_id,
        "account": req.account,
        "amount_kop": req.amount_kop,
        "status": "executed",
        "simulated": True,
    }


@app.post("/edo/sign")
async def edo_sign(req: EdoRequest) -> dict:
    return {
        "signature_id": str(uuid.uuid4()),
        "document_hash": req.document_hash,
        "signer": req.signer,
        "signed_at": datetime.now(UTC).isoformat(),
        "simulated": True,
    }
