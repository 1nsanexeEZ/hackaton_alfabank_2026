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

from src.applications.application.ports import AbsClient, ApplicationRepository
from src.applications.application.translate import to_contract
from src.applications.domain.application import CreditApplication
from src.applications.domain.statuses import ApplicationStatus, ensure_transition
from src.applications.domain.value_objects import DecisionSummary, Disbursement, Offer
from src.core.domain import Money
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import InvalidStatusTransitionError, NotFoundError
from src.core.messaging.contracts import applications as contracts
from src.core.messaging.contracts.base import IntegrationMessage
from src.core.messaging.outbox import OutboxWriter

logger = logging.getLogger(__name__)

_INFO_REQUEST_NAMESPACE = uuid5(NAMESPACE_URL, "applications/info-request")


class CommandService:
    def __init__(
        self,
        repository: ApplicationRepository,
        outbox: OutboxWriter,
        clock: Clock,
        abs_client: AbsClient | None = None,
    ) -> None:
        self._repository = repository
        self._outbox = outbox
        self._clock = clock
        self._abs = abs_client

    async def handle(self, command: IntegrationMessage, command_id: UUID) -> bool:
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
            await self._store(application, causation_id=command_id)
        return changed

    async def set_client_stage(self, application_id: UUID, client_stage: str | None) -> bool:
        """The label of the process stage for the client's screen. A step that
        does not change what the client sees carries no label and is skipped.

        Written past the aggregate on purpose: it is a display label, not the
        business state, and must not fight for the version with the commands
        and the client's own actions."""
        if not client_stage:
            return False
        return await self._repository.set_client_stage(
            application_id, client_stage, self._clock.now()
        )

    async def expire_offer(self, application_id: UUID) -> bool:
        application = await self._repository.get(application_id)
        if not application.expire_offer(self._clock.now()):
            return False
        await self._store(application, causation_id=None)
        return True

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
                terms = command.offer
                application.present_offer(
                    Offer(
                        kind=terms.kind,
                        amount=Money.of(terms.amount),
                        term_months=terms.term_months,
                        rate=terms.rate,
                        monthly_payment=Money.of(terms.monthly_payment),
                        schedule_type=terms.schedule_type,
                        conditions=tuple(terms.conditions),
                        expires_at=terms.expires_at,
                        decision_id=command.decision_id,
                    ),
                    DecisionSummary(
                        outcome="APPROVE" if terms.kind == "as_requested" else "COUNTER_OFFER",
                        client_explanation=command.client_explanation,
                        improvement_hints=tuple(command.improvement_hints),
                        alternative_product_code=command.alternative_product_code,
                    ),
                    now,
                )
                return True
            case contracts.RejectApplication():
                application.reject(
                    DecisionSummary(
                        outcome="REJECT",
                        client_explanation=command.client_explanation,
                        improvement_hints=tuple(command.improvement_hints),
                        alternative_product_code=command.alternative_product_code,
                    ),
                    now,
                )
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

    async def _store(self, application: CreditApplication, causation_id: UUID | None) -> None:
        await self._repository.save(application)
        for event in application.pull_events():
            await self._outbox.add(
                to_contract(event),
                key=application.id,
                correlation_id=application.id,
                causation_id=causation_id,
            )
