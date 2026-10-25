from typing import Protocol
from uuid import UUID


class QuestionRateLimiter(Protocol):
    def hit(self, account_id: UUID) -> None:
        """Counts a question. Raises TooManyQuestionsError over the budget."""
        ...
