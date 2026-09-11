"""Конфиг упражнений МАК (PRO-315). Источник — `psych-block-spec.md §C1`
(коды/стимулы/режимы) + `тестМак.md` §8 (форма полей). ТОЛЬКО E1 активно —
PRO-312 (финальный список/порядок/режимы у психолога) и PRO-313 (тексты
упражнений) ещё не закрыты; E2–E6 заведены строками с `active=False`,
чтобы схема была видна целиком и включалась без миграции, когда придёт
финальный контент. Наводящий вопрос E1 — черновой, не вычитан психологом
(демо для встречи 2026-09-11, не финальный контент)."""

MAC_EXERCISES = [
    {
        "order": 1,
        "code": "E1",
        "title": "Точка отсчёта",
        "stimulus_question": "Моя профессиональная ситуация сейчас",
        "draw_mode": "blind",
        "spread_size": None,
        "pick_count": 1,
        "followup_questions": [
            "Опиши, что ты видишь на карте.",
            "Чем это похоже на твою ситуацию сейчас?",
        ],
        "subjects": None,
        "active": True,
    },
    {
        "order": 2,
        "code": "E2",
        "title": "Блоки",
        "stimulus_question": "Что мешает мне выбрать / сменить профессию",
        "draw_mode": "blind",
        "spread_size": None,
        "pick_count": 1,
        "followup_questions": ["Опиши, что ты видишь на карте.", "Как это связано с тем, что тебе мешает?"],
        "subjects": None,
        "active": False,  # ждёт PRO-312/313
    },
    {
        "order": 3,
        "code": "E3",
        "title": "Образ будущего",
        "stimulus_question": "Моя идеальная профессия / кем я хочу быть",
        "draw_mode": "blind",
        "spread_size": None,
        "pick_count": 1,
        "followup_questions": ["Опиши, что ты видишь на карте.", "Как это связано с твоим будущим?"],
        "subjects": None,
        "active": False,
    },
    {
        "order": 4,
        "code": "E4",
        "title": "Сравнение перспектив",
        "stimulus_question": "Что у меня хорошо получается",
        "draw_mode": "open",
        "spread_size": 8,
        "pick_count": 1,
        "followup_questions": ["Опиши, что ты видишь на карте.", "Почему выбрал(а) именно эту карту?"],
        "subjects": ["self", "parents", "teachers", "friends"],
        "active": False,  # родительский вход (filled_by=parent) не подключён
    },
    {
        "order": 5,
        "code": "E5",
        "title": "Ресурс",
        "stimulus_question": "Что или кто мне поможет сделать выбор",
        "draw_mode": "blind",
        "spread_size": None,
        "pick_count": 1,
        "followup_questions": ["Опиши, что ты видишь на карте.", "Кто или что тебе в этом помогает?"],
        "subjects": None,
        "active": False,
    },
    {
        "order": 6,
        "code": "E6",
        "title": "Формула профессии",
        "stimulus_question": "Рассортируй карточки: моё / не моё",
        "draw_mode": "open",
        "spread_size": 30,
        "pick_count": 5,
        "followup_questions": ["Почему это «моё»?"],
        "subjects": None,
        "active": False,  # текстовая колода (не изобразительная) — отдельный набор карт
    },
]
