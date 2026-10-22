"""DTOs of the neighbours as bff reads them. Internal data carries recognizable
markers, so a test can check that none of it reaches a client screen."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from src.applications.facade import ApplicationCardDTO, DecisionSummaryDTO, OfferDTO
from src.decision.facade import (
    DecisionDTO,
    DecisionTermsDTO,
    LimitsDTO,
    PreApprovedOfferDTO,
    RuleTraceDTO,
)
from src.enrichment.facade import (
    CashflowForecastDTO,
    CashflowMonthDTO,
    CashflowProjectionDTO,
    CreditHistoryDTO,
    EnrichmentSnapshotDTO,
    ObligationDTO,
    SourceErrorDTO,
)
from src.notifications.facade import FeedItemDTO, NewsItemDTO
from src.process.facade import ProcessViewDTO, StepViewDTO, UserTaskDTO
from src.projector.facade import (
    ApplicationOverviewDTO,
    BackofficeMetricsDTO,
    DailyMetricsDTO,
    QueueItemDTO,
    TimelineEntryDTO,
)
from src.scoring.facade import FactorDTO, ScoringResultDTO
from tests.fakes.builders import NOW

# Markers of data the client must never see.
REASON_CODE = "SCORE_BELOW_AUTO_THRESHOLD"
RULE_NAME = "rule_debt_load_limit"
FACTOR_CODE = "factor_tax_arrears"
BKI_CREDITOR = "Банк Кредитор-БКИ"
BANK_TIMELINE_TITLE = "Скоринг: 612 баллов, грейд C"
PRE_APPROVED_BASIS = "score 640 on turnover"
INTERNAL_MARKERS = (
    REASON_CODE,
    RULE_NAME,
    FACTOR_CODE,
    BKI_CREDITOR,
    BANK_TIMELINE_TITLE,
    PRE_APPROVED_BASIS,
)

_ACTION = {"info_requested": "info", "offer_ready": "offer", "signing": "sign"}


def offer(kind: str = "as_requested", amount: str = "3000000", **overrides: Any) -> OfferDTO:
    dto = OfferDTO(
        kind=kind,  # type: ignore[arg-type]
        amount=Decimal(amount),
        term_months=24,
        rate=Decimal("19.5"),
        monthly_payment=Decimal("152000.00"),
        schedule_type="annuity",
        conditions=("Поручительство собственника",),
        expires_at=NOW + timedelta(days=5),
        decision_id=uuid4(),
    )
    return replace(dto, **overrides)


def overview(card: ApplicationCardDTO, **overrides: Any) -> ApplicationOverviewDTO:
    row = ApplicationOverviewDTO(
        application_id=card.id,
        organization_id=card.organization_id,
        number=card.number,
        product_code=card.product_code,
        product_name=f"Кредит {card.product_code}",
        amount=card.request.amount if card.request else None,
        term_months=card.request.term_months if card.request else None,
        status=card.status,
        client_stage=card.client_stage,
        action_required=_ACTION.get(card.status, "none"),  # type: ignore[arg-type]
        offer_amount=card.offer.amount if card.offer else None,
        offer_rate=card.offer.rate if card.offer else None,
        submitted_at=card.submitted_at,
        updated_at=card.updated_at,
    )
    return replace(row, **overrides)


def decision(application_id: UUID, outcome: str = "APPROVE", **overrides: Any) -> DecisionDTO:
    dto = DecisionDTO(
        id=uuid4(),
        application_id=application_id,
        policy_version="2026.10",
        key_rate=Decimal("16"),
        outcome=outcome,  # type: ignore[arg-type]
        terms=DecisionTermsDTO(
            amount=Decimal("3000000"),
            term_months=24,
            rate=Decimal("19.5"),
            monthly_payment=Decimal("152000.00"),
            schedule_type="annuity",
            conditions=(),
            expires_at=NOW + timedelta(days=5),
        ),
        alternative_product_code=None,
        reason_codes=(REASON_CODE,),
        client_explanation="Одобрено на запрошенных условиях",
        improvement_hints=("Подключите эквайринг",),
        requested_info=None,
        rule_trace=(RuleTraceDTO(rule=RULE_NAME, matched=True, detail="DTI 0.41 > 0.40"),),
        limits=LimitsDTO(
            by_revenue=Decimal("5000000"), by_ltv=None, by_capacity=Decimal("3200000")
        ),
        decided_by_type="auto",
        decided_by_id=None,
        override_of=None,
        comment=None,
        decided_at=NOW,
    )
    return replace(dto, **overrides)


def decision_summary() -> DecisionSummaryDTO:
    return DecisionSummaryDTO(
        outcome="APPROVE",
        client_explanation="Одобрено на запрошенных условиях",
        improvement_hints=(),
    )


def scoring_result(application_id: UUID) -> ScoringResultDTO:
    return ScoringResultDTO(
        id=uuid4(),
        application_id=application_id,
        model_version="scorecard-1",
        score=612,
        grade="C",
        factors=(
            FactorDTO(
                code=FACTOR_CODE, value="120000", bin="arrears", points=-40, direction="negative"
            ),
        ),
        flags=("cash_gap_2026_12",),
        data_completeness=Decimal("0.9"),
        computed_at=NOW,
    )


def enrichment_snapshot(application_id: UUID, organization_id: UUID) -> EnrichmentSnapshotDTO:
    return EnrichmentSnapshotDTO(
        id=uuid4(),
        application_id=application_id,
        organization_id=organization_id,
        collected_at=NOW,
        sources_ok=("egrul", "bki", "statement"),
        sources_failed=(SourceErrorDTO(source="fns", code="timeout", message="ФНС не ответила"),),
        egrul=None,
        fns=None,
        bki=CreditHistoryDTO(
            obligations=(
                ObligationDTO(
                    creditor=BKI_CREDITOR,
                    kind="loan",
                    amount=Decimal("1000000"),
                    balance=Decimal("400000"),
                    monthly_payment=Decimal("50000"),
                    opened_at=date(2025, 1, 10),
                    closes_at=None,
                    overdue_days=0,
                ),
            ),
            inquiries_last_30d=2,
            has_active_overdue=False,
            max_overdue_days_12m=0,
            total_monthly_payments=Decimal("50000"),
        ),
        cashflow=CashflowForecastDTO(
            months_history=(
                CashflowMonthDTO(
                    month="2026-09",
                    inflow=Decimal("900000"),
                    outflow=Decimal("850000"),
                    net=Decimal("50000"),
                    balance=Decimal("120000"),
                ),
            ),
            forecast=(CashflowProjectionDTO(month="2026-12", projected_balance=Decimal("-80000")),),
            gap_detected=True,
            gap_month="2026-12",
            gap_amount=Decimal("80000"),
            annual_inflow=Decimal("10800000"),
            revenue_confirmed=True,
            method="seasonal_naive",
            statement_document_ids=(),
        ),
    )


def process_view(application_id: UUID) -> ProcessViewDTO:
    return ProcessViewDTO(
        process_id=uuid4(),
        application_id=application_id,
        workflow_code="standard",
        workflow_version=1,
        status="waiting",
        current_node_id="underwriter_review",
        client_stage="Заявка у специалиста",
        visited_node_ids=("start", "fetch_enrichment", "calculate_score", "make_decision"),
        steps=(
            StepViewDTO(
                node_id="calculate_score",
                step_code="calculate_score",
                kind="async",
                iteration=1,
                started_at=NOW,
                finished_at=NOW,
                outcome="done",
            ),
        ),
        started_at=NOW,
    )


def user_task(application_id: UUID, **overrides: Any) -> UserTaskDTO:
    task = UserTaskDTO(
        id=uuid4(),
        process_id=uuid4(),
        application_id=application_id,
        node_id="underwriter_review",
        type="underwriter_review",
        candidate_role="underwriter",
        assignee_id=None,
        status="open",
        form_schema={"type": "object", "required": ["outcome", "comment"]},
        created_at=NOW,
        due_at=NOW + timedelta(hours=4),
    )
    return replace(task, **overrides)


def queue_item(card: ApplicationCardDTO, **overrides: Any) -> QueueItemDTO:
    item = QueueItemDTO(
        task_id=uuid4(),
        application_id=card.id,
        number=card.number,
        company_name=card.org_snapshot.name if card.org_snapshot else "",
        inn=card.org_snapshot.inn if card.org_snapshot else "",
        product_code=card.product_code,
        amount=card.request.amount if card.request else None,
        score=612,
        risk_grade="C",
        cash_gap=True,
        routing_reasons=("Сумма выше лимита автоматического решения",),
        due_at=NOW + timedelta(hours=4),
        overdue=False,
        assignee_id=None,
        status="open",
        created_at=NOW,
    )
    return replace(item, **overrides)


def timeline_entry(
    application_id: UUID,
    title: str,
    audience: str = "client",
    kind: str = "stage",
    minutes: int = 0,
    details: dict[str, Any] | None = None,
) -> TimelineEntryDTO:
    return TimelineEntryDTO(
        id=uuid4(),
        application_id=application_id,
        at=NOW + timedelta(minutes=minutes),
        kind=kind,  # type: ignore[arg-type]
        title=title,
        audience=audience,  # type: ignore[arg-type]
        details=details or {},
    )


def feed_item(
    organization_id: UUID, application_id: UUID | None = None, read: bool = False
) -> FeedItemDTO:
    return FeedItemDTO(
        id=uuid4(),
        type="stage_changed",
        title="Заявка: проверяем данные о компании",
        body="Это займёт несколько минут",
        link=None,
        priority="low",
        action_required=False,
        organization_id=organization_id,
        application_id=application_id,
        created_at=NOW,
        read_at=NOW if read else None,
    )


def news_item() -> NewsItemDTO:
    return NewsItemDTO(
        id=uuid4(),
        title="Льготная ставка для общепита",
        body="До конца года",
        published_at=NOW,
        relevance=("ОКВЭД 56",),
    )


def pre_approved(product_code: str = "UNSECURED", amount: str = "4000000") -> PreApprovedOfferDTO:
    return PreApprovedOfferDTO(
        product_code=product_code,
        max_amount=Decimal(amount),
        rate_from=Decimal("18.5"),
        term_max_months=36,
        valid_until=date(2026, 12, 31),
        basis=PRE_APPROVED_BASIS,
    )


def metrics(date_from: date, date_to: date) -> BackofficeMetricsDTO:
    row = DailyMetricsDTO(
        day=date_from,
        product_code="UNSECURED",
        submitted=10,
        approved=6,
        counter_offers=1,
        rejected=2,
        manual_reviews=1,
        auto_decisions=9,
        avg_time_to_decision_sec=95.0,
    )
    return BackofficeMetricsDTO(date_from, date_to, (row,), 10, 10, 0.9, 95.0)
