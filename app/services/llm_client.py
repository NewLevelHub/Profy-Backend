"""Thin OpenAI client for structured (JSON-schema-constrained) completions.

Callers pass chat messages plus a JSON schema and get back a parsed dict whose
shape the model was forced to follow (OpenAI Structured Outputs, strict mode).
Every failure — disabled, network, timeout, bad status, refusal, unparseable —
raises LLMError so callers can fall back deterministically. Cost is bounded by
a single retry, an output token cap, and a request timeout.
"""
import json
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# USD per token, for cost logging only — approximate, check OpenAI's pricing
# page for current numbers. Keyed by model prefix so LLM_MODEL can change
# without the log silently reporting the wrong model's cost. Falls back to
# gpt-4o-mini pricing (cheapest) for an unlisted model, logged as a warning.
_PRICING_PER_TOKEN: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15 / 1_000_000, 0.60 / 1_000_000),
    "gpt-4.1-mini": (0.40 / 1_000_000, 1.60 / 1_000_000),
    "gpt-4o": (2.50 / 1_000_000, 10.00 / 1_000_000),
    "gpt-4.1": (2.00 / 1_000_000, 8.00 / 1_000_000),
}

_MAX_ATTEMPTS = 2  # 1 initial + 1 retry


class LLMError(Exception):
    """Any failure talking to the LLM (disabled, network, timeout, bad response)."""


def is_enabled() -> bool:
    return settings.LLM_ENABLED and bool(settings.LLM_API_KEY)


def _pricing_for(model: str) -> tuple[float, float]:
    # Dict order matters: "-mini" variants are listed before their base model
    # so e.g. "gpt-4o-mini" (which startswith "gpt-4o" too) matches itself first.
    for prefix, pricing in _PRICING_PER_TOKEN.items():
        if model.startswith(prefix):
            return pricing
    logger.warning("No pricing entry for model=%s, cost log will be inaccurate", model)
    return _PRICING_PER_TOKEN["gpt-4o-mini"]


def _log_usage(usage: dict[str, Any] | None) -> None:
    if not usage:
        return
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cost_per_input, cost_per_output = _pricing_for(settings.LLM_MODEL)
    cost = prompt_tokens * cost_per_input + completion_tokens * cost_per_output
    logger.info(
        "LLM usage: model=%s prompt=%s completion=%s ~$%.5f",
        settings.LLM_MODEL, prompt_tokens, completion_tokens, cost,
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
) -> dict[str, Any]:
    """Return the model's JSON object, constrained to `schema`. Raises LLMError on failure.

    `timeout` and `max_tokens` default to the global settings; long generations
    (the direction roadmap) override them — the defaults are sized for short
    completions and a big plan simply cannot finish inside them."""
    if not is_enabled():
        raise LLMError("LLM disabled or API key missing")

    payload = {
        "model": settings.LLM_MODEL,
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
    async with httpx.AsyncClient(timeout=timeout or settings.LLM_TIMEOUT) as client:
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                # str(exc) is empty for timeouts — keep the class name or the log says nothing.
                last_error = LLMError(f"request failed: {type(exc).__name__}: {exc}")
                continue  # transient — retry
            # 5xx is transient (retry); other non-200 is terminal (don't spend again).
            if response.status_code >= 500:
                last_error = LLMError(f"status {response.status_code}")
                continue
            if response.status_code != 200:
                raise LLMError(f"status {response.status_code}: {response.text[:300]}")

            data = response.json()
            _log_usage(data.get("usage"))
            return _parse_content(data)

    raise last_error or LLMError("unknown error")
