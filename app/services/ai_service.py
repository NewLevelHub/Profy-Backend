"""Template-based report generation. Interface is LLM-ready: swap generate_report body only."""

from dataclasses import dataclass

STRENGTHS_MAP: dict[str, str] = {
    "technology": "Быстро осваивает технологии и цифровые инструменты",
    "investigative": "Любит докапываться до сути и исследовать",
    "artistic": "Легко придумывает нестандартные идеи и решения",
    "creative_think": "Легко придумывает нестандартные идеи и решения",
    "social": "Хорошо понимает людей и чувствует настроение",
    "social_think": "Хорошо понимает людей и чувствует настроение",
    "logical": "Мыслит структурно и видит логику",
    "mathematical": "Уверенно работает с числами и расчётами",
    "verbal": "Ясно и убедительно выражает мысли словами",
    "spatial": "Хорошо представляет объекты и пространство",
    "leadership": "Умеет брать инициативу и вести за собой",
    "enterprising": "Умеет брать инициативу и вести за собой",
    "conscientiousness": "Доводит начатое до конца, надёжный",
    "openness": "Открыт новому, легко пробует разные подходы",
    "emotional_stability": "Спокойно справляется с трудностями и не сдаётся",
    "extraversion": "Легко общается и чувствует себя уверенно среди людей",
    "agreeableness": "Дружелюбный, умеет работать в команде",
    "teamwork": "Хорошо работает в команде и поддерживает других",
    "independence": "Умеет самостоятельно разбираться в задачах",
    "helping_motiv": "Стремится помогать и приносить пользу",
    "strategic": "Видит картину целиком и планирует наперёд",
    "practical": "Умеет воплощать идеи в реальный результат",
    "realistic": "Умеет воплощать идеи в реальный результат",
    "science": "Проявляет глубокий интерес к научному познанию",
    "nature": "Чувствует связь с природой и живым миром",
    "numbers": "Уверенно работает с данными и статистикой",
    "conventional": "Любит порядок, системность и точность",
    "systematic": "Умеет выстраивать чёткие системы и процессы",
}

CATEGORY_LABELS: dict[str, str] = {
    "technology": "технологии",
    "investigative": "исследование",
    "artistic": "творчество",
    "creative_think": "творческое мышление",
    "social": "работа с людьми",
    "social_think": "понимание людей",
    "logical": "логика",
    "mathematical": "математика",
    "verbal": "языки и коммуникация",
    "spatial": "пространственное мышление",
    "leadership": "лидерство",
    "enterprising": "предпринимательство",
    "conscientiousness": "ответственность",
    "openness": "открытость новому",
    "emotional_stability": "эмоциональная устойчивость",
    "extraversion": "общительность",
    "agreeableness": "доброжелательность",
    "teamwork": "командная работа",
    "independence": "самостоятельность",
    "helping_motiv": "помощь другим",
    "strategic": "стратегическое мышление",
    "practical": "практичность",
    "realistic": "практичность",
    "science": "естественные науки",
    "nature": "природа",
    "numbers": "работа с числами",
    "conventional": "системность",
    "media": "медиа",
    "systematic": "системность",
}

MOTIVATION_MAP: dict[str, str] = {
    "helping_motiv": "Стремление помогать и приносить пользу людям",
    "leadership": "Желание вести за собой и организовывать других",
    "enterprising": "Стремление создавать и развивать своё дело",
    "conscientiousness": "Желание делать всё на высоком уровне",
    "openness": "Интерес к новому и постоянному развитию",
    "strategic": "Стремление мыслить масштабно и планировать",
    "practical": "Желание создавать реальные, ощутимые результаты",
    "investigative": "Стремление исследовать и находить новое",
    "artistic": "Желание создавать и воплощать творческие идеи",
    "social": "Стремление взаимодействовать и понимать людей",
}

INTERESTS_CATEGORIES = frozenset({
    "technology", "artistic", "social", "social_think", "science",
    "nature", "realistic", "media", "investigative", "conventional", "numbers",
})

THINKING_CATEGORIES = frozenset({
    "logical", "mathematical", "verbal", "spatial", "systematic", "creative_think",
})

MOTIVATION_CATEGORIES = frozenset({
    "helping_motiv", "leadership", "enterprising", "conscientiousness",
    "openness", "strategic", "practical", "investigative", "artistic", "social",
})


@dataclass
class MatchedDirection:
    slug: str
    name: str
    match_score: int
    description: str
    professions: list[str]
    skills_needed: list[str]
    subjects_to_develop: list[str]
    first_steps: list[str]
    required_scores: dict[str, float]


@dataclass
class ReportDraft:
    summary: str
    strengths: list[str]
    interests_map: dict[str, float]
    thinking_style: dict[str, float]
    motivation: list[str]
    directions: list[dict]


def build_strengths(normalized_scores: dict[str, float], limit: int = 7) -> list[str]:
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


def _build_summary(total_scores: dict[str, float]) -> str:
    ranked = sorted(total_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    labels = [CATEGORY_LABELS.get(cat, cat) for cat, _ in ranked]
    if not labels:
        return "Твои результаты показывают широкий потенциал для профессионального развития."
    cats_str = ", ".join(labels[:-1]) + " и " + labels[-1] if len(labels) >= 2 else labels[0]
    return (
        f"Твои результаты показывают высокий потенциал в таких сферах, как {cats_str}. "
        f"Это открывает широкие возможности для профессионального роста."
    )


def _filter_scores(
    total_scores: dict[str, float], categories: frozenset[str]
) -> dict[str, float]:
    return {k: v for k, v in total_scores.items() if k in categories}


def _build_motivation_list(total_scores: dict[str, float], top_n: int = 3) -> list[str]:
    motivation_scores = _filter_scores(total_scores, MOTIVATION_CATEGORIES)
    ranked = sorted(motivation_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    result: list[str] = []
    seen: set[str] = set()
    for cat, _ in ranked:
        text = MOTIVATION_MAP.get(cat)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _build_why_it_fits(
    direction: MatchedDirection, total_scores: dict[str, float]
) -> str:
    top_cats = sorted(
        [(cat, total_scores.get(cat, 0)) for cat in direction.required_scores],
        key=lambda x: x[1],
        reverse=True,
    )[:2]
    labels = [CATEGORY_LABELS.get(cat, cat) for cat, _ in top_cats]
    if not labels:
        return "Твои способности хорошо подходят для этого направления."
    combined = " и ".join(labels)
    return f"Твои результаты по {combined} хорошо подходят для этого направления."


def generate_report(
    profile: object,
    artifacts: list,
    total_scores: dict[str, float],
    matched_directions: list[MatchedDirection],
) -> ReportDraft:
    summary = _build_summary(total_scores)
    strengths = build_strengths(total_scores, limit=7)

    interests_map = _filter_scores(total_scores, INTERESTS_CATEGORIES)
    thinking_style = _filter_scores(total_scores, THINKING_CATEGORIES)
    motivation = _build_motivation_list(total_scores)

    directions = [
        {
            "slug": d.slug,
            "name": d.name,
            "match_score": d.match_score,
            "why_it_fits": _build_why_it_fits(d, total_scores),
            "description": d.description,
            "professions": d.professions,
            "skills_needed": d.skills_needed,
            "subjects_to_develop": d.subjects_to_develop,
            "first_steps": d.first_steps,
        }
        for d in matched_directions
    ]

    return ReportDraft(
        summary=summary,
        strengths=strengths,
        interests_map=interests_map,
        thinking_style=thinking_style,
        motivation=motivation,
        directions=directions,
    )
