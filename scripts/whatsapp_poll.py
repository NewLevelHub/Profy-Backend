"""Run the WhatsApp intake locally, without a webhook (app/services/whatsapp/).

Green API reaches a webhook only over public HTTPS, so on a laptop this
script takes the queued notifications instead (receiveNotification), hands
them to the same intake as the webhook, and deletes them. Never on a server:
the server uses the webhook (scripts/whatsapp_set_webhook.py).

    docker compose exec api python -u scripts/whatsapp_poll.py --setup   # once: queue instead of webhook
    docker compose exec api python -u scripts/whatsapp_poll.py

GREEN_API_* must be in .env and the API restarted. With a personal number
linked, set WHATSAPP_TEST_NUMBERS: other chats are skipped (and deleted from
the queue without being stored).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.database import async_session  # noqa: E402
from app.services.whatsapp import intake  # noqa: E402
from app.services.whatsapp.green_api import GreenApi  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("whatsapp_poll")

# The notifications the CRM takes (and nothing else, so the queue stays short).
NOTIFICATIONS = {
    "incomingWebhook": "yes",
    "outgoingMessageWebhook": "yes",
    "outgoingAPIMessageWebhook": "yes",
    "outgoingWebhook": "yes",
    "stateWebhook": "no",
    "deviceWebhook": "no",
    "incomingCallWebhook": "no",
    "pollMessageWebhook": "no",
    "editedMessageWebhook": "no",
    "deletedMessageWebhook": "no",
}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--setup", action="store_true", help="switch the instance to the queue (no webhook URL)")
    args = parser.parse_args()
    if not settings.whatsapp_enabled:
        print("GREEN_API_ID_INSTANCE and GREEN_API_TOKEN_INSTANCE must be set.")
        return 1
    green = GreenApi()
    print("instance:", await green.state())
    if args.setup:
        print("settings:", await green.set_settings(webhookUrl="", webhookUrlToken="", **NOTIFICATIONS))
        print("Green API applies settings within a few minutes.")
        return 0
    if settings.WHATSAPP_TEST_NUMBERS:
        print("test mode: only", settings.WHATSAPP_TEST_NUMBERS)
    while True:
        try:
            got = await green.receive()
        except Exception as error:  # keep polling through a network blip
            logger.warning("receive failed: %s", type(error).__name__)
            await asyncio.sleep(5)
            continue
        if got is None:
            continue
        receipt_id, body = got
        try:
            async with async_session() as db:
                stored = await intake.handle(db, green.parse(body))
            logger.info("%s → stored %s", body.get("typeWebhook"), stored)
        except Exception:
            logger.exception("intake failed")
        await green.delete(receipt_id)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
