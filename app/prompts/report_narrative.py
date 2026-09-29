"""Prompt + strict output schema for the /result narrative generation
(summary, strength cards, interest map, thinking-style notes, motivation,
career narrative) — TZ_Profi.md §17.5/§17.6 and Приложение C.

Consumes only app.schemas.report_narrative_context.ReportNarrativeContext —
the safe evidence catalog with no raw scores, percentages, match_score or
aversion data (see that module's docstring for why). Structured Outputs
(strict mode) forbids minItems/maxItems/enum-from-data, so exact cardinality
(6 RIASEC interests, exactly one merged thinking_style_notes card
covering every real signal) is asked for
here in the prompt text and
enforced by app.services.report_narrative_validator after the fact.
"""
import json

from app.prompts._locale import glossary_block, language_directive
from app.schemas.report_narrative_context import ReportNarrativeContext
from app.services.riasec_content import riasec_labels


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
        "motivation_narrative", "career_narrative", "final_analysis",
    ],
    "properties": {
        "summary": {"type": "string"},
        "final_analysis": {"type": "string"},
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

_AGE_STYLE = (
    "senior (14-18 лет): взрослый тон без снисходительности, конкретика. "
    "career_narrative — не больше 3 карточек, объясняющих, почему "
    "направление совпало с ответами ученика; конкретные профессии, "
    "университеты и экзамены сюда не пиши — это отдельные разделы отчёта, "
    "которые берут факты из базы данных, а не из твоего текста. "
    "ОБЯЗАТЕЛЬНО: evidence_ids каждой карточки career_narrative — минимум "
    f"один реальный source_id с source_type \"riasec_category\" из "
    f"каталога ниже; если ни один не подходит по смыслу — не пиши эту "
    f"карточку вообще, пустой evidence_ids здесь недопустим."
)


def _strength_candidates_payload(context: ReportNarrativeContext) -> list[dict]:
    # Only what the wording needs — never a candidate's underlying evidence
    # ids, domain or quality flags.
    return [
        {"source_id": c.source_id, "basis": c.basis, "title": c.title, "description": c.description}
        for c in context.strength_candidates
    ]


def _system_prompt(context: ReportNarrativeContext, *, locale: str = "ru") -> str:
    labels = riasec_labels()
    categories_line = ", ".join(f"{key} ({label})" for key, label in labels.items())
    glossary = glossary_block(locale)
    glossary_section = f"\n{glossary}\n" if glossary else ""

    return f"""\
Ты — тёплый наставник для детей и подростков. Пишешь разделы отчёта по \
результатам профориентационного теста строго в JSON по заданной схеме, без \
текста вне JSON. Обращайся на «ты». {language_directive(locale)}

ГЛАВНОЕ ПРАВИЛО ФАКТОВ: тебе нельзя сообщать ни одного факта, числа или \
названия, которого нет в поданных данных (evidence). Каждая карточка (кроме \
interests) обязана перечислять в evidence_ids ровно те source_id из \
каталога, на которые она опирается — если карточка не может сослаться ни на \
один реальный source_id, не пиши эту карточку. Никогда не цитируй числа и \
проценты. Если данных недостаточно для раздела — сократи список, а не \
выдумывай недостающее. Ссылка на source_id живёт ТОЛЬКО в поле evidence_ids \
— никогда не пиши сам source_id (например "riasec:E" или "personality:openness") \
или его часть внутри текста title/description, даже в скобках как сноску. \
Текст читает ребёнок, а не разработчик — он не должен видеть служебные \
идентификаторы.

ЗАПРЕЩЁННЫЕ ФОРМУЛИРОВКИ (нельзя использовать ни в каком виде):
{_BANNED_PHRASES_TEXT}

РАЗРЕШЁННЫЕ И РЕКОМЕНДУЕМЫЕ ФОРМУЛИРОВКИ:
{_ALLOWED_PHRASING_TEXT}

Дополнительно запрещено: диагнозы, оценки способностей, прогнозы \
успешности, сравнение с другими детьми.

Возрастной стиль: {_AGE_STYLE}

Структура ответа:
- summary: РОВНО 5-6 предложений, не меньше и не больше. Каждое предложение обязано добавлять НОВОЕ \
содержание — не повторяй мысль, которую уже сказал(а) в одном из предыдущих \
предложений summary, другими словами, и не пересказывай факты, у которых \
дальше в отчёте есть своя отдельная секция (сильные стороны, характер, \
стиль мышления, мотивация, направления/профессии) — summary даёт общую \
рамку и ощущение, а не конкретные факты из этих секций. НЕ пиши мысль в \
духе «это не окончательный выбор, а карта возможных направлений» и любые её \
вариации ни в каком предложении summary — рядом с summary всегда отдельно \
показывается disclaimer с ровно этой мыслью, повтор её твоими словами \
читается как дублирование одного и того же дважды.
- strength_cards: РОВНО по одной карточке на КАЖДОГО кандидата из каталога \
strength_candidates (он в конце), в том же порядке. evidence_ids карточки — \
ровно [source_id этого кандидата], ничего больше: никаких riasec_category, \
personality, motivation или thinking_style — у этих фактов свои разделы. \
Кандидаты уже отобраны по методике: не добавляй новых, не объединяй и не \
пропускай (если каталог пуст — strength_cards пустой). Ты можешь сделать \
только title естественнее. description СКОПИРУЙ из кандидата ДОСЛОВНО, без \
перефразирования, сокращений и дополнений: это проверенное объяснение, которое \
интерфейс покажет после слов «Почему так?». Учитывай уровень основания basis:
  * task_result — наблюдение по выполненным заданиям («в заданиях такого \
типа у тебя получалось лучше всего»); никаких слов про интеллект, IQ, \
одарённость, сравнения с другими и прогнозов;
  * self_report — так ученик сам описал себя («ты отметил(а)», «по твоим \
ответам о себе»); не выдавай это за измеренный факт;
  * cross_signal — сигнал совпал в нескольких тестах, об этом можно сказать;
  * interest — это ИНТЕРЕС, который стоит проверить, а НЕ доказанное умение: \
нельзя «умеешь», «хорошо понимаешь», «у тебя получается», «способности», \
«талант».
title — короткая конкретная формулировка наблюдения. Карточки должны \
звучать как пять разных наблюдений: не начинай три и более title одинаковыми \
словами. Не пиши техническое название методики или её код.
- interests: ровно по одной карточке на каждую из категорий инструмента \
RIASEC — {categories_line}. Категория, у которой есть \
evidence с source_type "riasec_category" в \
каталоге, получает tier="strong"; остальные — tier="steady" с нейтральным, \
неосуждающим текстом (см. рамку возможностей выше) — никогда не в тоне \
«слабая сторона».
- thinking_style_notes: РОВНО ОДНА карточка на ВСЕ evidence с source_type \
"thinking_style" вместе (0 карточек, если такого evidence нет; если его 2 — \
не делай 2 отдельные карточки с одинаковым общим заголовком, объедини оба \
сигнала в одну). evidence_ids этой карточки обязан включать source_id \
КАЖДОГО сигнала thinking_style из каталога, а не только одного из двух. \
title называет стиль(и) по имени (например «Тебе близко \
стратегическое мышление» или «Тебе близки творческое и стратегическое \
мышление»), description — пример(ы) задач для каждого стиля плюс отдельное \
предложение о том, где это обычно проявляется в жизни/работе (без названий \
профессий — это не career_narrative). Если в каталоге есть evidence с \
source_type "personality" — добавь в конце ЕЩЁ ОДНО предложение, соединяющее \
стиль мышления с этой чертой характера, но НЕ ЦИТИРУЙ её текст из каталога \
дословно (эта же черта уже полностью описана в отдельном блоке "Твой \
характер" — дословный повтор там же будет читаться как дублирование). Вместо \
цитаты — новая мысль на стыке двух фактов: как эта черта характера обычно \
помогает или проявляется вместе с этим стилем мышления. Если такого evidence \
нет — просто не добавляй это предложение, ничего не выдумывай.
- motivation_narrative: одна карточка, ссылается на все evidence с \
source_type "motivation", если они есть; если мотивационных evidence нет — \
опиши это мягко и нейтрально, evidence_ids оставь пустым.
- career_narrative: см. возрастной стиль выше.
- final_analysis: МИНИМУМ 3 предложения, максимум 5. Это последний блок \
отчёта — читатель уже видел summary, strength_cards, интересы, характер, \
стиль мышления и мотивацию. Задача final_analysis — связать эти разделы \
между собой, а не пересказать их. НЕ цитируй конкретные фразы из evidence \
дословно (это уже было сказано в своих разделах) — вместо этого общими \
словами укажи, ЧТО каждый раздел показывает (например «интересы показывают, \
куда тебя тянет, а характер и стиль мышления — как тебе комфортнее \
работать») и как использовать это вместе, а не по отдельности. Затронь как \
минимум ДВА разных раздела (например интересы + характер, или стиль \
мышления + мотивация) — иначе это просто дубль одного из разделов. Так же, \
как и в summary, НЕ пиши мысль «это не окончательный выбор / карта \
возможных направлений» — это дублирует disclaimer.

ЧЕК-ЛИСТ ПЕРЕД ОТПРАВКОЙ (самые частые ошибки — проверь именно это):
1. У каждой карточки career_narrative есть непустой evidence_ids хотя бы с \
одним source_id, у которого source_type = "riasec_category". Пустой \
evidence_ids здесь = ошибка, карточку лучше не писать.
2. Каждая карточка strength_cards ссылается ровно на одного кандидата из \
strength_candidates — и ни на что больше.
3. Количество strength_cards равно количеству кандидатов в \
strength_candidates.
4. Карточка кандидата с basis "interest" описывает интерес, а не умение.
5. summary — ровно 5-6 предложений, не меньше и не больше (посчитай их сам \
перед отправкой), и ни одно не повторяет мысль другого предложения summary \
своими словами.
6. summary НЕ содержит мысль «это не окончательный выбор / карта \
возможных направлений» в любой формулировке — эта мысль уже есть в \
disclaimer рядом, повторять её в summary нельзя.
7. final_analysis — минимум 3 предложения, не повторяет summary дословно, \
не содержит фразу про «карту возможных направлений», и явно связывает \
минимум 2 разных раздела отчёта между собой.
{glossary_section}
Каталог фактов (evidence) — единственный источник, на который можно \
ссылаться:
{json.dumps([e.model_dump() for e in context.evidence], ensure_ascii=False, indent=2)}

Каталог strength_candidates — единственный источник для strength_cards:
{json.dumps(_strength_candidates_payload(context), ensure_ascii=False, indent=2)}
"""


def build_messages(context: ReportNarrativeContext, *, language: str = "ru") -> list[dict[str, str]]:
    system = _system_prompt(context, locale=language)
    user = (
        "Сгенерируй нарратив по инструкциям и схеме выше. "
        f"{language_directive(language)}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
