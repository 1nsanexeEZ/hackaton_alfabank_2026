"""The answer pipeline: route → collect facts → (the model words them) → post-check.

The model never decides anything: it gets the facts collected by code and a
template answer, and its text is shown only if every number in it comes from
the facts. Otherwise, and whenever the model is off, slow or busy, the client
gets the template.
"""

import logging
import time
from decimal import Decimal
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.uow import UnitOfWork
from src.modules.assistant.application.dto.assistant import AcceptedQuestionDTO, ReplyDTO
from src.modules.assistant.application.interfaces.context import ContextSource
from src.modules.assistant.application.interfaces.language_model import (
    LanguageModel,
    LanguageModelBusyError,
    LanguageModelTimeoutError,
    LanguageModelUnavailableError,
)
from src.modules.assistant.application.interfaces.rate_limit import QuestionRateLimiter
from src.modules.assistant.application.interfaces.repositories import ConversationRepository
from src.modules.assistant.domain import answers
from src.modules.assistant.domain.answers import Draft
from src.modules.assistant.domain.conversation import MAX_QUESTION_CHARS, Mode, StoredMessage
from src.modules.assistant.domain.exceptions import QuestionRejectedError
from src.modules.assistant.domain.intents import Intent, parse_payment_query, route
from src.modules.assistant.domain.postcheck import check
from src.modules.assistant.domain.prompt import build_messages
from src.modules.assistant.domain.views import (
    ApplicationView,
    ClientDecisionView,
    ProductView,
    Viewer,
)

log = logging.getLogger(__name__)


class AcceptQuestionUseCase:
    """Everything that may refuse a question, before an answer (or its stream) starts."""

    def __init__(
        self,
        repository: ConversationRepository,
        source: ContextSource,
        rate_limiter: QuestionRateLimiter,
    ) -> None:
        self._repository = repository
        self._source = source
        self._rate_limiter = rate_limiter

    async def execute(
        self, viewer: Viewer, conversation_id: UUID, text: str, application_id: UUID | None
    ) -> AcceptedQuestionDTO:
        """Raises QuestionRejectedError, ConversationNotFoundError,
        ApplicationNotFoundError, TooManyQuestionsError."""
        question = text.strip()
        if not question or len(question) > MAX_QUESTION_CHARS:
            raise QuestionRejectedError()
        await self._repository.get(viewer.account_id, conversation_id)
        app = await self._source.get_application(viewer, application_id) if application_id else None
        self._rate_limiter.hit(viewer.account_id)
        return AcceptedQuestionDTO(conversation_id, question, app)


class AnswerQuestionUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repository: ConversationRepository,
        source: ContextSource,
        model: LanguageModel | None,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._source = source
        self._model = model
        self._clock = clock

    async def execute(self, viewer: Viewer, accepted: AcceptedQuestionDTO) -> ReplyDTO:
        started = time.monotonic()
        question, app = accepted.question, accepted.application
        asked_about = app.id if app else None
        intent = route(question, has_application=app is not None)
        draft, app = await self._draft(viewer, intent, question, app)
        answer, mode, reason = await self._word(question, draft)

        now = self._clock.now()
        app_id = app.id if app else None
        reply = StoredMessage(uuid4(), "assistant", answer, now, app_id, intent.value, mode)
        async with self._uow:
            await self._repository.append(
                accepted.conversation_id,
                (
                    StoredMessage(uuid4(), "user", question, now, asked_about, intent.value),
                    reply,
                ),
            )
            await self._uow.commit()
        # No question or answer text in logs: they may hold personal data.
        log.info(
            "assistant answer intent=%s mode=%s fallback=%s ms=%d",
            intent.value,
            mode,
            reason,
            (time.monotonic() - started) * 1000,
        )
        return ReplyDTO(reply.id, answer, mode, intent, app_id, reason)

    # ---------- facts ----------

    async def _draft(
        self, viewer: Viewer, intent: Intent, question: str, app: ApplicationView | None
    ) -> tuple[Draft, ApplicationView | None]:
        if intent is Intent.INJECTION:
            return answers.injection_refusal(), app
        if intent is Intent.OFF_TOPIC:
            return answers.off_topic(), app
        if intent is Intent.GREETING:
            return answers.greeting(), app

        products = await self._source.list_products()
        by_code = {p.code: p for p in products}
        if intent is Intent.PRODUCTS:
            return answers.products_answer(question, products), app
        if intent is Intent.PAYMENT:
            return await self._payment(viewer, question, app, products), app

        if app is None:
            app = await self._single_active_application(viewer)
        decision = await self._decision(viewer, app)
        if intent is Intent.INTERNAL_DATA:
            return answers.internal_data_refusal(decision), app
        if app is None:
            if intent is Intent.STATUS:
                apps = await self._source.list_applications(viewer)
                return answers.applications_overview(apps, by_code), app
            return answers.need_application(), app
        if intent is Intent.DECISION:
            return answers.explain_decision(app, decision, by_code), app
        return answers.application_status(app, decision, by_code, can_sign=app.viewer_can_sign), app

    async def _payment(
        self,
        viewer: Viewer,
        question: str,
        app: ApplicationView | None,
        products: list[ProductView],
    ) -> Draft:
        query = parse_payment_query(question)
        matched = answers.match_products(question, products)
        if app is None and not matched:
            app = await self._single_active_application(viewer)
        decision = await self._decision(viewer, app)
        by_code = {p.code: p for p in products}
        product = matched[0] if matched else (by_code.get(app.product_code) if app else None)

        # «Сколько я буду платить?» about an offer: the bank's own terms.
        if query.amount is None and query.term_months is None and decision and decision.terms:
            t = decision.terms
            schedule = self._source.calculate_payment(
                t.amount, t.term_months, t.rate, t.schedule_type
            )
            offered = by_code.get(app.product_code) if app else None
            return answers.payment_answer(query, schedule, offered, "ставка из предложения банка")

        amount = query.amount or (app.request.amount if app and app.request else None)
        term = query.term_months or (app.request.term_months if app and app.request else None)
        product = product or by_code.get("UNSECURED")
        if amount is None or term is None or product is None:
            return answers.payment_answer(query, None, None, "")
        offer = decision if app and app.product_code == product.code else None
        rate, source = _rate_for(product, offer)
        repayment = product.repayment_options[0] if product.repayment_options else "annuity"
        try:
            schedule = self._source.calculate_payment(amount, term, rate, repayment)
        except ValueError:
            return answers.payment_answer(query, None, None, "")
        return answers.payment_answer(query, schedule, product, source)

    async def _single_active_application(self, viewer: Viewer) -> ApplicationView | None:
        apps = [
            a
            for a in await self._source.list_applications(viewer)
            if a.status in answers.ACTIVE_STATUSES
        ]
        if len(apps) != 1:
            return None
        # A list row may be short: read the whole card.
        return await self._source.get_application(viewer, apps[0].id)

    async def _decision(
        self, viewer: Viewer, app: ApplicationView | None
    ) -> ClientDecisionView | None:
        return await self._source.get_client_decision(viewer, app.id) if app else None

    # ---------- wording ----------

    async def _word(self, question: str, draft: Draft) -> tuple[str, Mode, str | None]:
        if not draft.rewordable:
            return draft.template, "rules", "template_only"
        model = self._model
        if model is None:
            return draft.template, "rules", "disabled"
        messages = build_messages(question, draft, with_client_text=model.inside_perimeter)
        try:
            text = await model.complete(messages)
        except LanguageModelBusyError:
            return draft.template, "rules", "busy"
        except LanguageModelTimeoutError:
            return draft.template, "rules", "timeout"
        except LanguageModelUnavailableError:
            return draft.template, "rules", "unavailable"
        verdict = check(text, draft.facts)
        if not verdict.ok:
            log.info("assistant postcheck rejected: %s", ",".join(verdict.violations))
            return draft.template, "rules", "postcheck"
        return text.strip(), "llm", None


def _rate_for(product: ProductView, decision: ClientDecisionView | None) -> tuple[Decimal, str]:
    if decision and decision.terms:
        return decision.terms.rate, "ставка из предложения банка"
    return product.rate_base, f"минимальная ставка продукта «{product.name}»"
