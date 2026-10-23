"""Commands of the process engine (`applications.commands`) and other
system-driven changes: offer expiry, the client stage label.

Never commits: inside a Kafka handler the message processor commits the
changes, the outgoing events and the inbox mark together; the expiry job
commits per application.

A command that does not fit the current status is not an error: the client
may have cancelled while scoring was running. It is logged and acknowledged,
the process learns the real state from `applications.events`.
"""

import logging
from uuid import NAMESPACE_URL, UUID, uuid5

from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import InvalidStatusTransitionError, NotFoundError
from src.core.messaging.contracts import applications as contracts
from src.core.messaging.contracts.base import IntegrationMessage
from src.modules.applications.application.interfaces.abs import AbsClient
from src.modules.applications.application.interfaces.outbox import MessageOutbox
from src.modules.applications.application.interfaces.repositories import ApplicationRepository
from src.modules.applications.application.mappers.messages import decision_of, offer_of
from src.modules.applications.application.use_cases.common import publish
from src.modules.applications.domain.application import CreditApplication
from src.modules.applications.domain.enums import ApplicationStatus
from src.modules.applications.domain.statuses import ensure_transition
from src.modules.applications.domain.value_objects import Disbursement

logger = logging.getLogger(__name__)

_INFO_REQUEST_NAMESPACE = uuid5(NAMESPACE_URL, "applications/info-request")


class HandleCommandUseCase:
    def __init__(
        self,
        repository: ApplicationRepository,
        outbox: MessageOutbox,
        clock: Clock,
        abs_client: AbsClient | None = None,
    ) -> None:
        self._repository = repository
        self._outbox = outbox
        self._clock = clock
        self._abs = abs_client

    async def execute(self, command: IntegrationMessage, command_id: UUID) -> bool:
        """Apply a command; False — acknowledged without changes."""
        application_id: UUID = command.application_id  # type: ignore[attr-defined]
        try:
            application = await self._repository.get(application_id)
            changed = await self._apply(application, command, command_id)
        except (InvalidStatusTransitionError, NotFoundError) as exc:
            logger.info(
                "Command %s for application %s skipped: %s", command.TYPE, application_id, exc
            )
            return False
        if changed:
            await self._repository.save(application)
            await publish(application, self._outbox, causation_id=command_id)
        return changed

    async def _apply(
        self, application: CreditApplication, command: IntegrationMessage, command_id: UUID
    ) -> bool:
        now = self._clock.now()
        match command:
            case contracts.StartReview():
                return application.start_review(now, command.client_stage)
            case contracts.RequestInfo():
                application.request_info(
                    # the same command always opens the same request
                    info_request_id=uuid5(_INFO_REQUEST_NAMESPACE, str(command_id)),
                    fields=tuple(command.requested_fields),
                    documents=tuple(command.requested_documents),
                    comment=command.comment,
                    due_at=command.due_at,
                    now=now,
                )
                return True
            case contracts.PresentOffer():
                outcome = "APPROVE" if command.offer.kind == "as_requested" else "COUNTER_OFFER"
                application.present_offer(offer_of(command), decision_of(command, outcome), now)
                return True
            case contracts.RejectApplication():
                application.reject(decision_of(command, "REJECT"), now)
                return True
            case contracts.MarkDisbursed():
                return await self._disburse(application)
        raise TypeError(f"Unexpected command {command.TYPE}")

    async def _disburse(self, application: CreditApplication) -> bool:
        """The ABS call is outside the database transaction, so a retry may
        repeat it: the application id is the idempotency key on the ABS side."""
        if application.status is ApplicationStatus.DISBURSED:
            return False  # repeated command
        ensure_transition(application.status, ApplicationStatus.DISBURSED)
        if application.offer is None or self._abs is None:
            raise RuntimeError("Disbursement needs a signed offer and an ABS client")
        offer = application.offer
        receipt = await self._abs.disburse(
            application.id,
            str(application.number),
            application.organization_id,
            offer.amount.amount,
            offer.term_months,
            offer.rate,
        )
        now = self._clock.now()
        return application.mark_disbursed(
            now, Disbursement(receipt.reference, now, receipt.simulated)
        )


class SetClientStageUseCase:
    """The label of the process stage for the client's screen. A step that
    does not change what the client sees carries no label and is skipped.

    Written past the aggregate on purpose: it is a display label, not the
    business state, and must not fight for the version with the commands
    and the client's own actions."""

    def __init__(self, repository: ApplicationRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    async def execute(self, application_id: UUID, client_stage: str | None) -> bool:
        if not client_stage:
            return False
        return await self._repository.set_client_stage(
            application_id, client_stage, self._clock.now()
        )


class ExpireOfferUseCase:
    def __init__(
        self, repository: ApplicationRepository, outbox: MessageOutbox, clock: Clock
    ) -> None:
        self._repository = repository
        self._outbox = outbox
        self._clock = clock

    async def execute(self, application_id: UUID) -> bool:
        application = await self._repository.get(application_id)
        if not application.expire_offer(self._clock.now()):
            return False
        await self._repository.save(application)
        await publish(application, self._outbox)
        return True
