"""Run the Telegram bot locally, without a webhook (app/services/telegram/).

Telegram reaches a webhook only over public HTTPS, so on a laptop this
script asks Telegram for the bot's messages instead (getUpdates) and handles
them like the webhook would. It also runs the call reminder check every
`--every` seconds. Never on a server: getUpdates and a webhook exclude each
other, and the server uses the webhook.

    docker compose exec api python scripts/telegram_poll.py
    docker compose exec api python scripts/telegram_poll.py --every 15

The bot settings (TELEGRAM_*) must be in .env and the API restarted.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.database import async_session  # noqa: E402
from app.services.telegram import client, links, reminders  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("telegram_poll")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--every", type=int, default=60, help="seconds between reminder checks")
    args = parser.parse_args()
    if not settings.telegram_enabled:
        print("TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME and TELEGRAM_WEBHOOK_SECRET must all be set.")
        return 1

    offset: int | None = None
    checked = 0.0
    logger.info("Polling @%s; reminders every %ss. Ctrl+C to stop.", settings.TELEGRAM_BOT_USERNAME, args.every)
    while True:
        if time.monotonic() - checked >= args.every:
            async with async_session() as db:
                sent = await reminders.send_due_reminders(db)
            if sent:
                logger.info("Reminders sent: %s", sent)
            checked = time.monotonic()
        try:
            updates = await client.get_updates(offset, timeout=min(25, args.every))
        except Exception as error:  # a network hiccup must not stop the bot
            logger.warning("getUpdates failed: %s", error)
            await asyncio.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            text = (update.get("message") or {}).get("text", "")
            logger.info("Update %s: %s", update["update_id"], text.split(" ", 1)[0])
            async with async_session() as db:
                await links.handle_update(db, update)


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass
