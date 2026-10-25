from collections import deque
from collections.abc import Callable
from uuid import UUID

from src.modules.assistant.application.interfaces.rate_limit import QuestionRateLimiter
from src.modules.assistant.domain.exceptions import TooManyQuestionsError


class InMemoryRateLimiter(QuestionRateLimiter):
    """Sliding window per account, in the process: one backend serves the stand."""

    def __init__(self, limit: int, window_s: float, now: Callable[[], float]) -> None:
        self._limit = limit
        self._window_s = window_s
        self._now = now
        self._hits: dict[UUID, deque[float]] = {}

    def hit(self, account_id: UUID) -> None:
        now = self._now()
        hits = self._hits.setdefault(account_id, deque())
        while hits and hits[0] <= now - self._window_s:
            hits.popleft()
        if len(hits) >= self._limit:
            raise TooManyQuestionsError(max(1, int(hits[0] + self._window_s - now) + 1))
        hits.append(now)
