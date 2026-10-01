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

# PRO-427 — the АСТУР block ("intelligence") is a percent of study-type tasks
# done under a product formula, with no norms behind it.
_INTELLIGENCE_RULES = """Правила для блока «Когнитивные навыки (учебные задания)» (intelligence):
- Это процент выполненных учебных заданий по каждому навыку, а не IQ, не уровень интеллекта и не норматив. Не используй слова «интеллект», «IQ», «СПН», «норма развития». overall_percent — лишь среднее выполнения семи блоков, а не единый уровень способностей; опирайся прежде всего на профиль по навыкам.
- Запрещены выводы про астенизацию, утомляемость, нервную систему, выносливость, работоспособность, внимание и память и любые диагнозы. Быстрые инструкции (quick_instructions) описывай только наблюдаемыми числами: верных ответов в первой и второй половине, ответов в лимит времени. При статусе insufficient_on_time не сравнивай половины.
- subject_profile — это осведомлённость в терминах предметных областей, а не способности. status = leading означает лишь наиболее высокий процент выполнения в текущем наборе заданий. При status = mixed не называй ведущую область, при insufficient_data не интерпретируй профиль вовсе.
- math_reasoning — распознавание закономерностей в числовых рядах. Выводы о математике делай только по нему; если divergence не none — назови расхождение между знанием терминов и решением числовых задач.
- Если protocol_quality.ok = false, прямо напиши, что результат интерпретируется с осторожностью, и назови причину по кодам флагов (ответы вне лимита времени, много пропусков, превышение времени субтеста, нет замера времени). legacy = true — попытка пройдена до обновления теста.
- history.repeat_exposure = true — ученик уже видел эти задания раньше (history.attempt_number — номер завершённой попытки). Изменение результата может быть связано со знакомством с заданиями: не называй его ростом или снижением способностей.
- Возраст и класс для этого блока — только age_at_completion и grade_at_completion (на момент прохождения), а не текущие. У ученика младше 16 лет или ниже 10-го класса низкий результат в заданиях, опирающихся на школьные знания (осведомлённость, обобщение, числовые ряды), в первую очередь объясняй пройденной программой, а не способностями. Не делай вывода о неспособности к направлению по результату этого теста. Если возраст на момент прохождения неизвестен, так и скажи.
"""


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

    age_line = (
        f"Текущий возраст ученика: {context.current_age}." if context.current_age is not None
        else "Текущий возраст ученика неизвестен."
    )
    grade_line = (
        f"Текущий класс: {context.current_grade}." if context.current_grade is not None else "Текущий класс неизвестен."
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

Контекст ученика сегодня (для всех блоков, кроме когнитивных навыков — у них свой возраст на момент прохождения): {age_line} {grade_line}
Возрастных норм ни по одной методике нет — не сравнивай результаты с \
«нормой для возраста». Если возраст или класс неизвестны и это важно для \
вывода, прямо скажи, что возрастной контекст отсутствует.

{_INTELLIGENCE_RULES}
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
