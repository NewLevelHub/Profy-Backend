"""Assessment scoring: raw weights, normalization, and direction matching."""

from typing import Any

from app.models.question import Question

# Preference keys from the university block — not used in direction scoring.
PREFERENCE_KEYS = frozenset({
    "pref_country",
    "pref_lang",
    "pref_priority",
    "exam_readiness",
    "portfolio",
    "pref_format",
    "timeline",
    "specialty",
})

DIRECTIONS_MATRIX: dict[str, dict[str, dict[str, int]]] = {
    "IT и разработка": {
        "required": {"technology": 55, "logical": 45},
        "bonus": {"investigative": 15, "mathematical": 10},
    },
    "Искусственный интеллект": {
        "required": {"technology": 60, "mathematical": 55},
        "bonus": {"investigative": 15, "logical": 10},
    },
    "Data Science": {
        "required": {"mathematical": 55, "numbers": 50},
        "bonus": {"technology": 15, "investigative": 10},
    },
    "Дизайн / цифровое искусство": {
        "required": {"artistic": 60, "creative_think": 50},
        "bonus": {"technology": 15},
    },
    "Медицина / биология": {
        "required": {"science": 60, "helping_motiv": 45},
        "bonus": {"investigative": 15, "social": 10},
    },
    "Наука и исследования": {
        "required": {"science": 60, "investigative": 55},
        "bonus": {"logical": 15, "mathematical": 10},
    },
    "Психология / педагогика": {
        "required": {"social": 60, "helping_motiv": 50},
        "bonus": {"verbal": 15},
    },
    "Бизнес / предпринимательство": {
        "required": {"enterprising": 55, "leadership": 45},
        "bonus": {"strategic": 15, "business": 10},
    },
    "Финансы / экономика": {
        "required": {"numbers": 55, "conventional": 45},
        "bonus": {"mathematical": 15, "enterprising": 10},
    },
    "Право / госуправление": {
        "required": {"verbal": 55, "social": 45},
        "bonus": {"conventional": 10, "strategic": 10},
    },
    "Медиа / журналистика": {
        "required": {"verbal": 55, "artistic": 45},
        "bonus": {"social": 15, "media": 10},
    },
    "Инженерия / архитектура": {
        "required": {"spatial": 55, "realistic": 45},
        "bonus": {"systematic": 15, "science": 10},
    },
    "Маркетинг / реклама": {
        "required": {"enterprising": 50, "creative_think": 50},
        "bonus": {"media": 15, "social": 10},
    },
    "Экология / природа": {
        "required": {"nature": 60, "science": 45},
        "bonus": {"investigative": 10, "realistic": 10},
    },
    "Управление проектами": {
        "required": {"strategic": 55, "conscientiousness": 45},
        "bonus": {"leadership": 15, "systematic": 10},
    },
}

LIKERT_LABELS = [
    "Совсем не про меня",
    "Скорее не про меня",
    "Нейтрально",
    "Скорее про меня",
    "Точно про меня",
]


def is_likert_question(options: Any) -> bool:
    return isinstance(options, dict) and options.get("type") == "likert"


def get_likert_meta(options: Any) -> tuple[dict[str, int | float], bool]:
    weights = options.get("weights", {})
    reversed_scale = bool(options.get("reversed", False))
    return weights, reversed_scale


def apply_choice_weights(
    raw_scores: dict[str, Any],
    options: list[dict[str, Any]],
    selected_option_index: int,
) -> None:
    if selected_option_index < 0 or selected_option_index >= len(options):
        return
    weights = options[selected_option_index].get("weights", {})
    for category, weight in weights.items():
        if isinstance(weight, str):
            raw_scores[category] = weight
        elif isinstance(weight, (int, float)):
            raw_scores[category] = raw_scores.get(category, 0) + weight


def apply_likert_weights(
    raw_scores: dict[str, Any],
    options: dict[str, Any],
    selected_option_index: int,
) -> None:
    weights, reversed_scale = get_likert_meta(options)
    user_answer = selected_option_index + 1
    if user_answer < 1 or user_answer > 5:
        return
    score_value = (6 - user_answer) if reversed_scale else user_answer
    for category, weight in weights.items():
        if isinstance(weight, (int, float)):
            raw_scores[category] = raw_scores.get(category, 0) + score_value * weight


def apply_answer(
    raw_scores: dict[str, Any],
    question: Question,
    selected_option_index: int,
) -> None:
    if is_likert_question(question.options):
        apply_likert_weights(raw_scores, question.options, selected_option_index)
    elif isinstance(question.options, list):
        apply_choice_weights(raw_scores, question.options, selected_option_index)


def calculate_raw_scores(
    questions: dict[Any, Question],
    answers: list[tuple[Any, int]],
) -> dict[str, Any]:
    raw_scores: dict[str, Any] = {}
    for question_id, selected_option_index in answers:
        question = questions.get(question_id)
        if question is None:
            continue
        apply_answer(raw_scores, question, selected_option_index)
    return raw_scores


def normalize_scores(raw_scores: dict[str, Any]) -> dict[str, float]:
    if not raw_scores:
        return {}
    scoring_scores = {
        k: v for k, v in raw_scores.items()
        if k not in PREFERENCE_KEYS and not k.startswith("goal_")
    }
    if not scoring_scores:
        return {}
    max_score = max(scoring_scores.values())
    if max_score <= 0:
        return {k: 0.0 for k in scoring_scores}
    return {k: round((v / max_score) * 100, 1) for k, v in scoring_scores.items()}


def extract_preferences(raw_scores: dict[str, Any]) -> dict[str, str]:
    """Extract university-block preference values from accumulated answer weights."""
    preferences: dict[str, str] = {}
    for key in PREFERENCE_KEYS:
        value = raw_scores.get(key)
        if isinstance(value, str):
            preferences[key] = value
    return preferences


def match_directions(normalized_scores: dict[str, float]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for direction, params in DIRECTIONS_MATRIX.items():
        req_scores = [
            min(normalized_scores.get(cat, 0) / threshold, 1.2)
            for cat, threshold in params["required"].items()
        ]
        base = sum(req_scores) / len(req_scores)

        bonus = sum(
            (normalized_scores.get(cat, 0) / 100) * weight
            for cat, weight in params["bonus"].items()
        )

        match_score = min(round(base * 75 + bonus), 99)
        results.append({"direction": direction, "score": match_score})

    return sorted(results, key=lambda x: x["score"], reverse=True)[:5]
