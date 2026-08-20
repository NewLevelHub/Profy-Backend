"""
Big Five methodology reference tables — mirrors riasec_content.py's role.
"""
from typing import Literal

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

# Mirrors the same product decision above, applied to the low/"growth" side
# instead of the high/"strength" side: a low score on openness,
# conscientiousness, or emotional_stability is a skill gap worth naming
# (trying new things, follow-through, handling stress). A low score on
# extraversion or agreeableness is temperament (introversion, directness),
# not a deficiency — naming it as something to "work on" would tell a
# student their normal personality is a problem. Used by
# report_v2_assembler.build_personality_note to scope which low traits get
# named in the report.
GROWTH_ELIGIBLE_TRAITS = frozenset({"openness", "conscientiousness", "emotional_stability"})


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


# Same 5 traits as _NOTES, but short/concrete phrasing with no abstractions
# (TZ_Profi.md §4.1: junior needs "очень короткие предложения, конкретные
# образы") — a 6-9-year-old reading "нестандартные подходы" or "отстаивать
# границы" gets nothing out of it. Derived fresh from the numeric profile at
# render time (personality_notes_for_age below), never from the stored
# adult-phrased `personality_notes` text — that stays adult-only (admin
# panel, and middle/senior's own "Твой характер" block).
_NOTES_JUNIOR: dict[str, dict[str, str]] = {
    "openness": {
        "high": "Тебе нравится пробовать новое и придумывать необычное",
        "low": "Тебе больше нравится привычное и понятное",
        "mid": "Тебе интересно и новое, и привычное — по-разному",
    },
    "conscientiousness": {
        "high": "Ты доводишь начатое до конца",
        "low": "Тебе легче, когда можно менять план на ходу",
        "mid": "Ты можешь и по плану, и без плана — как удобнее",
    },
    "extraversion": {
        "high": "Тебе нравится быть среди людей и знакомиться",
        "low": "Тебе комфортнее в тишине с близкими друзьями",
        "mid": "Тебе хорошо и в компании, и одному",
    },
    "agreeableness": {
        "high": "Тебе важно помогать другим и дружить",
        "low": "Ты прямо говоришь, что думаешь",
        "mid": "Ты умеешь и дружить, и стоять на своём",
    },
    "emotional_stability": {
        "high": "Ты спокойно переживаешь неудачи",
        "low": "Ты сильно всё чувствуешь — и это нормально",
        "mid": "Ты по-разному переживаешь трудности",
    },
}


def personality_notes_for_age(is_junior: bool, profile: dict[str, float]) -> dict[str, str]:
    """Age-appropriate tiered note per trait in `profile` (the 5-domain dict
    build_personality_profile() returns) — computed fresh from the numeric
    tier every time, not read from the stored `personality_notes` text
    (which is always adult-phrased, used for admin/storage regardless of
    the student's age). `profile` may be a stored `AnalysisResult.
    personality_profile` row just as well as a freshly-computed one — same
    5 keys either way."""
    table = _NOTES_JUNIOR if is_junior else _NOTES
    notes: dict[str, str] = {}
    for trait, value in profile.items():
        tier = "high" if value >= _STRONG else "low" if value <= _LOW else "mid"
        notes[trait] = table[trait][tier]
    return notes


def is_high_tier(value: float) -> bool:
    """Same threshold `build_personality_profile` uses for its "high" tier —
    exposed so other consumers (the report narrative evidence catalog) can
    filter to only strongly-evidenced traits without duplicating the magic
    number or re-deriving the tier from scratch."""
    return value >= _STRONG


def is_low_tier(value: float) -> bool:
    """Same threshold `build_personality_profile` uses for its "low" tier —
    mirrors `is_high_tier` above so consumers (e.g. `build_personality_note`)
    can name genuinely low traits, not just high ones, without duplicating
    the magic number."""
    return value <= _LOW


def personality_level(value: float) -> Literal["low", "medium", "high"]:
    """Same tier boundary personality_notes_for_age()/build_personality_profile()
    use to pick description text — level and description always agree for a
    trait. Mirrors report_v2_assembler._level()'s shape (low/medium/high) for
    the interest map, but on Big Five's own _STRONG/_LOW cutoffs, not
    RIASEC's different thresholds. Used by build_personality_notes() to set
    StudentPersonalityNote.level."""
    if value >= _STRONG:
        return "high"
    if value <= _LOW:
        return "low"
    return "medium"


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
