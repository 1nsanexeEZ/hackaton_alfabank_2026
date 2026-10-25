from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.types import SafeString
from src.modules.process.presentation.schemas.processes import ProcessOut


class TaskResultIn(BaseModel):
    """The underwriter's decision; the comment is mandatory."""

    decision: Literal["approve", "counter_offer", "reject", "request_info"]
    amount: Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=2)] | None = None
    term_months: int | None = Field(default=None, ge=1, le=360)
    rate: Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)] | None = None
    conditions: list[Annotated[SafeString, Field(max_length=300)]] = Field(
        default_factory=list, max_length=20
    )
    requested_documents: list[Annotated[str, Field(pattern=r"^[a-z][a-z_]*$")]] = Field(
        default_factory=list, max_length=20
    )
    comment: Annotated[SafeString, Field(min_length=1, max_length=2000)]

    def as_result(self) -> dict[str, Any]:
        result: dict[str, Any] = self.model_dump(mode="json", exclude_none=True)
        return result


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    process_id: UUID
    application_id: UUID
    type: str
    candidate_role: str
    status: str
    assignee_id: UUID | None
    form_schema: dict[str, Any]
    created_at: datetime
    due_at: datetime | None
    overdue: bool
    result: dict[str, Any] | None
    completed_by: UUID | None
    # Why the task is opened beyond the decision's reasons: the previous manual decision
    # was not accepted, a step failed or repeated too often. null — the decision sent it.
    reason: str | None


class TaskDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task: TaskOut
    process: ProcessOut | None
