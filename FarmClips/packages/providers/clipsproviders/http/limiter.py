"""Triple-rule rate limiter per (provider, model): concurrency semaphore + RPM bucket + unit budget, with 429 adaptive throttling."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from typing import AsyncIterator, Deque, Optional, Tuple


class ProviderRateLimiter:
    def __init__(
        self,
        max_concurrency: int = 6,
        requests_per_minute: float = 60.0,
        max_units_per_window: float = 28_800.0,
        unit_window_sec: float = 3600.0,
    ) -> None:
        self._sem = asyncio.Semaphore(max(1, max_concurrency))
        self.base_rpm = max(1.0, requests_per_minute)
        self.rate_multiplier = 1.0
        self.max_units_per_window = max_units_per_window
        self.unit_window_sec = unit_window_sec

        self._lock = asyncio.Lock()
        self._req_times: Deque[float] = deque()
        self._unit_ledger: Deque[Tuple[float, float]] = deque()
        self._cooldown_until: float = 0.0

    @property
    def effective_rpm(self) -> float:
        return max(1.0, self.base_rpm * self.rate_multiplier)

    def _prune(self, now: float) -> None:
        while self._req_times and now - self._req_times[0] >= 60.0:
            self._req_times.popleft()
        while self._unit_ledger and now - self._unit_ledger[0][0] >= self.unit_window_sec:
            self._unit_ledger.popleft()

    async def _wait_for_budget(self, estimated_units: float) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                self._prune(now)

                wait_sec = 0.0
                if now < self._cooldown_until:
                    wait_sec = max(wait_sec, self._cooldown_until - now)

                eff_rpm = int(max(1, round(self.effective_rpm)))
                if len(self._req_times) >= eff_rpm:
                    wait_sec = max(wait_sec, 60.0 - (now - self._req_times[0]) + 0.05)

                used_units = sum(u for _, u in self._unit_ledger)
                if self._unit_ledger and used_units + estimated_units > self.max_units_per_window:
                    wait_sec = max(wait_sec, self.unit_window_sec - (now - self._unit_ledger[0][0]) + 0.05)

                if wait_sec <= 0.0:
                    self._req_times.append(now)
                    if estimated_units > 0:
                        self._unit_ledger.append((now, estimated_units))
                    return

            await asyncio.sleep(min(wait_sec, 5.0))

    async def on_rate_limited(self, retry_after_sec: Optional[float] = None) -> None:
        async with self._lock:
            self.rate_multiplier = max(0.15, self.rate_multiplier * 0.5)
            delay = retry_after_sec if (retry_after_sec is not None and retry_after_sec > 0) else 2.0
            self._cooldown_until = max(self._cooldown_until, time.monotonic() + delay)

    async def on_success(self, actual_extra_units: float = 0.0) -> None:
        async with self._lock:
            self.rate_multiplier = min(1.0, self.rate_multiplier + 0.1)
            if actual_extra_units > 0:
                self._unit_ledger.append((time.monotonic(), actual_extra_units))

    @asynccontextmanager
    async def acquire(self, estimated_units: float = 1.0) -> AsyncIterator[None]:
        async with self._sem:
            await self._wait_for_budget(estimated_units)
            yield
