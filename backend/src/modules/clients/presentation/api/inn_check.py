from fastapi import APIRouter

from src.modules.clients.presentation.dependencies import BackofficeAccess, CheckInnDep
from src.modules.clients.presentation.schemas.inn_check import InnCheckRead, InnCheckRequest

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("/inn-check", response_model=InnCheckRead)
async def check_inn(
    body: InnCheckRequest, _: BackofficeAccess, use_case: CheckInnDep
) -> InnCheckRead:
    """Check of a company by INN before an application — bank staff only (`backoffice.read`).
    The company need not be a client. ЕГРЮЛ/ЕГРИП past the cache, the tax service, Kontur and
    the bank stop list; `ogrn`, `kpp`, `name` from the client's documents are matched against
    the registry. A typo in the INN — `fail`, an unknown INN — `not_found`, both with 200;
    the registry did not answer — 503. Nothing is stored."""
    return InnCheckRead.model_validate(await use_case.execute(body.to_dto()))
