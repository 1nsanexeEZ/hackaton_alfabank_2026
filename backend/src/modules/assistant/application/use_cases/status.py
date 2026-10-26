from src.modules.assistant.application.dto.assistant import StatusDTO
from src.modules.assistant.application.interfaces.language_model import (
    LanguageModelSetup,
    ModelReachability,
)


class GetStatusUseCase:
    """Who answers now: the model (`llm`) or the templates (`rules`). Answers at once: whether
    the model is up is the last background check (`ModelReachability`)."""

    def __init__(self, setup: LanguageModelSetup, reachability: ModelReachability) -> None:
        self._setup = setup
        self._reachability = reachability

    async def execute(self) -> StatusDTO:
        model = self._setup.model
        reachable = await self._reachability.reachable(model) if model else False
        return StatusDTO(
            enabled=model is not None,
            mode="llm" if reachable else "rules",
            provider=self._setup.provider,
            model=model.model if model else None,
            host=model.host if model else None,
            reachable=reachable,
            reason=self._setup.disabled_reason,
        )
