"""Telegram bot for specialists (ТЗ §4.6, B6): call reminders 24 h and 1 h
before, in the chat the specialist linked from Profile.

Off until `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` and
`TELEGRAM_WEBHOOK_SECRET` are set (`settings.telegram_enabled`): the routes
answer «disabled», the reminder check does not start, Profile hides the card.

- `client` — the Bot API calls (sendMessage, setWebhook);
- `links` — «Подключить Telegram»: a one-time deep link, the bot's `/start`;
- `reminders` — the background check, started from `app.main.lifespan`.

Turning it on: create the bot in @BotFather, put the three settings in the
server env, restart the API, run `scripts/telegram_set_webhook.py` once.
"""
