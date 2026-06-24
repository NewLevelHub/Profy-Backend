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


def get_answer_scores(question: Question, selected_option_index: int) -> dict[str, Any]:
    """Return the score contribution of a single answer."""
    scores: dict[str, Any] = {}
    apply_answer(scores, question, selected_option_index)
    return scores


def calculate_scores(
    questions_map: dict[Any, Question],
    answers: list[Any],
) -> dict[str, Any]:
    """Sum weights across all answers; answers items must have question_id and selected_option_index."""
    return calculate_raw_scores(
        questions_map,
        [(item.question_id, item.selected_option_index) for item in answers],
    )


def extract_preferences(raw_scores: dict[str, Any]) -> dict[str, str]:
    """Extract university-block preference values from accumulated answer weights."""
    preferences: dict[str, str] = {}
    for key in PREFERENCE_KEYS:
        value = raw_scores.get(key)
        if isinstance(value, str):
            preferences[key] = value
    return preferences
