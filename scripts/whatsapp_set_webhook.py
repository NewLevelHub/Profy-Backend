"""Point the Green API instance at this server's webhook (app/routers/whatsapp.py).

    docker compose exec api python scripts/whatsapp_set_webhook.py https://dev.profile.newlevelhub.kz

Sends GREEN_API_WEBHOOK_TOKEN as the webhookUrlToken and turns on the
notifications the CRM takes. Green API applies it within a few minutes.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.services.whatsapp.green_api import GreenApi  # noqa: E402
from scripts.whatsapp_poll import NOTIFICATIONS  # noqa: E402


async def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        print(__doc__)
        return 1
    if not (settings.whatsapp_enabled and settings.GREEN_API_WEBHOOK_TOKEN):
        print("GREEN_API_ID_INSTANCE, GREEN_API_TOKEN_INSTANCE and GREEN_API_WEBHOOK_TOKEN must be set.")
        return 1
    url = sys.argv[1].rstrip("/") + "/api/v1/whatsapp/webhook"
    green = GreenApi()
    print("instance:", await green.state())
    print("settings:", await green.set_settings(
        webhookUrl=url, webhookUrlToken=settings.GREEN_API_WEBHOOK_TOKEN, **NOTIFICATIONS
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
