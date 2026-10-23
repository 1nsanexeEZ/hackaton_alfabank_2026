from uuid import UUID

from fastapi import APIRouter, Response, status

from src.modules.clients.presentation.dependencies import (
    ListFinancialReportsDep,
    ReadAccess,
    SubmitFinancialReportDep,
    UpdateAccess,
)
from src.modules.clients.presentation.schemas.financial_reports import (
    FinancialReportCreate,
    FinancialReportRead,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/{organization_id}/financial-reports", response_model=list[FinancialReportRead])
async def list_financial_reports(
    organization_id: UUID, access: ReadAccess, use_case: ListFinancialReportsDep
) -> list[FinancialReportRead]:
    reports = await use_case.execute(access, organization_id)
    return [FinancialReportRead.model_validate(report) for report in reports]


@router.post(
    "/{organization_id}/financial-reports",
    response_model=FinancialReportRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_financial_report(
    organization_id: UUID,
    data: FinancialReportCreate,
    access: UpdateAccess,
    use_case: SubmitFinancialReportDep,
    response: Response,
) -> FinancialReportRead:
    """Declared report for a period that is over. The same period again
    revises the report (200), a new one is created (201)."""
    report, created = await use_case.execute(access, organization_id, data.to_dto())
    if not created:
        response.status_code = status.HTTP_200_OK
    return FinancialReportRead.model_validate(report)
