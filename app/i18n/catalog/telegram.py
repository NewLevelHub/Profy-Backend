"""Telegram bot messages to specialists (app/services/telegram/).

In the specialist's own `users.locale`, like the emails. `{when}` is the
call's Almaty date and time (the `when` phrase), `{call}` one of the `call_*` phrases,
`{student}` the student's name from the handoff card. The link to the
specialist's «Созвоны» is a button (`open_calls`), or the `calls_line`
where Telegram takes no button (a local http address).
"""

RU = {
    "linked": "Готово: Telegram подключён к Profile. Сюда придут напоминания о созвонах — за сутки и за час.",
    "link_invalid": "Ссылка устарела или уже использована. Откройте «Подключить Telegram» в Profile ещё раз.",
    "start_without_code": "Чтобы получать напоминания о созвонах, откройте «Подключить Telegram» в Profile → «Созвоны».",
    "stopped": "Telegram отключён от Profile — напоминаний больше не будет.",
    "call_intro30": "первый созвон (30 минут)",
    "call_main60": "разбор отчёта (1 час)",
    "student_unknown": "ученик",
    "when": "{date} в {time}",
    "reminder_day": "Напоминание: {when} — {call}, {student}.",
    "reminder_hour": "Через час, {when} — {call}, {student}.",
    "open_calls": "Открыть «Созвоны»",
    "calls_line": "Созвоны: {url}",
}

KK = {
    "linked": "Дайын: Telegram Profile-ға қосылды. Мұнда қоңыраулар туралы еске салғыштар келеді — бір тәулік және бір сағат бұрын.",
    "link_invalid": "Сілтеменің мерзімі өтті немесе ол пайдаланылды. Profile-да «Telegram қосу» түймесін қайта ашыңыз.",
    "start_without_code": "Қоңыраулар туралы еске салғыштар алу үшін Profile → «Қоңыраулар» бөлімінде «Telegram қосу» түймесін ашыңыз.",
    "stopped": "Telegram Profile-дан ажыратылды — еске салғыштар енді келмейді.",
    "call_intro30": "бірінші қоңырау (30 минут)",
    "call_main60": "есепті талдау (1 сағат)",
    "student_unknown": "оқушы",
    "when": "{date}, {time}",
    "reminder_day": "Еске салу: {when} — {call}, {student}.",
    "reminder_hour": "Бір сағаттан кейін, {when} — {call}, {student}.",
    "open_calls": "«Қоңыраулар» бөлімін ашу",
    "calls_line": "Қоңыраулар: {url}",
}
