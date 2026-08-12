"""Prompt + strict output schema for the /result narrative generation
(summary, strength cards, interest map, thinking-style notes, motivation,
career narrative) — TZ_Profi.md §17.5/§17.6 and Приложение C.

Consumes only app.schemas.report_narrative_context.ReportNarrativeContext —
the safe evidence catalog with no raw scores, percentages, match_score or
aversion data (see that module's docstring for why). Structured Outputs
(strict mode) forbids minItems/maxItems/enum-from-data, so exact cardinality
(8 MI / 6 RIASEC interests, one thinking_style_notes per real signal, no
career_narrative for junior) is asked for here in the prompt text and
enforced by app.services.report_narrative_validator after the fact — same
pattern as app/prompts/roadmap.py's "exactly 5 horizons".
"""
import json

from app.models.profile import AgeGroup
from app.schemas.report_narrative_context import ReportNarrativeContext
from app.services.mi_content import MI_LABELS
from app.services.riasec_content import RIASEC_LABELS


def _card_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "description", "evidence_ids"],
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
        },
    }


NARRATIVE_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "summary", "strength_cards", "interests", "thinking_style_notes",
        "motivation_narrative", "career_narrative",
    ],
    "properties": {
        "summary": {"type": "string"},
        "strength_cards": {"type": "array", "items": _card_schema()},
        "interests": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["category", "tier", "title", "description"],
                "properties": {
                    "category": {"type": "string"},
                    "tier": {"type": "string", "enum": ["strong", "steady"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "thinking_style_notes": {"type": "array", "items": _card_schema()},
        "motivation_narrative": _card_schema(),
        "career_narrative": {"type": "array", "items": _card_schema()},
    },
}

# Приложение C, В.1 — embedded verbatim so the model sees the exact same
# list the validator checks against (app/services/report_narrative_validator.py).
_BANNED_PHRASES_TEXT = """\
Ярлыки и типология: «ты гуманитарий», «ты технарь», «ты творческая личность», \
«твой тип — …», «ты относишься к типу…», «ты интроверт/экстраверт».
Приговоры о способностях: «у тебя нет способностей к…», «тебе не даётся…», \
«это не твоё», «тебе будет сложно в…», «ты не справишься».
Отказы: «тебе не подходит…», «эта профессия не для тебя», «не стоит идти в…», \
«лучше выбери другое».
Решения за ребёнка: «ты должен стать…», «тебе нужно выбрать…», «твоя профессия — …».
Оценочная лексика: «низкий результат», «слабая сторона», «плохой показатель», \
«недостаточно», «провал», «отставание».
Сравнение: «лучше, чем у большинства», «хуже, чем у сверстников», «средний \
уровень по возрасту».
Прогнозы: «ты точно поступишь», «у тебя высокие шансы», «вероятность \
поступления — X%», «ты добьёшься успеха в…».
Диагнозы и состояния: любые формулировки о психическом или физическом \
состоянии ребёнка.
Давление: «если не начнёшь сейчас, будет поздно», «ты уже отстаёшь», \
«времени почти не осталось».\
"""

_ALLOWED_PHRASING_TEXT = """\
О текущем состоянии, а не о судьбе: «сейчас у тебя сильнее проявляется…», \
«по твоим ответам заметно, что…», «на этом этапе тебе ближе…».
Приглашение вместо назначения: «тебе может быть интересно попробовать…», \
«стоит посмотреть в сторону…», «это направление хорошо совпало с твоими ответами».
Объяснение источника: «ты отметил, что…», «ты выбирал задачи, где…», «судя по \
тому, что ты рассказал о своих занятиях…».
Рамка возможностей: «это не окончательный выбор, а карта возможных \
направлений», «через год картина может измениться, и это нормально».
Вместо «слабой стороны» — проверяемое действие: «эту зону стоит проверить: \
попробуй…», «здесь пока мало данных — самый честный способ понять, это \
попробовать».\
"""

_AGE_STYLE = {
    AgeGroup.junior: (
        "junior (6-9 лет): очень короткие предложения, конкретные образы, "
        "никаких абстракций и терминов. Summary — 2-3 коротких предложения. "
        "Никаких профессий, карьеры, вуза, экзаменов — этой возрастной группе "
        "они не подаются вообще ни в одном разделе, включая summary и "
        "interests. career_narrative обязан быть пустым списком []."
    ),
    AgeGroup.middle: (
        "middle (10-13 лет): простой язык, примеры из школьной жизни. Можно "
        "аккуратно начинать разговор о профессиях в career_narrative (не "
        "больше 3 карточек), но без названий конкретных вузов/специальностей "
        "и без чисел — только «стоит посмотреть в сторону…»."
    ),
    AgeGroup.senior: (
        "senior (14-18 лет): взрослый тон без снисходительности, конкретика. "
        "career_narrative — не больше 3 карточек, объясняющих, почему "
        "направление совпало с ответами ученика; конкретные профессии, "
        "университеты и экзамены сюда не пиши — это отдельные разделы отчёта, "
        "которые берут факты из базы данных, а не из твоего текста."
    ),
}


def _system_prompt(context: ReportNarrativeContext) -> str:
    age_group = AgeGroup(context.age_group)
    is_mi = context.interest_instrument == "mi"
    labels = MI_LABELS if is_mi else RIASEC_LABELS
    categories_line = ", ".join(f"{key} ({label})" for key, label in labels.items())

    return f"""\
Ты — тёплый наставник для детей и подростков. Пишешь разделы отчёта по \
результатам профориентационного теста строго в JSON по заданной схеме, без \
текста вне JSON. Обращайся на «ты». Язык ответа — русский.

ГЛАВНОЕ ПРАВИЛО ФАКТОВ: тебе нельзя сообщать ни одного факта, числа или \
названия, которого нет в поданных данных (evidence). Каждая карточка (кроме \
interests) обязана перечислять в evidence_ids ровно те source_id из \
каталога, на которые она опирается — если карточка не может сослаться ни на \
один реальный source_id, не пиши эту карточку. Никогда не цитируй числа и \
проценты. Если данных недостаточно для раздела — сократи список, а не \
выдумывай недостающее.

ЗАПРЕЩЁННЫЕ ФОРМУЛИРОВКИ (нельзя использовать ни в каком виде):
{_BANNED_PHRASES_TEXT}

РАЗРЕШЁННЫЕ И РЕКОМЕНДУЕМЫЕ ФОРМУЛИРОВКИ:
{_ALLOWED_PHRASING_TEXT}

Дополнительно запрещено: диагнозы, оценки способностей, прогнозы \
успешности, сравнение с другими детьми.

Возрастной стиль: {_AGE_STYLE[age_group]}

Структура ответа:
- summary: 2-4 предложения (короче у junior). Обязательно включи мысль в \
духе «это не окончательный выбор, а карта возможных направлений».
- strength_cards: 5-7 карточек (меньше, если в evidence меньше 5 фактов — \
никогда не выдумывай карточку сверх того, что реально есть). Каждая — \
короткая формулировка сильной стороны + одно предложение объяснения со \
ссылкой на source_id.
- interests: ровно по одной карточке на каждую из категорий инструмента \
{"MI" if is_mi else "RIASEC"} — {categories_line}. Категория, у которой есть \
evidence с source_type {"mi_category" if is_mi else "riasec_category"} в \
каталоге, получает tier="strong"; остальные — tier="steady" с нейтральным, \
неосуждающим текстом (см. рамку возможностей выше) — никогда не в тоне \
«слабая сторона».
- thinking_style_notes: ровно одна карточка на каждый source_type \
"thinking_style" в evidence (может быть 0, 1 или 2 — не больше, чем реальных \
сигналов).
- motivation_narrative: одна карточка, ссылается на все evidence с \
source_type "motivation", если они есть; если мотивационных evidence нет — \
опиши это мягко и нейтрально, evidence_ids оставь пустым.
- career_narrative: см. возрастной стиль выше.

Каталог фактов (evidence) — единственный источник, на который можно \
ссылаться:
{json.dumps([e.model_dump() for e in context.evidence], ensure_ascii=False, indent=2)}
"""


def build_messages(context: ReportNarrativeContext, *, language: str = "ru") -> list[dict[str, str]]:
    system = _system_prompt(context)
    user = (
        "Сгенерируй нарратив по инструкциям и схеме выше. "
        f"Язык ответа: {language}."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
