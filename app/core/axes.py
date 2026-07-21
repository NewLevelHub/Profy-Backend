"""Canonical catalog of the 24 Akinator scoring axes.

Source of truth: akinatorLogic/profi_axes_phase1.md ("ЕДИНСТВЕННЫЙ источник
правды по осям"). Naming convention: short codes (People, Care, Phys, ...),
confirmed with product. Earlier drafts used family-prefixed codes
(A_people, B_analyze, C_body, D_persistence, E_subject_*) — those are
superseded; see the "Изменения от первого черновика" section of that file
for the old -> new mapping. Do not reintroduce the prefixed form.
"""

import enum
from dataclasses import dataclass
from typing import Literal


class AxisFamily(str, enum.Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


@dataclass(frozen=True, slots=True)
class AxisDefinition:
    code: str
    family: AxisFamily
    min_depth: int
    label_ru: str


AXIS_CATALOG: tuple[AxisDefinition, ...] = (
    # A — Ориентация (с чем работаешь). Формат: прямой. Глубина 0-1.
    AxisDefinition("People", AxisFamily.A, 0, "Ориентация на людей, общение"),
    AxisDefinition("Living", AxisFamily.A, 0, "Биология, животные, природа, тело"),
    AxisDefinition("Phys", AxisFamily.A, 0, "Предметы, машины, материалы"),
    AxisDefinition("Data", AxisFamily.A, 0, "Числа, код, количественное"),
    AxisDefinition("Ideas", AxisFamily.A, 0, "Абстрактное, эстетика, замысел"),
    # B — Модальность (что делаешь). Формат: смешанный. Глубина 1-3.
    AxisDefinition("Inv", AxisFamily.B, 1, "Изобретать, придумывать с нуля"),
    AxisDefinition("Obj", AxisFamily.B, 1, "Разбирать/докапываться vs строить инструмент"),
    AxisDefinition("Care", AxisFamily.B, 1, "Лечить, поддерживать конкретного человека"),
    AxisDefinition("Dev", AxisFamily.B, 1, "Учить, растить других"),
    AxisDefinition("Lead", AxisFamily.B, 1, "Вести, организовывать"),
    AxisDefinition("Vis", AxisFamily.B, 1, "Быть на виду, выступать"),
    # C — Канал (через что действуешь). Формат: смешанный. Глубина 3+.
    AxisDefinition("Motor", AxisFamily.C, 3, "Моторика, руки, тело"),
    AxisDefinition("Exp", AxisFamily.C, 3, "Глубокая узкая экспертиза"),
    AxisDefinition("Emp", AxisFamily.C, 3, "Эмоциональный интеллект"),
    # D — Темперамент. Формат: ситуативный, всегда. Глубина 2+.
    AxisDefinition("Focus", AxisFamily.D, 2, "Глубокий длительный фокус"),
    AxisDefinition("Motiv", AxisFamily.D, 2, "Результат, финиш vs процесс"),
    AxisDefinition("Risk", AxisFamily.D, 2, "Комфорт с риском, высокие ставки"),
    AxisDefinition("Auto", AxisFamily.D, 2, "Самостоятельность"),
    AxisDefinition("Struct", AxisFamily.D, 2, "Правила, порядок"),
    AxisDefinition("Pace", AxisFamily.D, 2, "Срочно, динамично"),
    AxisDefinition("Predict", AxisFamily.D, 2, "Новизна, сюрпризы"),
    # E — Практика (факты). Формат: прямой.
    AxisDefinition("Acad", AxisFamily.E, 0, "Готовность к долгой учёбе"),
    AxisDefinition("PhysSt", AxisFamily.E, 0, "Физическая нагрузка"),
    AxisDefinition("Math", AxisFamily.E, 0, "Алгоритмы, высшая математика"),
)

AXIS_CODES: frozenset[str] = frozenset(axis.code for axis in AXIS_CATALOG)

_AXIS_BY_CODE: dict[str, AxisDefinition] = {axis.code: axis for axis in AXIS_CATALOG}


@dataclass(frozen=True, slots=True)
class AxisGrowthCopy:
    """Static, non-personalized explanation for an axis shown as a "growth
    point" on the results page — same text regardless of which direction or
    student it's attached to. `meaning` answers "what is this", `suggestion`
    answers "what could I try" (see result_service._axis_comparison_for)."""
    meaning: str
    suggestion: str


AXIS_GROWTH_COPY: dict[str, AxisGrowthCopy] = {
    "People": AxisGrowthCopy(
        "Про то, чтобы быть в контакте с людьми, работать через общение.",
        "Попробуй больше командной работы, дебаты, волонтёрство, публичные проекты.",
    ),
    "Living": AxisGrowthCopy(
        "Про интерес к живому — организмам, природе, телу.",
        "Попробуй биологию на практике: уход за животными или растениями, лабораторные, походы.",
    ),
    "Phys": AxisGrowthCopy(
        "Про работу с материальными вещами — устройствами, механизмами, материалами.",
        "Попробуй что-то собрать или починить руками: конструктор, ремонт, мастерская.",
    ),
    "Data": AxisGrowthCopy(
        "Про работу с числами, данными, кодом.",
        "Попробуй задачи с таблицами, статистикой или простое программирование.",
    ),
    "Ideas": AxisGrowthCopy(
        "Про абстрактное мышление, эстетику, замысел «с нуля».",
        "Попробуй придумать концепт — дизайн, историю, идею проекта — не важно, каким получится результат.",
    ),
    "Inv": AxisGrowthCopy(
        "Про то, чтобы придумывать новое, а не следовать готовому.",
        "Попробуй сделать что-то своё с нуля — проект, поделку, идею — без образца перед глазами.",
    ),
    "Obj": AxisGrowthCopy(
        "Про то, чтобы разбираться, как всё устроено, и строить решения из этого понимания.",
        "Попробуй разобрать сложную вещь (в прямом или переносном смысле) и понять, как она работает.",
    ),
    "Care": AxisGrowthCopy(
        "Про заботу о конкретном человеке — поддержку, помощь, лечение.",
        "Попробуй помочь кому-то напрямую: волонтёрство, забота о младших, поддержка друга в трудной ситуации.",
    ),
    "Dev": AxisGrowthCopy(
        "Про то, чтобы учить и помогать расти другим.",
        "Попробуй объяснить что-то младшим или сверстникам — побыть наставником хоть раз.",
    ),
    "Lead": AxisGrowthCopy(
        "Про то, чтобы вести за собой и организовывать процесс.",
        "Попробуй взять на себя организацию — проекта, мероприятия, команды.",
    ),
    "Vis": AxisGrowthCopy(
        "Про то, чтобы быть на виду и выступать перед другими.",
        "Попробуй выступить публично: доклад, презентация, сцена — в комфортном для себя формате.",
    ),
    "Motor": AxisGrowthCopy(
        "Про точную работу руками и телом.",
        "Попробуй что-то, что тренирует моторику: рукоделие, спорт, конструирование.",
    ),
    "Exp": AxisGrowthCopy(
        "Про то, чтобы уйти глубоко в одну тему, а не по верхам.",
        "Попробуй закопаться в одну тему надолго вместо того, чтобы перескакивать между интересами.",
    ),
    "Emp": AxisGrowthCopy(
        "Про то, чтобы считывать и учитывать чужие эмоции.",
        "Попробуй осознанно слушать и подмечать состояние других — в разговоре, в команде.",
    ),
    "Focus": AxisGrowthCopy(
        "Про способность долго удерживать внимание на одном деле.",
        "Попробуй один длинный подход без отвлечений — час-два над одной задачей.",
    ),
    "Motiv": AxisGrowthCopy(
        "Про ориентацию на результат и завершение, а не только процесс.",
        "Попробуй довести до конца небольшой проект, который легко бросить на середине.",
    ),
    "Risk": AxisGrowthCopy(
        "Про готовность рисковать и работать в условиях высоких ставок.",
        "Попробуй взяться за задачу с неочевидным исходом — соревнование, публичную попытку.",
    ),
    "Auto": AxisGrowthCopy(
        "Про то, чтобы действовать самому, без постоянного контроля.",
        "Попробуй взять задачу и довести её без подсказок и напоминаний.",
    ),
    "Struct": AxisGrowthCopy(
        "Про комфорт с правилами, структурой, порядком.",
        "Попробуй задачу с чёткими шагами и правилами — и пройти её по порядку до конца.",
    ),
    "Pace": AxisGrowthCopy(
        "Про работу в быстром, динамичном темпе.",
        "Попробуй задачу на время — с реальным дедлайном и быстрым темпом.",
    ),
    "Predict": AxisGrowthCopy(
        "Про комфорт с новизной и неожиданностями.",
        "Попробуй что-то без чёткого плана заранее — импровизацию, новое место, новый формат.",
    ),
    "Acad": AxisGrowthCopy(
        "Про готовность долго и системно учиться.",
        "Попробуй один длинный курс или книгу вместо коротких форматов.",
    ),
    "PhysSt": AxisGrowthCopy(
        "Про готовность к физической нагрузке.",
        "Попробуй регулярную физическую активность — спорт, тренировки, активный отдых.",
    ),
    "Math": AxisGrowthCopy(
        "Про интерес и готовность к математике и алгоритмам.",
        "Попробуй задачи по математике или логике за пределами школьной программы.",
    ),
}

# Static, non-personalized "you"-phrased statement for an axis shown as a
# match/strength on the results page — same pairing purpose as
# AXIS_GROWTH_COPY, but deliberately first person direct ("тебе легко...")
# rather than growth's softer third-person framing (see result_service
# module docstring for why match and growth use different registers).
# Senior-tuned for now; revisit per age group once junior/middle need it.
AXIS_STRENGTH_COPY: dict[str, str] = {
    "People": "Тебе легко находить общий язык с людьми и быть с ними на связи.",
    "Living": "Тебя тянет к живому — природе, животным, тому, как устроено тело.",
    "Phys": "Тебе нравится работать с вещами руками — устройствами, механизмами, материалами.",
    "Data": "Тебе легко даётся работа с числами, данными и точными расчётами.",
    "Ideas": "Тебе легко работать с идеями и придумывать замысел с нуля.",
    "Inv": "Ты умеешь придумывать новое, а не просто повторять готовое.",
    "Obj": "Тебе интересно разбираться, как всё устроено изнутри.",
    "Care": "Тебе легко поддерживать и заботиться о конкретном человеке.",
    "Dev": "У тебя получается объяснять и помогать другим расти.",
    "Lead": "Тебе легко брать на себя организацию и вести за собой.",
    "Vis": "Тебе комфортно быть на виду и выступать перед другими.",
    "Motor": "У тебя хорошая моторика — тебе легко даётся точная работа руками.",
    "Exp": "Тебе нравится уходить глубоко в одну тему, а не хвататься за всё подряд.",
    "Emp": "Ты хорошо считываешь и понимаешь чужие эмоции.",
    "Focus": "Ты умеешь долго удерживать внимание на одном деле.",
    "Motiv": "Тебе важно довести дело до конкретного результата, а не просто попробовать.",
    "Risk": "Ты спокойно относишься к риску и высоким ставкам.",
    "Auto": "Тебе легко действовать самостоятельно, без постоянного контроля.",
    "Struct": "Тебе комфортно с чёткими правилами и порядком.",
    "Pace": "Тебе нравится работать в быстром, динамичном темпе.",
    "Predict": "Тебе комфортно с новизной и неожиданными поворотами.",
    "Acad": "У тебя есть терпение долго и системно учиться одному делу.",
    "PhysSt": "У тебя достаточно выносливости для физической нагрузки.",
    "Math": "Тебе легко даются математика и алгоритмы.",
}

# A, E are always direct; D is always situational; B, C are direct while
# shallow and situational once the question goes deep (see "Правило формата"
# in profi_axes_phase1.md).
_ALWAYS_DIRECT = {AxisFamily.A, AxisFamily.E}
_ALWAYS_SITUATIONAL = {AxisFamily.D}
_MIXED_SITUATIONAL_FROM_DEPTH = 2


def is_valid_axis(code: str) -> bool:
    return code in AXIS_CODES


def format_for_axis(axis_code: str, depth: int) -> Literal["direct", "situational"]:
    axis = _AXIS_BY_CODE.get(axis_code)
    if axis is None:
        raise ValueError(f"Unknown axis code: {axis_code!r}")
    if axis.family in _ALWAYS_DIRECT:
        return "direct"
    if axis.family in _ALWAYS_SITUATIONAL:
        return "situational"
    return "situational" if depth >= _MIXED_SITUATIONAL_FROM_DEPTH else "direct"
