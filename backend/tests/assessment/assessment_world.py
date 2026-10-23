"""Мир сквозных golden-тестов оценки (#41): настоящее приложение со всеми модулями и сидами §9.

- SQLite, сообщения в ручном режиме: команду кладём в outbox (как это сделал бы process) и
  доставляем `drain()` через реальные подписки модулей — «команда → ответ»;
- заявки создаются через публичный API applications от имени демо-аккаунтов;
- документы лежат в памяти (`FakeDocumentStorage`), выписки — `seed/statements/*.csv`;
- внешние источники — ответы сервиса external-mocks, записанные в `fixtures/external_mocks.json`
  и поданные адаптерам enrichment через `httpx.MockTransport`: настоящий HTTP-путь, ретраи и ACL.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID, uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.access.permissions import Permissions
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.contracts.decision import MakeDecision
from src.core.messaging.contracts.enrichment import FetchEnrichment
from src.core.messaging.contracts.scoring import CalculateScore
from src.core.messaging.outbox import OutboxRecord, SqlAlchemyOutboxWriter
from src.modules.applications.facade import ApplicationsFacade, ScoringInputDTO
from src.modules.applications.infrastructure.repositories.applications import (
    SqlAlchemyApplicationRepository,
)
from src.modules.clients.infrastructure.database.models import OrganizationModel
from src.modules.decision.facade import ClientDecisionDTO, DecisionDTO, DecisionFacade
from src.modules.enrichment.application.interfaces.sources import Sources
from src.modules.enrichment.infrastructure.adapters.aml_http import (
    PepHttpSource,
    RfmHttpSource,
    ZskHttpSource,
)
from src.modules.enrichment.infrastructure.adapters.bank_stop_list_http import (
    BankStopListHttpSource,
)
from src.modules.enrichment.infrastructure.adapters.bki_http import BkiHttpSource
from src.modules.enrichment.infrastructure.adapters.bki_person_http import BkiPersonHttpSource
from src.modules.enrichment.infrastructure.adapters.egrul_http import EgrulHttpSource
from src.modules.enrichment.infrastructure.adapters.fns_http import FnsHttpSource
from src.modules.enrichment.infrastructure.adapters.gir_bo_http import GirBoHttpSource
from src.modules.enrichment.infrastructure.adapters.kontur_http import KonturHttpSource
from src.modules.identity.infrastructure.database.models import AccountModel
from src.modules.process.domain.steps import ENRICHMENT_SOURCES
from tests.fakes.document_storage import FakeDocumentStorage
from tests.helpers import bearer, token_for

T = TypeVar("T")

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
_STEP = timedelta(minutes=1)
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "external_mocks.json"
_STATEMENTS = Path(__file__).resolve().parents[2] / "seed" / "statements"

_CLIENT_PERMISSIONS = [
    Permissions.REQUESTS_READ,
    Permissions.REQUESTS_CREATE,
    Permissions.REQUESTS_UPDATE,
    Permissions.ORGANIZATIONS_READ,
]
_CLIENT_POLICIES = {
    Permissions.REQUESTS_READ: ["org_member"],
    Permissions.REQUESTS_CREATE: ["org_member"],
    Permissions.REQUESTS_UPDATE: ["org_member"],
}


def mock_sources() -> Sources:
    """Адаптеры enrichment поверх записанных ответов external-mocks (без пауз между ретраями)."""
    recorded: dict[str, Any] = json.loads(_FIXTURES.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        aml = _aml_answer(request)
        if aml is not None:
            return aml
        if path.startswith("/abs/stop-list/"):
            # Демо-компании во внутреннем стоп-листе банка не состоят.
            inn = path.rsplit("/", 1)[1]
            if inn not in recorded:
                return httpx.Response(404, json={"detail": "not found"})
            body = {"inn": inn, "listed": False, "reason": None, "listed_at": None}
            return httpx.Response(200, json=body)
        if path == "/bki/report":
            source, inn = "bki", json.loads(request.content)["inn"]
        elif path == "/bki/person-report":
            source, inn = "bki_head", json.loads(request.content)["company_inn"]
        else:
            source, inn = path.strip("/").split("/", 1)
            source = source.replace("-", "_")  # /gir-bo/{inn} -> gir_bo
        entry = recorded.get(inn)
        if entry is None:
            return httpx.Response(404, json={"detail": "not found"})
        answer = entry[source]
        return httpx.Response(answer["status"], json=answer["body"])

    client = httpx.AsyncClient(
        base_url="http://external-mocks.test", transport=httpx.MockTransport(handler)
    )
    backoff = (0.0, 0.0)
    return Sources(
        registry=EgrulHttpSource(client, backoff=backoff),
        tax=FnsHttpSource(client, backoff=backoff),
        bureau=BkiHttpSource(client, backoff=backoff),
        accounting=GirBoHttpSource(client, backoff=backoff),
        counterparty=KonturHttpSource(client, backoff=backoff),
        person_bureau=BkiPersonHttpSource(client, backoff=backoff),
        aml_lists=RfmHttpSource(client, backoff=backoff),
        pep=PepHttpSource(client, backoff=backoff),
        zsk=ZskHttpSource(client, backoff=backoff),
        bank_stop_list=BankStopListHttpSource(client, backoff=backoff),
    )


def _aml_answer(request: httpx.Request) -> httpx.Response | None:
    """Проверки по 115-ФЗ: демо-компании и их люди чистые, уровень ЗСК низкий (как отвечает
    external-mocks, `app/compliance.py`); ответ собирается по запросу."""
    path = request.url.path
    if path == "/rfm/screen":
        subjects = json.loads(request.content)["subjects"]
        results = [{"id": subject["id"], "Совпадения": []} for subject in subjects]
        return httpx.Response(200, json={"ДатаАктуальности": "2026-10-21", "Результаты": results})
    if path == "/pep/screen":
        persons = json.loads(request.content)["persons"]
        return httpx.Response(
            200, json={"Результаты": [{"id": person["id"], "ПДЛ": None} for person in persons]}
        )
    if path.startswith("/zsk/"):
        inn = path.removeprefix("/zsk/")
        body = {"ИНН": inn, "Уровень": "НИЗКИЙ", "ДатаАктуальности": "2026-10-21"}
        return httpx.Response(200, json=body)
    return None


@dataclass
class Assessment:
    client: TestClient
    storage: FakeDocumentStorage

    # --- инфраструктура -------------------------------------------------

    def run(self, fn: Callable[..., Awaitable[T]], *args: Any) -> T:
        return self.client.portal.call(fn, *args)  # type: ignore[union-attr]

    def with_session(self, fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
        async def call() -> T:
            async with self.client.app.state.session_factory() as session:  # type: ignore[attr-defined]
                return await fn(session)

        return self.run(call)

    def facade(self, key: type[Any], call: Callable[[Any], Awaitable[T]]) -> T:
        facades = self.client.app.state.facades  # type: ignore[attr-defined]
        return self.with_session(lambda session: call(facades.get(key, session)))

    def organization_id(self, inn: str) -> UUID:
        async def find(session: AsyncSession) -> UUID:
            stmt = select(OrganizationModel.id).where(OrganizationModel.inn == inn)
            return (await session.scalars(stmt)).one()

        return self.with_session(find)

    def account_id(self, email: str) -> UUID:
        async def find(session: AsyncSession) -> UUID:
            return (
                await session.scalars(select(AccountModel.id).where(AccountModel.email == email))
            ).one()

        return self.with_session(find)

    def headers(self, email: str) -> dict[str, str]:
        token = token_for(
            self.client.app,  # type: ignore[arg-type]
            _CLIENT_PERMISSIONS,
            _CLIENT_POLICIES,
            self.account_id(email),
        )
        return bearer(token)

    # --- заявка через публичный API ---------------------------------------

    def apply(
        self,
        *,
        email: str,
        inn: str,
        product: str,
        amount: str,
        term: int,
        purpose: str = "working_capital",
        documents: tuple[str, ...] = (),
        statement: str | None = None,
        collateral: dict[str, Any] | None = None,
        product_fields: dict[str, Any] | None = None,
    ) -> UUID:
        headers = self.headers(email)
        created = self.client.post(
            "/applications",
            json={"organization_id": str(self.organization_id(inn)), "product_code": product},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        application_id = created.json()["id"]
        for document_type in documents:
            self._upload(
                application_id, document_type, b"%PDF-1.4 demo", "application/pdf", headers
            )
        if statement is not None:
            content = (_STATEMENTS / f"{statement}.csv").read_bytes()
            self._upload(application_id, "bank_statement", content, "text/csv", headers)

        version = self.client.get(f"/applications/{application_id}", headers=headers).json()[
            "version"
        ]
        body: dict[str, Any] = {
            "version": version,
            "request": {"amount": amount, "term_months": term, "purpose": purpose},
            "consents": {"personal_data": True, "credit_bureau": True},
        }
        if collateral is not None:
            body["collateral"] = collateral
        if product_fields is not None:
            body["product_fields"] = product_fields
        updated = self.client.patch(f"/applications/{application_id}", json=body, headers=headers)
        assert updated.status_code == 200, updated.text
        submitted = self.client.post(f"/applications/{application_id}/submit", headers=headers)
        assert submitted.status_code == 200, submitted.text
        return UUID(application_id)

    def _upload(
        self,
        application_id: str,
        document_type: str,
        content: bytes,
        content_type: str,
        headers: dict[str, str],
    ) -> None:
        announced = self.client.post(
            f"/applications/{application_id}/documents",
            json={
                "type": document_type,
                "filename": f"{document_type}.{'csv' if content_type == 'text/csv' else 'pdf'}",
                "content_type": content_type,
                "size_bytes": len(content),
            },
            headers=headers,
        )
        assert announced.status_code == 201, announced.text
        document_id = announced.json()["document"]["id"]
        self.storage.put(f"applications/{application_id}/{document_id}", content, content_type)
        confirmed = self.client.post(
            f"/applications/{application_id}/documents/{document_id}/confirm", headers=headers
        )
        assert confirmed.status_code == 200, confirmed.text

    # --- команды и ответы ------------------------------------------------

    def scoring_input(self, application_id: UUID) -> ScoringInputDTO:
        return self.facade(ApplicationsFacade, lambda f: f.get_scoring_input(application_id))

    def fetch_enrichment(self, application_id: UUID) -> dict[str, Any]:
        source = self.scoring_input(application_id)
        command = FetchEnrichment(
            application_id=application_id,
            organization_id=source.organization_id,
            inn=source.organization.inn,
            # Как process: все источники. Личных согласий в сидах нет — БКИ руководителя `skipped`.
            sources=list(ENRICHMENT_SOURCES),
            bki_consent_at=source.credit_bureau_consent_at,
            statement_document_ids=list(source.statement_document_ids),
        )
        return self.deliver(command, application_id, reply="EnrichmentCompleted")

    def calculate_score(self, application_id: UUID) -> dict[str, Any]:
        command = CalculateScore(application_id=application_id)
        return self.deliver(command, application_id, reply="ScoreCalculated")

    def make_decision(self, application_id: UUID) -> dict[str, Any]:
        command = MakeDecision(application_id=application_id)
        return self.deliver(command, application_id, reply="DecisionMade")

    def decision(self, application_id: UUID) -> DecisionDTO | None:
        """Решение для банка: с кодами причин и трассой правил."""
        return self.facade(DecisionFacade, lambda f: f.get_decision(application_id))

    def client_view(self, application_id: UUID) -> ClientDecisionDTO | None:
        """То, что видит клиент: без кодов причин и трассы."""
        return self.facade(DecisionFacade, lambda f: f.get_client_view(application_id))

    # --- дозапрос: играем process, которого ещё нет ------------------------

    def request_statement(self, application_id: UUID, comment: str) -> UUID:
        """Взять заявку в работу и запросить выписку. Настоящий process уже мог открыть
        дозапрос сам (решение REQUEST_INFO пришло ему через ту же шину) — тогда отвечаем
        на его дозапрос; иначе открываем свой, меняя агрегат напрямую."""
        clock = self.client.app.state.clock  # type: ignore[attr-defined]
        info_request_id = uuid4()

        async def change(session: AsyncSession) -> None:
            nonlocal info_request_id
            repository = SqlAlchemyApplicationRepository(session)
            application = await repository.get(application_id)
            opened = application.open_info_request
            if opened is not None and "bank_statement" in opened.requested_documents:
                info_request_id = opened.id
                return
            now = clock.now()
            application.start_review(now)
            application.request_info(
                info_request_id=info_request_id,
                fields=(),
                documents=("bank_statement",),
                comment=comment,
                due_at=None,
                now=now,
            )
            application.pull_events()
            await repository.save(application)
            await session.commit()

        self.with_session(change)
        return info_request_id

    def answer_with_statement(
        self, application_id: UUID, info_request_id: UUID, *, email: str, statement: str
    ) -> None:
        """Клиент загружает выписку по дозапросу и отвечает на него через API."""
        headers = self.headers(email)
        content = (_STATEMENTS / f"{statement}.csv").read_bytes()
        self._upload(str(application_id), "bank_statement", content, "text/csv", headers)
        answered = self.client.post(
            f"/applications/{application_id}/info-requests/{info_request_id}/answer",
            headers=headers,
        )
        assert answered.status_code == 200, answered.text

    def deliver(
        self, command: IntegrationMessage, application_id: UUID, *, reply: str
    ) -> dict[str, Any]:
        """Положить команду в outbox (как process), доставить и вернуть payload ответа."""
        clock = self.client.app.state.clock  # type: ignore[attr-defined]
        # Между шагами конвейера проходит время: без этого у повторного снимка/скора/решения
        # то же время, что у прошлого, и «последний» по фасаду выбирается наугад.
        clock.advance(_STEP)

        async def stage(session: AsyncSession) -> None:
            await SqlAlchemyOutboxWriter(session, "process", clock).add(
                command, key=application_id, correlation_id=application_id
            )
            await session.commit()

        self.with_session(stage)
        self.run(self.client.app.state.messaging.drain)  # type: ignore[attr-defined]
        replies = self.replies(reply, application_id)
        assert replies, f"нет ответа {reply} на {command.TYPE}"
        return replies[-1]

    def replies(self, message_type: str, application_id: UUID) -> list[dict[str, Any]]:
        async def read(session: AsyncSession) -> list[dict[str, Any]]:
            stmt = (
                select(OutboxRecord)
                .where(OutboxRecord.message_type == message_type)
                .order_by(OutboxRecord.id)
            )
            payloads = [record.envelope["payload"] for record in await session.scalars(stmt)]
            return [p for p in payloads if p.get("application_id") == str(application_id)]

        return self.with_session(read)

    def dead_letters(self) -> list[Any]:
        bus = self.client.app.state.messaging.bus  # type: ignore[attr-defined]
        return list(bus.dead_letters)
