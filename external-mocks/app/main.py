"""Сервис external-mocks: ЕГРЮЛ/ЕГРИП, ФНС «Прозрачный бизнес», ГИР БО, Контур.Фокус, БКИ
компаний и физлиц, перечни Росфинмониторинга, база ПДЛ, платформа ЗСК Банка России, реестр
лицензий, АБС (выдача и внутренний стоп-лист банка), ЭДО (подписание).

Настоящий HTTP-сервис с «чужим» форматом ответов — бэкенд ходит в него через адаптеры,
а не перекладывает поля 1:1. Все операции АБС и ЭДО помечены `simulated: true`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException

from app import compliance
from app.chaos import chaos_middleware
from app.config import get_settings
from app.data import (
    Company,
    bank_accounts_response,
    bank_stop_list_response,
    bki_response,
    egrul_response,
    fns_response,
    get_company,
)
from app.dossier import gir_bo_response, kontur_response, person_history, person_report_response
from app.licenses import licenses_response
from app.schemas import (
    AbsRequest,
    BkiRequest,
    EdoRequest,
    PepRequest,
    PersonBkiRequest,
    ScreeningRequest,
)

app = FastAPI(title="external-mocks", version="0.1.0")
app.middleware("http")(chaos_middleware)

_NOT_FOUND = "Организация с таким ИНН не найдена в реестре"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def _company(inn: str) -> Company:
    company = get_company(inn)
    if company is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return company


@app.get("/egrul/{inn}")
async def egrul(inn: str) -> dict:
    return egrul_response(_company(inn))


@app.get("/fns/{inn}")
async def fns(inn: str) -> dict:
    return fns_response(_company(inn))


@app.get("/gir-bo/{inn}")
async def gir_bo(inn: str) -> dict:
    return gir_bo_response(_company(inn))


@app.get("/kontur/{inn}")
async def kontur(inn: str) -> dict:
    return kontur_response(_company(inn))


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


@app.post("/bki/person-report")
async def bki_person(req: PersonBkiRequest) -> dict:
    if not req.consent_at:
        raise HTTPException(status_code=400, detail="Требуется согласие субъекта (consent_at)")
    if req.company_inn and req.company_inn in get_settings().bki_always_fail_inns:
        raise HTTPException(status_code=503, detail="Бюро кредитных историй недоступно")
    company = get_company(req.company_inn) if req.company_inn else None
    history = person_history(company, req.last_name, req.first_name, req.middle_name)
    return person_report_response(history, req.last_name, req.first_name, req.middle_name)


@app.post("/rfm/screen")
async def rfm_screen(req: ScreeningRequest) -> dict:
    """Перечни Росфинмониторинга: экстремизм и терроризм, решения МВК, ФРОМУ."""
    results = []
    for subject in req.subjects:
        if subject.type == "UL":
            hits = compliance.screen_organization(subject.inn)
        else:
            hits = compliance.screen_person(subject.name)
        results.append({"id": subject.id, "Совпадения": hits})
    return {"ДатаАктуальности": compliance.lists_date(), "Результаты": results}


@app.post("/pep/screen")
async def pep_screen(req: PepRequest) -> dict:
    """База публичных должностных лиц: категория и должность, если человек — ПДЛ."""
    return {
        "Результаты": [
            {"id": person.id, "ПДЛ": compliance.pep_status(person.fio)} for person in req.persons
        ]
    }


@app.get("/zsk/{inn}")
async def zsk(inn: str) -> dict:
    """Платформа «Знай своего клиента» Банка России: уровень риска юрлица или ИП."""
    company = _company(inn)
    return {
        "ИНН": company.inn,
        "Уровень": compliance.zsk_level(company),
        "ДатаАктуальности": compliance.lists_date(),
    }


@app.get("/licenses/{inn}")
async def licenses(inn: str) -> dict:
    """Реестр лицензий: действующие лицензии компании и лицензируемый вид деятельности."""
    return licenses_response(_company(inn))


@app.get("/abs/accounts/{inn}")
async def abs_accounts(inn: str) -> dict:
    """АБС: клиент банка с какой даты и помесячные обороты по расчётному счёту за 24 месяца."""
    return bank_accounts_response(_company(inn))


@app.get("/abs/stop-list/{inn}")
async def abs_stop_list(inn: str) -> dict:
    """Внутренний стоп-лист банка: стоп-фактор решения, согласия клиента не требует."""
    return bank_stop_list_response(_company(inn))


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
