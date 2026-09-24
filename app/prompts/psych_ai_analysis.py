"""Prompt + strict output schema for the psychologist-view AI analysis
(per-block commentary, final synthesis, one profession pick).

Consumes app.services.psych_ai_analysis_context.PsychAiAnalysisContext — the
raw report/new_tests data, not the pre-abstracted "safe evidence" catalog
app/prompts/report_narrative.py uses (that one is student-facing; this
reader is a professional psychologist). The one hard rule Structured
Outputs can't express on its own — the recommended profession must be one
of `context.careers`, never invented — is asked for here in the prompt text
and enforced after the fact by app.services.psych_ai_analysis_validator,
same "prompt asks, validator verifies" split as report_narrative.py's exact
cardinality rules."""
import json

from app.services.psych_ai_analysis_context import PsychAiAnalysisContext

JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["block_analyses", "final_summary", "recommended_profession"],
    "properties": {
        "block_analyses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["block", "text"],
                "properties": {
                    "block": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        },
        "final_summary": {"type": "string"},
        # Structured Outputs strict mode forbids a truly optional/nullable
        # sub-object with its own `required` list in some SDKs' json_schema
        # validators, so this is always present; a careers-less context
        # (no matching direction) gets an explicit sentinel slug the validator treats as
        # "no recommendation", rather than a bare null the schema can't
        # cleanly express here.
        "recommended_profession": {
            "type": "object",
            "additionalProperties": False,
            "required": ["slug", "name", "reasoning"],
            "properties": {
                "slug": {"type": "string"},
                "name": {"type": "string"},
                "reasoning": {"type": "string"},
            },
        },
    },
}

NO_RECOMMENDATION_SLUG = "__none__"


def _system_prompt(context: PsychAiAnalysisContext) -> str:
    blocks_json = json.dumps(
        [{"block": b.key, "label": b.label, "facts": b.facts} for b in context.blocks],
        ensure_ascii=False, indent=2,
    )
    careers_json = json.dumps(
        [c.model_dump() for c in context.careers], ensure_ascii=False, indent=2,
    )
    careers_rule = (
        f"Список профессий, из которого МОЖНО и НУЖНО выбрать ровно одну "
        f"(поле slug должен буквально совпадать с одним из slug ниже — "
        f"никогда не придумывай свою профессию и не меняй название):\n{careers_json}"
        if context.careers
        else (
            "Список профессий пуст (у этого ученика профориентационный блок "
            f"не строится). В recommended_profession верни ровно "
            f'{{"slug": "{NO_RECOMMENDATION_SLUG}", "name": "", "reasoning": ""}} '
            "— не предлагай никакую профессию."
        )
    )

    return f"""\
Ты — ассистент психолога, помогающий проанализировать результаты \
психодиагностической батареи ученика. Пишешь строго в JSON по заданной \
схеме, без текста вне JSON. Читатель — дипломированный психолог, а не \
ребёнок: можно свободно оперировать сырыми баллами, шкалами и \
профессиональными терминами, без смягчений и метафор для детей.

ГЛАВНОЕ ПРАВИЛО: тебе нельзя сообщать ни одного факта или числа, которого \
нет в данных ниже. Если по какому-то блоку данных не хватает — не пиши про \
него ничего лишнего, ограничься тем, что реально дано.

Структура ответа:
- block_analyses: ровно один элемент на каждый блок из списка "Блоки данных" \
ниже (используй то же значение block, что и key блока), 1-3 предложения \
психологического комментария по этому блоку конкретно для этого ученика — \
не общее описание методики, а именно интерпретация ЭТИХ цифр/уровней. Не \
повторяй в разных блоках одну и ту же мысль.
- final_summary: 5-7 предложений, синтез по ВСЕМ блокам вместе — как они \
согласуются или противоречат друг другу, на что психологу стоит обратить \
внимание в первую очередь. Не пересказывай block_analyses дословно.
- recommended_profession: {careers_rule}

Блоки данных:
{blocks_json}
"""


def build_messages(context: PsychAiAnalysisContext) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _system_prompt(context)},
        {"role": "user", "content": "Сгенерируй анализ по инструкциям и схеме выше."},
    ]
