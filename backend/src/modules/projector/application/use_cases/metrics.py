"""Read of the back office metrics."""

from datetime import date

from src.modules.projector.application.dto.metrics import BackofficeMetricsDTO, DailyMetricsDTO
from src.modules.projector.application.interfaces.repositories import ReadModelQueries
from src.modules.projector.domain.metrics import MetricsSummary


class GetBackofficeMetricsUseCase:
    def __init__(self, read_models: ReadModelQueries) -> None:
        self._read_models = read_models

    async def execute(self, date_from: date, date_to: date) -> BackofficeMetricsDTO:
        cells = await self._read_models.metrics_between(date_from, date_to)
        summary = MetricsSummary.of(cells)
        return BackofficeMetricsDTO(
            date_from=date_from,
            date_to=date_to,
            rows=tuple(
                DailyMetricsDTO(
                    day=c.day,
                    product_code=c.product_code,
                    submitted=c.submitted,
                    approved=c.approved,
                    counter_offers=c.counter_offers,
                    rejected=c.rejected,
                    manual_reviews=c.manual_reviews,
                    auto_decisions=c.auto_decisions,
                    avg_time_to_decision_sec=c.avg_time_to_decision_sec,
                )
                for c in cells
            ),
            submitted=summary.submitted,
            decided=summary.decided,
            auto_decision_share=summary.auto_decision_share,
            avg_time_to_decision_sec=summary.avg_time_to_decision_sec,
        )
