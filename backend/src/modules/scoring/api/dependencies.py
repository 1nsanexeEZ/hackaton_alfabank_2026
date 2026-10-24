from typing import Annotated

from fastapi import Depends, Request

from src.core.infrastructure.database.session import DbSession
from src.modules.scoring.application.model_versions import ModelVersions
from src.modules.scoring.infrastructure.config_loader import PdModelDocuments
from src.modules.scoring.infrastructure.repository import (
    SqlAlchemyModelVersionRepository,
    SqlAlchemyScoringRepository,
)


def get_model_versions(request: Request, session: DbSession) -> ModelVersions:
    return ModelVersions(
        SqlAlchemyModelVersionRepository(session), PdModelDocuments(), request.app.state.clock
    )


def get_scoring_history(session: DbSession) -> SqlAlchemyScoringRepository:
    return SqlAlchemyScoringRepository(session)


ModelVersionsDep = Annotated[ModelVersions, Depends(get_model_versions)]
ScoringHistoryDep = Annotated[SqlAlchemyScoringRepository, Depends(get_scoring_history)]
