from uuid import UUID

from fastapi import APIRouter

from src.modules.process.presentation.dependencies import CanRead, GetProcessDep
from src.modules.process.presentation.schemas.processes import ProcessOut

router = APIRouter(tags=["process"])


@router.get("/processes/{application_id}", response_model=ProcessOut, dependencies=CanRead)
async def get_process(application_id: UUID, use_case: GetProcessDep) -> ProcessOut:
    return ProcessOut.model_validate(await use_case.execute(application_id))
