"""PRO-338 Ф1.9 — full content for the `boyko_empathy` instrument: all 36
canonical items of V.V. Boyko's "Диагностика уровня эмпатических
способностей" + the 6-channel scoring key. Source:
docs/psych/new-tests-content-sources.md (Ф0.1 content audit, "Пробел 2" —
closed 2026-09-15, full 36-item structure, text verified against
Райгородский Д.Я. «Практическая психодиагностика» 2001, с. 486-490 against
Бойко В.В. 1996 original).

The ticket's own text (Тикеты-новые-тесты/02-Фаза1-Лёгкие-тесты.md §1.Г
Ф1.9) carries ~31 of 36 items and is marked "BLOCKED on Ф0.1" — that premise
is stale, Ф0.1 already closed this gap (items 32-36 were missing from a
digitization/OCR error on double-sided source forms, restored from
Райгородский). The 6-channel key below matches the ticket's own key table
verbatim; only the item texts were incomplete there.

Binary Да/Нет scale (Ф0.5's YES_NO_SCALE on the frontend). Keyed direction
lives on each item right here in the bank (`keyed`: "yes"/"no" — every item
counts, there are no buffer/filler items in this instrument, unlike Elers),
not a DB column — the future scoring service resolves it via
`Question.order` against this file, same pattern eysenck_service.py /
elers_bank.py established, consistent with the Ф0.8 "content+order only"
decision.
"""

# order 511-546 — right after elers (470-510), contiguous within the
# "Дополнительные тесты" block.
_TEXTS = [
    "У меня есть привычка внимательно изучать лица и поведение людей, чтобы понять их характер, наклонности, способности.",
    "Если окружающие проявляют признаки нервозности, я обычно остаюсь спокойным.",
    "Я больше верю доводам своего рассудка, чем интуиции.",
    "Я считаю вполне уместным для себя интересоваться домашними проблемами сослуживцев.",
    "Я могу легко войти в доверие к человеку, если потребуется.",
    "Обычно я с первой же встречи угадываю «родственную душу» в новом человеке.",
    "Я из любопытства обычно завожу разговор о жизни, работе, политике со случайными попутчиками в поезде, самолете.",
    "Я теряю душевное равновесие, если окружающие чем-то угнетены.",
    "Моя интуиция — более надежное средство понимания окружающих, чем знания или опыт.",
    "Проявлять любопытство к внутреннему миру другой личности — бестактно.",
    "Часто своими словами я обижаю близких мне людей, не замечая того.",
    "Я легко могу представить себя каким-либо животным, ощутить его повадки и состояния.",
    "Я редко рассуждаю о причинах поступков людей, которые имеют ко мне непосредственное отношение.",
    "Я редко принимаю близко к сердцу проблемы своих друзей.",
    "Обычно за несколько дней я чувствую: что-то должно случиться с близким мне человеком, и ожидания оправдываются.",
    "В общении с деловыми партнерами обычно стараюсь избегать разговоров о личном.",
    "Иногда близкие упрекают меня в черствости, невнимании к ним.",
    "Мне легко удается копировать интонацию, мимику людей, подражая им.",
    "Мой любопытный взгляд часто смущает новых партнеров.",
    "Чужой смех обычно заражает меня.",
    "Часто, действуя наугад, я тем не менее нахожу правильный подход к человеку.",
    "Плакать от счастья глупо.",
    "Я способен полностью слиться с любимым человеком, как бы растворившись в нем.",
    "Мне редко встречались люди, которых я понимал бы без лишних слов.",
    "Я невольно или из любопытства часто подслушиваю разговоры посторонних людей.",
    "Я могу оставаться спокойным, даже если все вокруг меня волнуются.",
    "Мне проще подсознательно почувствовать сущность человека, чем понять его, «разложив по полочкам».",
    "Я спокойно отношусь к мелким неприятностям, которые случаются у кого-либо из членов семьи.",
    "Мне было бы трудно задушевно, доверительно беседовать с настороженным, замкнутым человеком.",
    "У меня творческая натура — поэтическая, художественная, артистичная.",
    "Я без особого любопытства выслушиваю исповеди новых знакомых.",
    "Я расстраиваюсь, если вижу плачущего человека.",
    "Мое мышление больше отличается конкретностью, строгостью, последовательностью, чем интуицией.",
    "Когда друзья начинают говорить о своих неприятностях, я предпочитаю перевести разговор на другую тему.",
    "Если я вижу, что у кого-то из близких плохо на душе, то обычно воздерживаюсь от расспросов.",
    "Мне трудно понять, почему пустяки могут так сильно огорчать людей.",
]

assert len(_TEXTS) == 36, f"Boyko empathy must have exactly 36 canonical items, got {len(_TEXTS)}"

# Key, verbatim from docs/psych/new-tests-content-sources.md — item numbers
# are 1-based, matching _TEXTS' position (item N = _TEXTS[N-1]). Every item
# belongs to exactly one of 6 channels; no buffer items in this instrument.
_CHANNELS: dict[str, dict[str, set[int]]] = {
    "rational": {"yes": {1, 7, 19, 25}, "no": {13, 31}},
    "emotional": {"yes": {8, 20, 32}, "no": {2, 14, 26}},
    "intuitive": {"yes": {9, 15, 21, 27}, "no": {3, 33}},
    "attitudes": {"yes": {4}, "no": {10, 16, 22, 28, 34}},
    "penetration": {"yes": {5}, "no": {11, 17, 23, 29, 35}},
    "identification": {"yes": {6, 12, 18, 30}, "no": {24, 36}},
}

_CHANNEL_OF: dict[int, str] = {
    n: channel for channel, keyed in _CHANNELS.items() for ns in keyed.values() for n in ns
}
_KEYED: dict[int, str] = {
    n: direction for channel, keyed in _CHANNELS.items() for direction, ns in keyed.items() for n in ns
}

assert set(_CHANNEL_OF.keys()) == set(range(1, 37)), "every item 1-36 must belong to exactly one channel"
for _channel, _keyed in _CHANNELS.items():
    assert len(_keyed["yes"]) + len(_keyed["no"]) == 6, f"channel {_channel} must have exactly 6 items"

QUESTIONS: list[dict] = [
    {
        "order": 511 + i,
        "text": text,
        "age_tier": "senior",
        "channel": _CHANNEL_OF[i + 1],
        "keyed": _KEYED[i + 1],
    }
    for i, text in enumerate(_TEXTS)
]
