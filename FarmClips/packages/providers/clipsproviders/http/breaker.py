"""Circuit breaker with automatic failover to backup provider (Deepgram <-> Groq, Gemini <-> OpenAI-compat)."""

from __future__ import annotations

import time
from typing import Awaitable, Callable, Generic, Optional, TypeVar

from .retry import PayloadTooLargeError, ProviderError

A = TypeVar("A")
R = TypeVar("R")


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 3, open_seconds: float = 180.0) -> None:
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.open_seconds = open_seconds
        self.consecutive_failures = 0
        self.opened_until: float = 0.0

    @property
    def is_open(self) -> bool:
        return time.monotonic() < self.opened_until

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_until = 0.0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.opened_until = time.monotonic() + self.open_seconds


class FailoverRouter(Generic[A]):
    """Routes calls to primary adapter; opens circuit after repeated failures and switches to backup adapter."""

    def __init__(
        self,
        primary: A,
        backup: Optional[A] = None,
        failure_threshold: int = 3,
        open_seconds: float = 180.0,
    ) -> None:
        self.primary = primary
        self.backup = backup
        self.primary_breaker = CircuitBreaker("primary", failure_threshold, open_seconds)
        self.backup_breaker = CircuitBreaker("backup", failure_threshold, open_seconds)

    async def call(self, invoke: Callable[[A], Awaitable[R]]) -> R:
        candidates = []
        if not self.primary_breaker.is_open:
            candidates.append((self.primary, self.primary_breaker))
        if self.backup is not None and not self.backup_breaker.is_open:
            candidates.append((self.backup, self.backup_breaker))
        if not candidates:
            # Half-open probe on primary if both circuits tripped
            candidates.append((self.primary, self.primary_breaker))

        last_err: Optional[Exception] = None
        for adapter, breaker in candidates:
            try:
                out = await invoke(adapter)
                breaker.record_success()
                return out
            except PayloadTooLargeError:
                # 413 needs finer audio splitting at the caller level, not provider failover
                raise
            except ProviderError as exc:
                breaker.record_failure()
                last_err = exc
                continue
        assert last_err is not None
        raise last_err
