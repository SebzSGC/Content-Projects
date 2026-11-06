"""Smart HTTP retry rules: retry 429/5xx/timeouts with backoff+jitter, fail fast on 400/401, raise PayloadTooLargeError on 413."""

from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, Optional, TypeVar

import httpx

from .limiter import ProviderRateLimiter

T = TypeVar("T")


class ProviderError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FatalApiError(ProviderError):
    """400, 401, 403, invalid credentials or malformed request — never retried."""


class PayloadTooLargeError(ProviderError):
    """413 Payload Too Large (or pre-flight size exceeded) — triggers finer audio chunking."""


class TransientApiError(ProviderError):
    """429, 5xx, network drops or timeouts — retried with exponential backoff + jitter."""

    def __init__(self, message: str, status_code: Optional[int] = None, retry_after: Optional[float] = None) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after = retry_after


def parse_retry_after(headers: httpx.Headers) -> Optional[float]:
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.1, float(raw.strip()))
    except ValueError:
        return None


def classify_http_error(provider_name: str, resp: httpx.Response) -> ProviderError:
    code = resp.status_code
    body_preview = resp.text[:400].strip()
    if code == 413:
        return PayloadTooLargeError(f"{provider_name} rechazó el tamaño del archivo (413): {body_preview}", status_code=413)
    if code == 429:
        return TransientApiError(
            f"{provider_name} límite de tasa alcanzado (429): {body_preview}",
            status_code=429,
            retry_after=parse_retry_after(resp.headers),
        )
    if code >= 500:
        return TransientApiError(f"{provider_name} error temporal ({code}): {body_preview}", status_code=code)
    return FatalApiError(f"{provider_name} error no recuperable ({code}): {body_preview}", status_code=code)


async def execute_with_retry(
    fn: Callable[[], Awaitable[T]],
    limiter: Optional[ProviderRateLimiter] = None,
    estimated_units: float = 1.0,
    max_attempts: int = 5,
    base_delay_sec: float = 0.8,
) -> T:
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            if limiter is not None:
                async with limiter.acquire(estimated_units=estimated_units):
                    res = await fn()
                await limiter.on_success()
                return res
            return await fn()
        except (FatalApiError, PayloadTooLargeError):
            raise
        except TransientApiError as exc:
            last_exc = exc
            if exc.status_code == 429 and limiter is not None:
                await limiter.on_rate_limited(exc.retry_after)
            if attempt >= max_attempts:
                break
            exp = base_delay_sec * (2 ** (attempt - 1))
            jitter = random.uniform(0.5, 1.35) * exp
            wait_s = max(jitter, exc.retry_after or 0.0)
            await asyncio.sleep(min(30.0, wait_s))
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = TransientApiError(f"Error de red/timeout ({type(exc).__name__}): {exc}")
            if attempt >= max_attempts:
                break
            wait_s = random.uniform(0.5, 1.35) * (base_delay_sec * (2 ** (attempt - 1)))
            await asyncio.sleep(min(20.0, wait_s))

    assert last_exc is not None
    raise last_exc
