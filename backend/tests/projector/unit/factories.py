from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from src.modules.projector.domain.read_models import ApplicationOverview, QueueItem

T0 = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def overview(**changes: Any) -> ApplicationOverview:
    row = ApplicationOverview(
        application_id=uuid4(),
        organization_id=uuid4(),
        number="КР-2026-000001",
        product_code="UNSECURED",
        product_name="Кредит без залога",
        company_name="ООО «Ромашка»",
        inn="7701234567",
        amount=Decimal("3000000"),
        term_months=24,
        status="in_review",
        client_stage=None,
        action_required="none",
        offer_amount=None,
        offer_rate=None,
        submitted_at=T0,
        updated_at=T0,
        source_version=3,
    )
    return replace(row, **changes)


def queue_item(**changes: Any) -> QueueItem:
    item = QueueItem(
        task_id=uuid4(),
        application_id=uuid4(),
        task_type="manual_review",
        candidate_role="underwriter",
        status="open",
        assignee_id=None,
        due_at=T0 + timedelta(hours=4),
        created_at=T0,
        source_version=0,
    )
    return replace(item, **changes)
