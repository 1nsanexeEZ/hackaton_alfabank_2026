from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.modules.assistant.domain.views import (
    ApplicationView,
    ClientDecisionView,
    PaymentView,
    ProductView,
    Viewer,
)


class ContextSource(Protocol):
    """What the assistant reads from the neighbours. Each read of an application
    checks that the viewer may see it."""

    async def get_application(self, viewer: Viewer, application_id: UUID) -> ApplicationView:
        """Raises ApplicationNotFoundError: no such application or not the viewer's."""
        ...

    async def list_applications(self, viewer: Viewer) -> list[ApplicationView]:
        """The applications of the viewer's companies; empty for bank staff."""
        ...

    async def get_client_decision(
        self, viewer: Viewer, application_id: UUID
    ) -> ClientDecisionView | None: ...

    async def list_products(self) -> list[ProductView]: ...

    def calculate_payment(
        self, amount: Decimal, term_months: int, rate: Decimal, repayment: str
    ) -> PaymentView:
        """The system's single payment formula. Raises ValueError out of range."""
        ...
