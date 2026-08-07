"""Prompt + strict schema for the AI-generated result summary ("Резюме").

Personalizes on onboarding (city/country/subjects/clubs), goal, age, and the
RIASEC code/strengths/top careers. One call at report-generation time; falls
back to the template summary on any failure.
"""
import json

from app.models.profile import AgeGroup, Profile
from app.services.mi_content import MI_LABELS
from app.services.riasec_content import RIASEC_LABELS

SUMMARY_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary"],
    "properties": {"summary": {"type": "string"}},
}

_GOAL_FRAMING = {
    "explore": "Цель ученика — понять себя. Покажи его сильные стороны и мягко подскажи, в какие сферы интересно посмотреть.",
    "unsure": "Ученик пока не выбрал. Особенно тепло и ободряюще: ничего страшного, что не определился — покажи опоры и с чего можно начать.",
    "profession": "Ученик выбирает профессию. Свяжи сильные стороны с подходящими направлениями, чуть конкретнее.",
    "university": "Ученик готовится к поступлению. Свяжи сильные стороны с целью и направлением.",
}

_SYSTEM = """\
Ты — тёплый наставник для детей и подростков. Напиши короткое личное резюме по \
результатам профориентационного теста: 2-4 предложения. Обращайся на «ты».
Тон оптимистичный и поддерживающий. Опирайся на сильные стороны, интересы, любимые \
предметы, кружки/секции и город ученика — резюме должно звучать «про него».
Тон по возрасту: junior/middle — простыми словами, без терминов (ML, IT и т.п.); \
senior — взрослее. Язык — русский. Строго JSON, поле summary.\
"""


def build_messages(
    profile: Profile,
    goal: str,
    code: list[str],
    strengths: list[str],
    careers: list[dict],
    artifacts: list,
    personality_highlights: list[str],
    motivation_highlights: list[str],
) -> list[dict[str, str]]:
    # Junior (6-9) uses MI-style categories instead of RIASEC letters — see
    # mi_service.py/mi_content.py. `code`/`strengths` hold MI category keys
    # for that age group, RIASEC letters for middle/senior.
    is_junior = profile.age_group == AgeGroup.junior
    labels = MI_LABELS if is_junior else RIASEC_LABELS
    student = {
        "age": profile.age,
        "age_group": profile.age_group.value,
        "city": profile.city,
        "country": profile.country,
        "subjects_liked": list(profile.subjects_liked or []),
        "subjects_disliked": list(profile.subjects_disliked or []),
        "subjects_easy": list(profile.subjects_easy or []),
        "subjects_hard": list(profile.subjects_hard or []),
        "clubs_sections": [a.value for a in artifacts],
        "riasec_code": "" if is_junior else "".join(code),
        "interests": [labels.get(c, c) for c in code] if is_junior else [],
        "strengths": [labels.get(c, c) for c in strengths],
        "top_careers": [c.get("name", "") for c in careers[:3]],
        # Already-interpreted RU phrases from Big Five — never raw domain
        # percentages, so the LLM can't turn them into "Openness: 78%" talk.
        "personality_highlights": personality_highlights,
        "motivation_highlights": motivation_highlights,
    }
    framing = _GOAL_FRAMING.get(goal, _GOAL_FRAMING["explore"])
    user = (
        f"{framing}\n\n"
        f"ДАННЫЕ УЧЕНИКА:\n{json.dumps(student, ensure_ascii=False, indent=2)}\n\n"
        "Напиши резюме по схеме."
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
