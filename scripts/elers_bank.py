"""PRO-338 Ф1.7 — full content for the `elers` instrument: all 41 canonical
items of Elers' "Диагностика личности на мотивацию к успеху" (уровень
притязаний) + the scoring key. Source: docs/psych/new-tests-content-sources.md
(Ф0.1 content audit, "Пробел 1" — closed 2026-09-15, canonical 41-item
version, verified against Ильин 2000 / Фетискин-Козлов-Мануйлов 2002 /
Райгородский 2001).

41, not 40 — the audit resolved the spec's discrepancy: some sources drop
the last item to 40 by a copy error, but the scoring key scores item 41
regardless, and it's the item that anchors the "too high" motivation band.

Wording note (2026-09-18): the canonical instrument was normed on working
adults, so several items originally referenced "работа"/"коллеги"/
"руководитель"/"отпуск" (job, colleagues, boss, vacation) — jarring for a
14-18 y/o respondent who has none of those. Items 3, 10, 12, 13, 15, 18, 19,
25, 26, 27, 28, 29, 32, 33, 34, 37, 39 were lightly reworded to a school
equivalent (работа→дело/занятия/учёба, коллеги→одноклассники,
руководитель→учитель, отпуск→каникулы, etc.), preserving each item's
achievement-motivation meaning and its Да/Нет key direction unchanged — only
vocabulary changed, not what the item measures. This is a deliberate
deviation from the literal published adult text; flag for the project
psychologist to confirm the substitutions preserve intent.

Binary Да/Нет scale (Ф0.5's YES_NO_SCALE on the frontend). Keyed direction
lives on each item right here in the bank (`keyed`: "yes"/"no"/"buffer" —
buffer items are shown to the respondent like any other but never scored,
so which ones don't count is never revealed on the wire), not a DB column
— the future scoring service (Ф1.8: sum of key matches + band thresholds)
resolves it via `Question.order` against this file, same pattern
eysenck_service.py established in Ф1.5, consistent with the Ф0.8
"content+order only" decision (no scoring metadata was ever written to the
DB for this epic's new instruments).
"""

# order 470-510 — right after eysenck (410-466), contiguous within the
# "Дополнительные тесты" block.
_TEXTS = [
    "Если между двумя вариантами есть выбор, его лучше сделать быстрее, чем откладывать на потом.",
    "Если замечаю, что не могу на все 100% выполнить задание, я легко раздражаюсь.",
    "Когда я берусь за дело, это выглядит так, будто я ставлю на карту все.",
    "Если возникает проблемная ситуация, чаще всего я принимаю решение одним из последних.",
    "Если два дня подряд у меня нет дела, я теряю покой.",
    "В некоторые дни мои успехи ниже средних.",
    "Я более требователен к себе, чем к другим.",
    "Я доброжелательнее других.",
    "Если я отказываюсь от сложного задания, впоследствии сурово осуждаю себя, так как знаю, что в нем я добился бы успеха.",
    "В процессе занятий я нуждаюсь в небольших паузах для отдыха.",
    "Усердие — это не основная моя черта.",
    "Мои достижения в учёбе не всегда одинаковы.",
    "Другое дело привлекает меня больше того, которым я занят.",
    "Порицание стимулирует меня сильнее похвалы.",
    "Знаю, что одноклассники считают меня организованным человеком.",
    "Преодоление препятствий способствует тому, что мои решения становятся более категоричными.",
    "На моем честолюбии легко сыграть.",
    "Если я занимаюсь без вдохновения, это обычно заметно.",
    "Выполняя задания, я не рассчитываю на помощь других.",
    "Иногда я откладываю на завтра то, что должен сделать сегодня.",
    "Нужно полагаться только на самого себя.",
    "В жизни немного вещей важнее денег.",
    "Если мне предстоит выполнить важное задание, я никогда не думаю ни о чем другом.",
    "Я менее честолюбив, чем многие другие.",
    "В конце каникул я обычно радуюсь, что скоро пойду в школу.",
    "Если я расположен к делу, выполняю его лучше и умелее, чем другие.",
    "Мне проще и легче общаться с людьми, способными усердно заниматься делом.",
    "Когда мне нечем заняться, мне не по себе.",
    "Ответственные поручения мне приходится выполнять чаще других.",
    "Если мне приходится принимать решение, стараюсь делать это как можно лучше.",
    "Иногда друзья считают меня ленивым.",
    "Мои успехи в какой-то мере зависят от одноклассников.",
    "Противодействовать воле учителя бессмысленно.",
    "Иногда не знаешь, какое задание придется выполнять.",
    "Если у меня что-то не ладится, я становлюсь нетерпеливым.",
    "Обычно я обращаю мало внимания на свои достижения.",
    "Если я занимаюсь вместе с другими, у меня получается лучше, чем у других.",
    "Не довожу до конца многое, за что берусь.",
    "Завидую людям, не загруженным делами.",
    "Не завидую тем, кто стремится к власти и положению.",
    "Если я уверен, что стою на правильном пути, для доказательства своей правоты пойду на крайние меры.",
]

assert len(_TEXTS) == 41, f"Elers must have exactly 41 canonical items, got {len(_TEXTS)}"

# Key, verbatim from docs/psych/new-tests-content-sources.md — item numbers
# are 1-based, matching _TEXTS' position (item N = _TEXTS[N-1]).
_YES = {2, 3, 4, 5, 7, 8, 9, 10, 14, 15, 16, 17, 21, 22, 25, 26, 27, 28, 29, 30, 32, 37, 41}
_NO = {6, 13, 18, 20, 24, 31, 36, 38, 39}
_BUFFER = {1, 11, 12, 19, 23, 33, 34, 35, 40}

_KEY: dict[int, str] = {
    **{n: "yes" for n in _YES},
    **{n: "no" for n in _NO},
    **{n: "buffer" for n in _BUFFER},
}

assert set(_KEY.keys()) == set(range(1, 42)), "every item 1-41 must have exactly one key entry"
assert len(_YES) == 23, "Да key must have 23 items"
assert len(_NO) == 9, "Нет key must have 9 items"
assert len(_BUFFER) == 9, "buffer must have 9 items"

QUESTIONS: list[dict] = [
    {
        "order": 470 + i,
        "text": text,
        "age_tier": "senior",
        "keyed": _KEY[i + 1],
    }
    for i, text in enumerate(_TEXTS)
]
