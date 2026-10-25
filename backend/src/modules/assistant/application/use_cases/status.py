from src.modules.assistant.application.dto.assistant import StatusDTO
from src.modules.assistant.application.interfaces.language_model import LanguageModelSetup


class GetStatusUseCase:
    """Who answers now: the model (`llm`) or the templates (`rules`)."""

    def __init__(self, setup: LanguageModelSetup) -> None:
        self._setup = setup

    async def execute(self) -> StatusDTO:
        model = self._setup.model
        reachable = await model.ping() if model else False
        return StatusDTO(
            enabled=model is not None,
            mode="llm" if reachable else "rules",
            provider=self._setup.provider,
            model=model.model if model else None,
            host=model.host if model else None,
            reachable=reachable,
            reason=self._setup.disabled_reason,
        )
