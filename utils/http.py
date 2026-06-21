"""Async HTTP client with retries and proxy support."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from utils.proxy import ProxyRotator

logger = logging.getLogger("arb_scanner.http")


class AsyncHttpClient:
    def __init__(
        self,
        proxy_rotator: ProxyRotator | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.proxy_rotator = proxy_rotator
        self.timeout = timeout
        self.max_retries = max_retries

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            proxy = self.proxy_rotator.next() if self.proxy_rotator else None
            try:
                kwargs: dict[str, Any] = {"timeout": self.timeout, "follow_redirects": True}
                if proxy:
                    kwargs["proxy"] = proxy
                async with httpx.AsyncClient(**kwargs) as client:
                    response = await client.get(url, params=params, headers=headers)
                    if response.status_code == 429:
                        wait = min(2**attempt, 30)
                        logger.warning("Rate limited on %s, waiting %ss", url, wait)
                        await asyncio.sleep(wait)
                        continue
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code in (403, 503):
                    logger.warning("HTTP %s for %s (attempt %d)", exc.response.status_code, url, attempt)
                    await asyncio.sleep(attempt)
                    continue
                raise
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning("Request error for %s (attempt %d): %s", url, attempt, exc)
                await asyncio.sleep(attempt)
        raise RuntimeError(f"Failed after {self.max_retries} attempts: {url}") from last_error

    async def post(
        self,
        url: str,
        json: dict[str, Any] | list[Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        proxy = self.proxy_rotator.next() if self.proxy_rotator else None
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if proxy:
            kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**kwargs) as client:
            response = await client.post(url, json=json, headers=headers)
            response.raise_for_status()
            return response.json()
