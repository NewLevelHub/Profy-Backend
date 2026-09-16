"""PRO-338 Ф1.10 — full content for the `kondash_anxiety` instrument: all 40
canonical items of O. Kondash's «Шкала личностной тревожности для
учащихся» in A.M. Prikhozhan's adaptation (форма Б, 13-16 лет — matches the
epic's senior-only scope), 4 subscales. Source:
docs/psych/new-tests-content-sources.md (Ф0.1 content audit, "Пробел 3" —
closed 2026-09-16, full 40-item text supplied and verified by the project's
consulting psychologist; a prior 2026-09-15 version of this gap had 11/40
items as a working reconstruction, now replaced with the confirmed
original — see that doc's "Расхождение и решение" for the correction,
including one item (№14) whose earlier reconstructed text was wrong).

NOT a Да/Нет instrument — respondent rates each situation 0-4 (Нет=0 …
Очень=4, 5-point scale, own frontend scale, see Ф1.10's own frontend wiring
in LikertPage.tsx/constants.ts), reusing the same 0..5-bounded `answer_value`
field professional_types_abilities widened the floor for (app/schemas/
response.py) — no further backend schema change needed.

Score = raw sum per subscale (no keyed direction, no buffer items — every
item counts at face value, unlike Elers). Subscale is resolved via
`Question.order` against this file's own data (no DB column), same
"content+order only" decision as every other Ф1 instrument bank."""

# order 547-586 — right after boyko_empathy (511-546), contiguous within the
# "Дополнительные тесты" block.
_TEXTS = [
    "Отвечать у доски.",
    "Требуется обратиться с вопросом, просьбой к незнакомому человеку.",
    "Участвовать в соревнованиях, конкурсах, олимпиадах.",
    "Слышать заклятия.",
    "Разговаривать с директором школы.",
    "Сравнивать себя с другими.",
    "Учитель делает тебе замечание.",
    "Тебя критикуют, в чем-то упрекают.",
    "На тебя смотрят, когда ты что-нибудь делаешь (наблюдают за тобой во время работы, решения задачи).",
    "Видеть плохие или «вещие» сны.",
    "Писать контрольную работу, выполнять тест по какому-нибудь предмету.",
    "После контрольной, теста учитель называет отметки.",
    "У тебя что-то не получается.",
    "Мысль о том, что неосторожным поступком можно навлечь на себя гнев потусторонних сил.",
    "На тебя не обращают внимания.",
    "Ждешь родителей с родительского собрания.",
    "Тебе грозит неуспех, провал.",
    "Слышать смех за своей спиной.",
    "Не понимать объяснений учителя.",
    "Думаешь о своем будущем.",
    "Слышать предсказания о космических катастрофах.",
    "Выступать перед большой аудиторией.",
    "Слышать, что какой-то человек «напускает порчу» на других.",
    "Ссориться с родителями.",
    "Участвовать в психологическом эксперименте.",
    "На тебя смотрят, как на маленького.",
    "На экзамене тебе достался 13-й билет.",
    "На уроке учитель неожиданно задает тебе вопрос.",
    "Думаешь о своей привлекательности для девочек.",
    "Не можешь справиться с домашним заданием.",
    "Оказаться в темноте, видеть неясные силуэты, слышать непонятные шорохи.",
    "Не соглашаешься с родителями.",
    "Берешься за новое дело.",
    "Разговаривать со школьным психологом.",
    "Думать о том, что тебя могут «сглазить».",
    "Замолчали, когда ты подошел.",
    "Общаться с человеком, похожим на мага, экстрасенса.",
    "Слушать, как кто-то говорит о своих любовных похождениях.",
    "Смотреться в зеркало.",
    "Кажется, что нечто непонятное, сверхъестественное может помешать тебе добиться желаемого.",
]

assert len(_TEXTS) == 40, f"Kondash anxiety must have exactly 40 canonical items, got {len(_TEXTS)}"

# Subscale, verbatim from docs/psych/new-tests-content-sources.md — item
# numbers are 1-based, matching _TEXTS' position (item N = _TEXTS[N-1]).
# Latin keys in code per project convention (avoid Cyrillic identifiers).
_SUBSCALES: dict[str, set[int]] = {
    "school": {1, 5, 7, 11, 12, 16, 19, 28, 30, 34},
    "self_esteem": {3, 6, 8, 13, 17, 20, 25, 29, 33, 39},
    "interpersonal": {2, 9, 15, 18, 22, 24, 26, 32, 36, 38},
    "magical": {4, 10, 14, 21, 23, 27, 31, 35, 37, 40},
}

_SUBSCALE_OF: dict[int, str] = {n: subscale for subscale, ns in _SUBSCALES.items() for n in ns}

assert set(_SUBSCALE_OF.keys()) == set(range(1, 41)), "every item 1-40 must belong to exactly one subscale"
for _subscale, _ns in _SUBSCALES.items():
    assert len(_ns) == 10, f"subscale {_subscale} must have exactly 10 items"

QUESTIONS: list[dict] = [
    {
        "order": 547 + i,
        "text": text,
        "age_tier": "senior",
        "subscale": _SUBSCALE_OF[i + 1],
    }
    for i, text in enumerate(_TEXTS)
]
