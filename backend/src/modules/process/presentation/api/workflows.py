from fastapi import APIRouter
from fastapi.responses import Response

from src.modules.process.presentation.dependencies import (
    CanRead,
    ListWorkflowsDep,
    WorkflowDiagramDep,
)
from src.modules.process.presentation.schemas.workflows import WorkflowOut

router = APIRouter(tags=["process"])


@router.get("/workflows", response_model=list[WorkflowOut], dependencies=CanRead)
async def list_workflows(use_case: ListWorkflowsDep) -> list[WorkflowOut]:
    return [WorkflowOut.model_validate(workflow) for workflow in use_case.execute()]


@router.get("/workflows/{code}/diagram", dependencies=CanRead)
async def workflow_diagram(code: str, use_case: WorkflowDiagramDep) -> Response:
    """BPMN XML for bpmn-js; highlight `visited_node_ids` from /processes."""
    return Response(content=use_case.execute(code), media_type="application/xml")
