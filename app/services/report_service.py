"""Report building helpers: strengths mapping and section assembly."""

STRENGTHS_MAP: dict[str, str] = {
    "technology": "Быстро осваивает технологии и цифровые инструменты",
    "investigative": "Любит докапываться до сути и исследовать",
    "artistic": "Легко придумывает идеи и нестандартные решения",
    "creative_think": "Легко придумывает идеи и нестандартные решения",
    "social": "Хорошо понимает людей и чувствует настроение",
    "social_think": "Хорошо понимает людей и чувствует настроение",
    "logical": "Мыслит структурно и видит логику",
    "mathematical": "Уверенно работает с числами и расчётами",
    "verbal": "Ясно выражает мысли словами",
    "spatial": "Хорошо представляет объекты и пространство",
    "leadership": "Умеет брать инициативу и вести за собой",
    "enterprising": "Умеет брать инициативу и вести за собой",
    "conscientiousness": "Доводит начатое до конца, надёжный",
    "openness": "Открыт новому, любит пробовать",
    "helping_motiv": "Стремится помогать и приносить пользу",
    "strategic": "Видит картину целиком и планирует наперёд",
    "practical": "Умеет воплощать идеи в реальный результат",
    "realistic": "Умеет воплощать идеи в реальный результат",
}


def build_strengths(normalized_scores: dict[str, float], limit: int = 7) -> list[str]:
    """Return top strength descriptions from normalized category scores."""
    ranked = sorted(normalized_scores.items(), key=lambda item: item[1], reverse=True)
    strengths: list[str] = []
    seen_texts: set[str] = set()

    for category, _score in ranked:
        text = STRENGTHS_MAP.get(category)
        if text is None or text in seen_texts:
            continue
        strengths.append(text)
        seen_texts.add(text)
        if len(strengths) >= limit:
            break

    return strengths
