"""Point the Telegram bot's updates at this API (app/services/telegram/).

Run once after the bot settings are in the server env, inside the API
container:

    docker compose exec api python scripts/telegram_set_webhook.py
    docker compose exec api python scripts/telegram_set_webhook.py --url https://dev.profile.newlevelhub.kz

The webhook is <url>/api/v1/telegram/webhook, `--url` defaults to
FRONTEND_URL (the API is served on the same domain). Telegram needs HTTPS.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.services.telegram import client  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=settings.FRONTEND_URL, help="the public https origin of the API")
    args = parser.parse_args()
    if not settings.telegram_enabled:
        print("TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME and TELEGRAM_WEBHOOK_SECRET must all be set.")
        return 1
    webhook = f"{args.url.rstrip('/')}/api/v1/telegram/webhook"
    if not webhook.startswith("https://"):
        print(f"Telegram accepts only an https webhook, got {webhook}")
        return 1
    answer = await client.set_webhook(webhook)
    print(f"{webhook}: {answer.get('description') or answer}")
    return 0 if answer.get("ok") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
