"""Thin OpenAI client for structured (JSON-schema-constrained) completions.

Callers pass chat messages plus a JSON schema and get back a parsed dict whose
shape the model was forced to follow (OpenAI Structured Outputs, strict mode).
Every failure — disabled, network, timeout, bad status, refusal, unparseable —
raises LLMError so callers can fall back deterministically. Cost is bounded by
a single retry, an output token cap, and a request timeout.
"""
import asyncio
import json
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 429 (rate limit) is retryable, not terminal — OpenAI TPM limits are easy to
# hit with a few dense calls. Sleep for the server-suggested delay (capped) and
# try again, on a small budget separate from the normal attempt count.
_MAX_429_RETRIES = 4
_MAX_429_SLEEP = 20.0


def _retry_after_seconds(response: httpx.Response) -> float:
    raw = response.headers.get("retry-after")
    if raw:
        try:
            return min(float(raw), _MAX_429_SLEEP)
        except ValueError:
            pass
    return 5.0

# USD per token, input/output — for cost logging only. Keep in sync with
# OpenAI's published pricing; an unlisted model still logs token counts, just
# without a $ figure, rather than silently reporting someone else's price.
_PRICING_PER_MODEL: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15 / 1_000_000, 0.60 / 1_000_000),
    "gpt-4.1": (2.00 / 1_000_000, 8.00 / 1_000_000),
    "gpt-4o": (2.50 / 1_000_000, 10.00 / 1_000_000),
}

_MAX_ATTEMPTS = 2  # 1 initial + 1 retry


class LLMError(Exception):
    """Any failure talking to the LLM (disabled, network, timeout, bad response)."""


def is_enabled() -> bool:
    return settings.LLM_ENABLED and bool(settings.LLM_API_KEY)


def _log_usage(model: str, usage: dict[str, Any] | None) -> None:
    if not usage:
        return
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    pricing = _PRICING_PER_MODEL.get(model)
    if pricing is None:
        logger.info(
            "LLM usage: model=%s prompt=%s completion=%s cost=unknown "
            "(add %s to _PRICING_PER_MODEL)",
            model, prompt_tokens, completion_tokens, model,
        )
        return
    cost_per_input, cost_per_output = pricing
    cost = prompt_tokens * cost_per_input + completion_tokens * cost_per_output
    logger.info(
        "LLM usage: model=%s prompt=%s completion=%s ~$%.5f",
        model, prompt_tokens, completion_tokens, cost,
    )


def _parse_content(data: dict[str, Any]) -> dict[str, Any]:
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"unexpected response shape: {exc}") from exc

    if message.get("refusal"):
        raise LLMError(f"model refusal: {message['refusal']}")

    try:
        return json.loads(message["content"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise LLMError(f"invalid JSON content: {exc}") from exc


async def complete_json(
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
    *,
    timeout: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Return the model's JSON object, constrained to `schema`. Raises LLMError on failure.

    `timeout` and `max_tokens` default to the global settings; long generations
    (both roadmap generators) override them — the defaults are sized for short
    completions and a big plan simply cannot finish inside them. `model` likewise
    defaults to the global cheap model; the roadmap generators pass a stronger
    one (`settings.LLM_ROADMAP_MODEL`) since they're the densest, highest-value
    output in the app."""
    if not is_enabled():
        raise LLMError("LLM disabled or API key missing")

    resolved_model = model or settings.LLM_MODEL
    payload = {
        "model": resolved_model,
        "messages": messages,
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
    }
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{settings.LLM_BASE_URL}/chat/completions"

    last_error: LLMError | None = None
    attempt = 0
    rate_limit_retries = 0
    async with httpx.AsyncClient(timeout=timeout or settings.LLM_TIMEOUT) as client:
        while attempt < _MAX_ATTEMPTS:
            try:
                response = await client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                # str(exc) is empty for timeouts — keep the class name or the log says nothing.
                last_error = LLMError(f"request failed: {type(exc).__name__}: {exc}")
                attempt += 1
                continue  # transient — retry
            # 5xx is transient (retry); other non-200 is terminal (don't spend again).
            if response.status_code >= 500:
                last_error = LLMError(f"status {response.status_code}")
                attempt += 1
                continue
            if response.status_code == 429:
                # Rate limit — retryable, on its own budget (does not consume a
                # normal attempt), sleeping for the server-suggested delay.
                last_error = LLMError("status 429: rate limited")
                if rate_limit_retries >= _MAX_429_RETRIES:
                    raise last_error
                rate_limit_retries += 1
                delay = _retry_after_seconds(response)
                logger.warning(
                    "LLM 429 (rate limit), retry %s/%s after %.1fs",
                    rate_limit_retries, _MAX_429_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                continue
            if response.status_code != 200:
                raise LLMError(f"status {response.status_code}: {response.text[:300]}")

            data = response.json()
            _log_usage(resolved_model, data.get("usage"))
            return _parse_content(data)

    raise last_error or LLMError("unknown error")
