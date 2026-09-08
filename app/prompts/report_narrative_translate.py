"""Translate an already-generated & validated report narrative into another
locale with ONE LLM call — instead of a second independent generation.

Background: the `/results` narrative is generated per locale (report_service
stores one AnalysisResult row per `locale`). Generating each locale from
scratch produced two differently-worded reports for the same student (ru
leaning on motivation facets, kk on liked-subjects, different closing
sentences). This prompt renders the *primary* locale's narrative into the
target language, preserving meaning, so a language switch shows the same
report translated rather than a fresh take.

Reuses the KZ-401 language directive + Kazakh glossary so proper nouns,
admission terms (ЕНТ→ҰБТ) and profession names stay consistent with the rest
of the product.
"""
import json

from app.prompts._locale import glossary_block, language_directive

_CARD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "description"],
    "properties": {"title": {"type": "string"}, "description": {"type": "string"}},
}

TRANSLATE_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "final_analysis", "strength_cards", "thinking_style_notes"],
    "properties": {
        "summary": {"type": "string"},
        "final_analysis": {"type": "string"},
        "strength_cards": {"type": "array", "items": _CARD_SCHEMA},
        "thinking_style_notes": {"type": "array", "items": _CARD_SCHEMA},
    },
}

_SOURCE_LANG = {"ru": "русского", "kk": "казахского"}
_TARGET_LANG = {"ru": "русский", "kk": "казахский"}


def _payload(source: dict) -> dict:
    return {
        "summary": source["summary"],
        "final_analysis": source["final_analysis"],
        "strength_cards": [
            {"title": c["title"], "description": c["description"]}
            for c in source["strength_cards"]
        ],
        "thinking_style_notes": [
            {"title": n["title"], "description": n["description"]}
            for n in source["thinking_style_notes"]
        ],
    }


def build_messages(source: dict, *, source_locale: str, target_locale: str) -> list[dict[str, str]]:
    n_cards = len(source["strength_cards"])
    n_notes = len(source["thinking_style_notes"])
    rules = [
        f"Ниже — текст профориентационного отчёта школьника с "
        f"{_SOURCE_LANG.get(source_locale, source_locale)} языка, в формате JSON.",
        f"Переведи его на {_TARGET_LANG.get(target_locale, target_locale)} язык. "
        f"Точно сохрани смысл, интонацию и обращение на «ты».",
        "Это ПЕРЕВОД, а не новая генерация: ничего не добавляй, не убирай и не "
        "переосмысливай. Не меняй порядок и количество элементов — в "
        f"strength_cards ровно {n_cards} шт., в thinking_style_notes ровно "
        f"{n_notes} шт.",
        "Числа, названия и имена собственные оставляй как есть (только "
        "переводи склоняемую обвязку вокруг них).",
        "Верни JSON ровно той же схемы: summary, final_analysis, "
        "strength_cards[{title, description}], thinking_style_notes[{title, description}]. "
        "Никакого текста вне JSON.",
        language_directive(target_locale),
    ]
    glossary = glossary_block(target_locale)
    if glossary:
        rules.append(glossary)
    elif target_locale == "ru" and source_locale == "kk":
        # glossary_block() is empty for ru, but a kk->ru translation still has
        # to map the Kazakh admission terms back (ҰБТ -> ЕНТ, …). Built from
        # the same catalog (KZ-503) so it can't drift.
        from app.i18n.catalog import tr as _tr

        ru_terms = _tr("subjects", locale="ru")["admission_terms"]
        kk_terms = _tr("subjects", locale="kk")["admission_terms"]
        pairs = ", ".join(
            f"«{kk_terms[k]}» → «{ru_terms[k]}»"
            for k in ("ent", "profile_subjects", "threshold_score")
        )
        rules.append(f"Термины приёмной кампании переводи обратно: {pairs}.")

    return [
        {"role": "system", "content": "\n".join(rules)},
        {"role": "user", "content": json.dumps(_payload(source), ensure_ascii=False, indent=2)},
    ]


def correction_message(target_locale: str) -> str:
    return (
        "Твой предыдущий ответ не подходит: либо он не полностью на "
        f"{_TARGET_LANG.get(target_locale, target_locale)} языке, либо изменил "
        "количество/структуру элементов, либо содержит запрещённые формулировки. "
        "Пришли новый полный JSON той же схемы — это перевод один-к-одному, без "
        "добавлений и сокращений."
    )
