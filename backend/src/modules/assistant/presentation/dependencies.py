"""Use cases for the routers: adapters are picked here, use cases see only interfaces."""

from typing import Annotated

from fastapi import Depends, Request

from src.core.access.access_context import AccessContext
from src.core.access.dependencies import get_access_context_for
from src.core.access.permissions import Permissions
from src.core.domain.clock import Clock
from src.core.facades import use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.uow import SqlAlchemyUnitOfWork, UnitOfWork
from src.modules.applications.facade import ApplicationsFacade
from src.modules.assistant.application.interfaces.context import ContextSource
from src.modules.assistant.application.interfaces.language_model import LanguageModelSetup
from src.modules.assistant.application.interfaces.rate_limit import QuestionRateLimiter
from src.modules.assistant.application.interfaces.repositories import ConversationRepository
from src.modules.assistant.application.use_cases.conversations import (
    GetConversationUseCase,
    ListApplicationsUseCase,
    StartConversationUseCase,
)
from src.modules.assistant.application.use_cases.questions import (
    AcceptQuestionUseCase,
    AnswerQuestionUseCase,
)
from src.modules.assistant.application.use_cases.status import GetStatusUseCase
from src.modules.assistant.domain.views import Viewer
from src.modules.assistant.infrastructure.adapters.context_source import FacadeContextSource
from src.modules.assistant.infrastructure.repositories.conversations import (
    SqlAlchemyConversationRepository,
)
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.facade import DecisionFacade
from src.modules.products.facade import ProductsFacade

# --- access --------------------------------------------------------------------

# A client: the companies they are a member of (`org_member`); bank staff: not limited.
CanUse = Annotated[AccessContext, Depends(get_access_context_for(Permissions.ASSISTANT_USE))]


def get_viewer(access: CanUse) -> Viewer:
    return Viewer(account_id=access.user_id, organization_ids=access.organization_ids)


CurrentViewer = Annotated[Viewer, Depends(get_viewer)]


# --- adapters ------------------------------------------------------------------


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_uow(session: DbSession) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def get_repository(session: DbSession) -> ConversationRepository:
    return SqlAlchemyConversationRepository(session)


def get_context_source(
    applications: Annotated[ApplicationsFacade, Depends(use_facade(ApplicationsFacade))],
    decision: Annotated[DecisionFacade, Depends(use_facade(DecisionFacade))],
    products: Annotated[ProductsFacade, Depends(use_facade(ProductsFacade))],
    clients: Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))],
) -> ContextSource:
    return FacadeContextSource(applications, decision, products, clients)


def get_model_setup(request: Request) -> LanguageModelSetup:
    """Built once in `module.wire`; tests put a fake model there."""
    return request.app.state.assistant_model


def get_rate_limiter(request: Request) -> QuestionRateLimiter:
    return request.app.state.assistant_rate_limiter


ClockDep = Annotated[Clock, Depends(get_clock)]
Uow = Annotated[UnitOfWork, Depends(get_uow)]
Repository = Annotated[ConversationRepository, Depends(get_repository)]
Source = Annotated[ContextSource, Depends(get_context_source)]
ModelSetup = Annotated[LanguageModelSetup, Depends(get_model_setup)]
RateLimiter = Annotated[QuestionRateLimiter, Depends(get_rate_limiter)]


# --- use cases -----------------------------------------------------------------


def get_status(request: Request, setup: ModelSetup) -> GetStatusUseCase:
    return GetStatusUseCase(setup, request.app.state.assistant_reachability)


def get_start_conversation(
    uow: Uow, repository: Repository, clock: ClockDep
) -> StartConversationUseCase:
    return StartConversationUseCase(uow, repository, clock)


def get_get_conversation(repository: Repository) -> GetConversationUseCase:
    return GetConversationUseCase(repository)


def get_list_applications(source: Source) -> ListApplicationsUseCase:
    return ListApplicationsUseCase(source)


def get_accept_question(
    repository: Repository, source: Source, rate_limiter: RateLimiter
) -> AcceptQuestionUseCase:
    return AcceptQuestionUseCase(repository, source, rate_limiter)


def get_answer_question(
    uow: Uow, repository: Repository, source: Source, setup: ModelSetup, clock: ClockDep
) -> AnswerQuestionUseCase:
    return AnswerQuestionUseCase(uow, repository, source, setup.model, clock)


StatusDep = Annotated[GetStatusUseCase, Depends(get_status)]
StartConversationDep = Annotated[StartConversationUseCase, Depends(get_start_conversation)]
GetConversationDep = Annotated[GetConversationUseCase, Depends(get_get_conversation)]
ListApplicationsDep = Annotated[ListApplicationsUseCase, Depends(get_list_applications)]
AcceptQuestionDep = Annotated[AcceptQuestionUseCase, Depends(get_accept_question)]
AnswerQuestionDep = Annotated[AnswerQuestionUseCase, Depends(get_answer_question)]
