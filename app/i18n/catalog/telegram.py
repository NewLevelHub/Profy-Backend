"""Telegram bot messages to specialists (app/services/telegram/): call
reminders, the weekly «заполните расписание» (`week_reminder`, `{week}` as
in the email) and «отчёт ждёт проверки» (`review_pending`).

In the specialist's own `users.locale`, like the emails. `{when}` is the
call's Almaty date and time (the `when` phrase), `{call}` one of the `call_*` phrases,
`{student}` the student's name from the handoff card. The link into
Profile is the button under the message (`open_calls`, `open_schedule`).
"""

RU = {
    "linked": "Готово: Telegram подключён к Profile. Сюда придут напоминания о созвонах — за сутки и за час, о новых отчётах на проверку и о расписании на следующую неделю.",
    "link_invalid": "Ссылка устарела или уже использована. Откройте «Подключить Telegram» в Profile ещё раз.",
    "start_without_code": "Чтобы получать напоминания о созвонах, откройте «Подключить Telegram» в Profile → «Созвоны».",
    "stopped": "Telegram отключён от Profile — напоминаний больше не будет.",
    "call_intro30": "первый созвон (30 минут)",
    "call_main60": "разбор отчёта (1 час)",
    "student_unknown": "ученик",
    "when": "{date} в {time}",
    "reminder_day": "Напоминание: {when} — {call}, {student}.",
    "reminder_hour": "Через час, {when} — {call}, {student}.",
    "open_calls": "Перейти в «Созвоны»",
    "week_reminder": "Расписание на неделю {week} ещё не заполнено. Отметьте свободное время и нажмите «Готово, неделя заполнена».",
    "open_schedule": "Перейти в «Расписание»",
    "review_pending": "{student}: тест пройден — отчёт уже доступен для проверки.",
    "review_after_call": "Опубликовать его можно после второго созвона — разбора.",
    "open_report": "Перейти к отчёту",
}

KK = {
    "linked": "Дайын: Telegram Profile-ға қосылды. Мұнда қоңыраулар туралы — бір тәулік және бір сағат бұрын, тексеруге келген жаңа есептер және келесі аптаның кестесі туралы хабарлар келеді.",
    "link_invalid": "Сілтеменің мерзімі өтті немесе ол пайдаланылды. Profile-да «Telegram қосу» түймесін қайта ашыңыз.",
    "start_without_code": "Қоңыраулар туралы еске салғыштар алу үшін Profile → «Қоңыраулар» бөлімінде «Telegram қосу» түймесін ашыңыз.",
    "stopped": "Telegram Profile-дан ажыратылды — еске салғыштар енді келмейді.",
    "call_intro30": "бірінші қоңырау (30 минут)",
    "call_main60": "есепті талдау (1 сағат)",
    "student_unknown": "оқушы",
    "when": "{date}, {time}",
    "reminder_day": "Еске салу: {when} — {call}, {student}.",
    "reminder_hour": "Бір сағаттан кейін, {when} — {call}, {student}.",
    "open_calls": "«Қоңыраулар» бөліміне өту",
    "week_reminder": "{week} аптасының кестесі әлі толтырылмаған. Бос уақытыңызды белгілеп, «Дайын, апта толтырылды» түймесін басыңыз.",
    "open_schedule": "«Кесте» бөліміне өту",
    "review_pending": "{student}: тест тапсырылды — есеп тексеруге қолжетімді.",
    "review_after_call": "Оны екінші қоңыраудан — талдаудан кейін жариялауға болады.",
    "open_report": "Есепке өту",
}
