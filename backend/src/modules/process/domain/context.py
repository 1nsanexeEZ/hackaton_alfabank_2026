"""What the process knows about the application: references to results of
other modules and the facts gateways branch on. Gateway conditions may read
any field listed in CONDITION_FIELDS."""

import dataclasses
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass
class ProcessContext:
    application_id: UUID
    organization_id: UUID
    product_code: str
    # check_completeness
    complete: bool | None = None
    missing_fields: tuple[str, ...] = ()
    missing_documents: tuple[str, ...] = ()
    # fetch_enrichment
    enrichment_snapshot_id: UUID | None = None
    sources_failed: tuple[str, ...] = ()
    cash_gap_flag: bool | None = None
    # check_stop_factors: a stop factor matched — the decision is made without scoring
    stopped: bool | None = None
    # assess_collateral
    collateral_value: Decimal | None = None
    # calculate_score
    scoring_result_id: UUID | None = None
    risk_grade: str | None = None
    score_flags: tuple[str, ...] = ()
    # make_decision / record_manual_decision
    decision_id: UUID | None = None
    outcome: str | None = None
    decided_by: str | None = None
    # The decision as the client-facing commands need it (offer, explanation...).
    decision: dict[str, Any] | None = None
    # underwriter_review
    last_task_id: UUID | None = None
    manual_result: dict[str, Any] | None = None
    manual_review_reason: str | None = None
    # waits
    info_requests_count: int = 0
    info_provided: bool = False
    offer_answer: str | None = None
    signed: bool = False
    # Last label sent to the client, so the same stage is not announced twice.
    last_client_stage: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def update(self, values: dict[str, Any]) -> None:
        for name, value in values.items():
            if name not in _FIELDS:
                raise KeyError(f"Unknown context field {name!r}")
            setattr(self, name, value)

    def as_mapping(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _FIELDS}


_FIELDS = frozenset(f.name for f in dataclasses.fields(ProcessContext))
CONDITION_FIELDS = _FIELDS - {"extra", "decision", "manual_result"}
