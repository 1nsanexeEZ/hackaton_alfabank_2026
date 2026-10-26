"""The admin's scoring overview in one call: the submitted applications with both models'
grades, data quality and the decision, three queries in all (applications, scoring results,
decisions) instead of a card per application."""

from collections import Counter

from src.modules.applications.facade import ApplicationsFacade, ApplicationSummaryDTO
from src.modules.bff.application.dto.scoring_overview import (
    GradeCountDTO,
    ScoredApplicationDTO,
    ScoringOverviewDTO,
    VersionCountDTO,
    ZonePairDTO,
)
from src.modules.bff.application.interfaces.neighbours import Neighbours
from src.modules.decision.facade import DecisionDTO, DecisionFacade
from src.modules.scoring.facade import ScoringFacade, ScoringResultDTO

# The counts are over at most this many latest submitted applications.
SUMMARY_MAX = 1000
GRADES = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J")
ZONES = ("green", "yellow", "red")
# Zones of a grade as the built-in policy sets them (policy_v10 `models.zones`).
GRADE_ZONE = (
    {g: "green" for g in "ABCD"}
    | {g: "yellow" for g in "EFG"}
    | {"H": "red", "I": "red", "J": "red"}
)
FINAL = frozenset({"APPROVE", "COUNTER_OFFER", "REJECT"})


class ScoringOverviewUseCase:
    def __init__(self, neighbours: Neighbours) -> None:
        self._n = neighbours

    async def execute(self, limit: int) -> ScoringOverviewDTO:
        applications = await self._n(ApplicationsFacade).list_submitted(SUMMARY_MAX)
        ids = [a.id for a in applications]
        results = await self._n(ScoringFacade).get_results(ids)
        decisions = await self._n(DecisionFacade).get_decisions(ids)
        rows = [_row(a, results.get(a.id), decisions.get(a.id)) for a in applications]
        scored = [r for r in rows if r.grade is not None]
        with_ml = [r for r in scored if r.ml_grade is not None]
        final = [r for r in rows if r.outcome in FINAL]
        grades_pd = Counter(r.grade for r in scored)
        grades_ml = Counter(r.ml_grade for r in with_ml)
        pairs = Counter((GRADE_ZONE[r.grade or ""], GRADE_ZONE[r.ml_grade or ""]) for r in with_ml)
        versions = (
            [("pd", results[r.application_id].model_version) for r in scored]
            + [
                ("ml", ml.model_version)
                for r in with_ml
                if (ml := results[r.application_id].ml) is not None
            ]
            + [("policy", d.policy_version) for d in decisions.values()]
        )
        return ScoringOverviewDTO(
            considered=len(rows),
            scored=len(scored),
            stopped_before_models=sum(
                1
                for r in rows
                if r.grade is None and any(c.startswith("STOP_") for c in r.reason_codes)
            ),
            with_ml=len(with_ml),
            models_agree=sum(1 for r in with_ml if not r.models_disagree),
            degraded=sum(1 for r in scored if r.quality == "degraded"),
            manual_review=sum(1 for r in rows if r.outcome == "MANUAL_REVIEW"),
            decided=len(final),
            decided_auto=sum(1 for r in final if r.decided_by_type == "auto"),
            by_grade=tuple(GradeCountDTO(g, grades_pd[g], grades_ml[g]) for g in GRADES),
            zones=tuple(ZonePairDTO(pd, ml, pairs[(pd, ml)]) for pd in ZONES for ml in ZONES),
            versions=tuple(
                VersionCountDTO(kind, version, count)  # type: ignore[arg-type]
                for (kind, version), count in sorted(Counter(versions).items())
            ),
            items=tuple(rows[:limit]),
        )


def _row(
    application: ApplicationSummaryDTO,
    result: ScoringResultDTO | None,
    decision: DecisionDTO | None,
) -> ScoredApplicationDTO:
    ml = result.ml if result is not None else None
    return ScoredApplicationDTO(
        application_id=application.id,
        number=application.number,
        company_name=application.company_name,
        product_code=application.product_code,
        amount=application.amount,
        status=application.status,
        submitted_at=application.submitted_at,
        score=result.score if result else None,
        grade=result.grade if result else None,
        pd_12m=result.pd_12m if result else None,
        ml_score=ml.score if ml else None,
        ml_grade=ml.grade if ml else None,
        ml_pd_12m=ml.pd_12m if ml else None,
        ml_not_applicable=result.ml_not_applicable if result else None,
        quality=result.quality if result else None,
        models_disagree=bool(
            result and ml and GRADE_ZONE.get(result.grade) != GRADE_ZONE.get(ml.grade)
        ),
        outcome=decision.outcome if decision else None,
        decided_by_type=decision.decided_by_type if decision else None,
        reason_codes=decision.reason_codes if decision else (),
    )
