"""Read-only Meta Marketing API client: the account's ads and their daily
insights. The token goes in the query string, as Graph API wants; neither it
nor a request URL is ever logged (httpx is kept at WARNING, see
app/services/telegram/client.py)."""

import asyncio
import json
import logging
from datetime import date
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

GRAPH = "https://graph.facebook.com"
TIMEOUT = httpx.Timeout(30.0)
CONVERSATION = "onsite_conversion.messaging_conversation_started_7d"
# Rate limit codes (doc §5): wait and try again.
RATE_LIMITED = {4, 17, 32, 613, 80004}
RETRIES = 3

INSIGHT_FIELDS = ",".join((
    "date_start", "campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name",
    "spend", "impressions", "reach", "clicks", "inline_link_clicks", "actions",
))
AD_FIELDS = "id,name,status,adset_id,campaign_id,adset{name},campaign{name},creative{id}"


class MetaError(Exception):
    """Graph API refused. `token_invalid` (code 190) is not retried: the
    token was revoked and the owner has to issue a new one."""

    def __init__(self, code: int | None, message: str):
        super().__init__(message)
        self.code = code

    @property
    def token_invalid(self) -> bool:
        return self.code == 190


def _base() -> str:
    return f"{GRAPH}/{settings.META_API_VERSION}"


async def _get_pages(path: str, params: dict[str, Any]) -> list[dict]:
    """Every page of a list answer, following `paging.next`."""
    url: str | None = f"{_base()}/{path}"
    query: dict[str, Any] | None = {**params, "access_token": settings.META_ACCESS_TOKEN}
    rows: list[dict] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while url:
            body = await _get(client, url, query)
            rows.extend(body.get("data", []))
            # `next` already carries every parameter, the token included.
            url, query = body.get("paging", {}).get("next"), None
    return rows


async def _get(client: httpx.AsyncClient, url: str, query: dict[str, Any] | None) -> dict:
    for attempt in range(RETRIES):
        try:
            response = await client.get(url, params=query)
        except httpx.HTTPError as error:
            if attempt == RETRIES - 1:
                raise MetaError(None, f"network: {type(error).__name__}") from None
            await asyncio.sleep(5 * (attempt + 1))
            continue
        body = response.json() if response.content else {}
        error = body.get("error") if isinstance(body, dict) else None
        if response.status_code == 200 and not error:
            return body
        code = (error or {}).get("code")
        message = (error or {}).get("message") or f"HTTP {response.status_code}"
        if code in RATE_LIMITED and attempt < RETRIES - 1:
            await asyncio.sleep(60 * (attempt + 1))
            continue
        raise MetaError(code, message)
    raise MetaError(None, "retries exhausted")


async def ads() -> list[dict]:
    return await _get_pages(f"{settings.META_AD_ACCOUNT_ID}/ads", {"fields": AD_FIELDS, "limit": 200})


async def insights(since: date, until: date) -> list[dict]:
    """One row per ad per day between the dates (the account's zone, Almaty)."""
    return await _get_pages(
        f"{settings.META_AD_ACCOUNT_ID}/insights",
        {
            "level": "ad",
            "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
            "time_increment": 1,
            "fields": INSIGHT_FIELDS,
            "limit": 500,
        },
    )


def conversations(row: dict) -> int:
    for action in row.get("actions") or ():
        if action.get("action_type") == CONVERSATION:
            return int(float(action.get("value") or 0))
    return 0
