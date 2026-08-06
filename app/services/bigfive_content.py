"""
Big Five methodology reference tables — mirrors riasec_content.py's role.
"""

# Russian domain labels — admin/debug use only. Raw Big Five percentages are
# never shown to the student directly (TZ_Profi.md §18.3: numbers are
# admin-only); the student-facing report uses thinking_style + the
# interpreted phrases below instead.
BIGFIVE_LABELS: dict[str, str] = {
    "N": "Эмоциональная чувствительность",
    "E": "Экстраверсия",
    "O": "Открытость опыту",
    "A": "Доброжелательность",
    "C": "Добросовестность",
}

# The fixed 1-5 scale every Big Five question is answered on — different
# wording from RIASEC's LIKERT_LABELS (agreement, not liking), needed for
# admin-panel display of raw answers.
LIKERT_LABELS: list[str] = [
    "Очень Неточно",
    "Умеренно Неточно",
    "Ни Точно, Ни Неточно",
    "Умеренно Точно",
    "Очень Точно",
]

THINKING_STYLE_LABELS: dict[str, str] = {
    "creative_think": "Генерация нестандартных решений",
    "systematic": "Выстраивание систем и порядка",
    "strategic": "Видение целого, планирование наперёд",
    "practical": "Доведение идеи до работающего результата",
}

# Only 3 domains feed "Сильные стороны" (Openness, Conscientiousness, low
# Neuroticism) — confirmed with product owner: Extraversion/Agreeableness
# aren't reliably "strengths" (can be a liability depending on context), so
# they're excluded here rather than guessed at.
_STRONG = 60.0
_LOW = 40.0


def strength_phrases(bigfive_normalized: dict[str, float]) -> list[str]:
    phrases: list[str] = []
    if bigfive_normalized.get("O", 0.0) >= _STRONG:
        phrases.append("Тебе интересно пробовать новое и нестандартно смотреть на вещи")
    if bigfive_normalized.get("C", 0.0) >= _STRONG:
        phrases.append("Ты умеешь довести начатое до конца, даже когда это скучно")
    if bigfive_normalized.get("N", 100.0) <= _LOW:
        phrases.append("Ты спокойно переживаешь неудачи и пробуешь снова")
    return phrases


# "Твой характер" — full 5-trait profile, distinct from strength_phrases()
# above (only 3 conditional highlights) and from the raw admin-only
# `big_five` dict. Keys are descriptive names, not N/E/O/A/C letters — same
# convention as thinking_style's creative_think/systematic/etc.
PERSONALITY_LABELS: dict[str, str] = {
    "openness": "Открытость новому",
    "conscientiousness": "Организованность",
    "extraversion": "Общительность",
    "agreeableness": "Доброжелательность",
    "emotional_stability": "Эмоциональная устойчивость",
}

_NOTES: dict[str, dict[str, str]] = {
    "openness": {
        "high": "Тебе интересно узнавать новое, пробовать нестандартные подходы и открывать необычные идеи",
        "low": "Тебе комфортнее с проверенными и понятными способами, чем с экспериментами",
        "mid": "Ты одинаково легко и пробуешь новое, и полагаешься на проверенные способы",
    },
    "conscientiousness": {
        "high": "Ты организован, доводишь дела до конца и держишь слово",
        "low": "Тебе ближе гибкость и спонтанность, чем жёсткие планы и расписания",
        "mid": "Ты можешь и следовать плану, и действовать по ситуации — смотря что нужно",
    },
    "extraversion": {
        "high": "Ты заряжаешься энергией от общения и легко находишь общий язык с новыми людьми",
        "low": "Тебе комфортнее в спокойной обстановке и в компании близких людей, чем в шумных компаниях",
        "mid": "Ты одинаково хорошо чувствуешь себя и в компании, и наедине с собой",
    },
    "agreeableness": {
        "high": "Тебе важно помогать другим, идти на компромиссы и поддерживать хорошие отношения",
        "low": "Ты прямо говоришь, что думаешь, и умеешь отстаивать свои границы",
        "mid": "Ты умеешь и договариваться, и стоять на своём — в зависимости от ситуации",
    },
    "emotional_stability": {
        "high": "Ты обычно сохраняешь спокойствие даже в стрессовых ситуациях",
        "low": "Ты тонко чувствуешь события вокруг — иногда это помогает быть внимательным, а иногда стоит дать себе отдохнуть",
        "mid": "Ты справляешься со стрессом по-разному — в зависимости от ситуации",
    },
}


def build_personality_profile(
    bigfive_normalized: dict[str, float],
) -> tuple[dict[str, float], dict[str, str]]:
    """Display-ready 5-trait profile + one tiered note per trait. Neuroticism
    is flipped to Emotional Stability (100 - N) so a high bar always reads
    positive, matching the other 4 traits — the raw `big_five.N` used
    elsewhere (admin, thinking_style) is untouched."""
    profile = {
        "openness": bigfive_normalized.get("O", 0.0),
        "conscientiousness": bigfive_normalized.get("C", 0.0),
        "extraversion": bigfive_normalized.get("E", 0.0),
        "agreeableness": bigfive_normalized.get("A", 0.0),
        "emotional_stability": round(100.0 - bigfive_normalized.get("N", 0.0), 1),
    }
    notes: dict[str, str] = {}
    for trait, value in profile.items():
        tier = "high" if value >= _STRONG else "low" if value <= _LOW else "mid"
        notes[trait] = _NOTES[trait][tier]
    return profile, notes
