"""Student-facing /result v2 contract — see frontend-result-api-contract.md
(parent ProOf/ folder) for the agreed shape this mirrors exactly.

Deliberately separate from app/schemas/admin_result.py (the raw/admin
shape) — this is the only schema a student ever sees: no percentages, no
match_score, no raw category letters/keys outside of `interest_map[].code`
and `careers[].slug`, which are opaque identifiers, not scores.

`ResultResponseV2` / `ResultV2Schema` are the RIASEC result — the only
shape since the junior MI branch was removed (PRO-425). `ResultV2Adapter`
is the cache (de)serializer.
"""
import uuid
from datetime import datetime
from typing import Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

# TZ_Profi.md §17.5 point 7 / Приложение C В.2: every report must carry this
# framing, verbatim and unconditionally — server-authored, not LLM text, so
# it can never be paraphrased away or dropped by a bad generation. Separate
# from `summary` (which also carries the same idea in its own words per the
# narrative pipeline's own prompt/validator — this field is the guarantee,
# that one is the personalization).
DISCLAIMER = (
    "Это не окончательный выбор, а карта возможных направлений — со временем "
    "картина может измениться, и это нормально."
)

# Closing line of the old junior "Что можно попробовать" list. Kept in the
# contract (with `exploration_activities`, always empty now) because the
# frontend still reads both; the component no-ops on an empty list.
EXPLORATION_CLOSING_NOTE = (
    "Не обязательно пробовать всё сразу — начни с того, что откликается "
    "больше всего. Даже маленький шаг сегодня помогает лучше понять, что "
    "тебе действительно нравится."
)

# Default for `interest_map_note` — a *default*, not a required field, same
# reasoning as EXPLORATION_CLOSING_NOTE: an already-cached response
# serialized before this field existed must still deserialize cleanly
# (ResultV2Adapter.validate_json in report_service.py) rather than raising.
# report_v2_assembler.build_interest_map_note() overrides this with a real,
# personalized note every time a fresh response is assembled.
INTEREST_MAP_NOTE_FALLBACK = (
    "Карта показывает, какие сферы проявляются ярче, а какие — тише. Это не "
    "оценка, а просто снимок текущего состояния."
)

# Same reasoning again for `final_analysis` — a plain default so old cached
# responses (from before this field existed) don't fail to deserialize.
FINAL_ANALYSIS_FALLBACK = (
    "Каждый раздел этого отчёта — отдельный кусочек общей картины: не "
    "разрозненные факты, а разные стороны одного и того же человека. "
    "Используй их вместе, а не по одному, когда будешь решать, что "
    "попробовать дальше."
)

# Same reasoning again for `personality_note` — a plain default so old
# cached responses (from before this field existed) don't fail to
# deserialize. report_v2_assembler.build_personality_note() overrides this
# with a real synthesis every time a fresh response is assembled.
PERSONALITY_NOTE_FALLBACK = (
    "Каждая черта характера проявляется по-своему — вместе они складываются "
    "в общую картину того, как тебе комфортнее действовать и общаться."
)

_RIASEC_INTEREST_COUNT = 6  # len(riasec_content.RIASEC_LABELS) — every Holland letter, always
_PERSONALITY_TRAIT_COUNT = 5  # len(bigfive_content.PERSONALITY_LABELS) — every Big Five domain, always
_MAX_CAREERS = 10

_model_config = {"extra": "forbid"}


# --- Psychology block sections (PRO-282 epic) -------------------------------
# Skeleton only. Each section is `null` in /result until its phase lands the
# calculation (validity → Фаза 1 PRO-296…300, psychoemotional → Фаза 2
# PRO-307…309). Every phase extends its own model
# below with concrete fields. `consent_ok` is the one field defined now — it
# mirrors the stored parental consent (consent_service.has_consent, scope
# "psych_block") and is a *flag*, not a gate: MVP (PRO-282 §3/§4) shows the
# section regardless of its value. Section *visibility* is decided in
# exactly one place — report_service.psych_sections_for — never here.





# --- Психоэмоциональный тест: вложенные структуры вывода (§B8) --------------
_PsychoAnxietyLevel = Literal["low", "moderate", "high", "very_high"]
_PsychoCompensationLevel = Literal["low", "moderate", "high"]
_PsychoSoLevel = Literal["norm", "elevated", "high"]
_PsychoVkLevel = Literal["low_tone", "reduced", "balance", "overexcited"]


class PsychoEmotionalPositionalPair(BaseModel):
    """§B5.1 — пара цветов по позициям списка 2 с функциональным знаком."""

    sign: Literal["plus", "cross", "equal", "minus"]
    colors: tuple[int, int]  # ID цветов (0–7) на этих двух позициях
    model_config = _model_config


class PsychoEmotionalSplitPair(BaseModel):
    """§B5.2 — пара из списка 1: `stable` → рядом в списке 2 `( )`,
    иначе расщеплена `[ ]`."""

    colors: tuple[int, int]
    stable: bool
    model_config = _model_config


class PsychoEmotionalAnxiety(BaseModel):
    """§B5.3 — индекс тревоги: сумма, уровень, вклад каждого основного цвета."""

    score: int  # 0–12
    level: _PsychoAnxietyLevel
    breakdown: dict[str, int]  # color_id → вклад (0/1/2/3)
    model_config = _model_config


class PsychoEmotionalCompensation(BaseModel):
    """§B5.4 — индекс компенсации: сумма, уровень, вклад доп. цветов + пометка
    про фиолетовый (в подсчёт не входит)."""

    score: int  # 0–9
    level: _PsychoCompensationLevel
    breakdown: dict[str, int]  # color_id → вклад (0/1/2/3)
    purple_forward: bool  # фиолетовый (ID 5) на позициях 1–3
    purple_position: int  # ранг фиолетового 1–8
    model_config = _model_config


class PsychoEmotionalHistoryItem(BaseModel):
    """Компактная строка предыдущего прохождения для динамики (§B8)."""

    run_number: int
    completed_at: datetime
    so: int | None  # None, если то прохождение не было посчитано
    anxiety_score: int | None
    validity_flag: Literal["ok", "caution", "low"] | None
    model_config = _model_config


class PsychoEmotionalSection(BaseModel):
    """«Психоэмоциональный тест» (МЦВ Собчик). Название «Люшер» в продукте
    не используется (PRO-282 §4). Собирается из ПОСЛЕДНЕЙ строки
    `psychoemotional_runs` + всех предыдущих для динамики
    (report_service._build_psychoemotional_section). `null`, пока последнее
    прохождение не посчитано движком (PRO-307) — так же, как validity.

    Состав вывода специалисту (§B8 / PRO-309): идентификация + динамика,
    check-in, флаг достоверности прохождения, списки 1/2 + D, функциональные
    пары с ( )/[ ], индексы тревоги / компенсации / СО / ВК с уровнями и
    раскладками, структурные индексы без уровней. Никогда не кэшируется —
    переприкрепляется на каждый запрос /result. Постоянная пометка «шкала
    взрослая…» и тексты направлений структурных индексов — на фронте
    (psychEmotional namespace, PRO-293).

    Текстовые подсказки-гипотезы (был `hints: list[str]`, PRO-304/307) убраны
    по решению владельца: адресат — дипломированный психолог, готовые
    формулировки по ресёрчу ему не нужны и могут сбивать с толку. Трактовка
    метрик/раскладок — целиком за специалистом."""

    consent_ok: bool = False
    thresholds_version: int | None = None

    # Идентификация прохождения + динамика (§B8)
    run_number: int  # номер этого прохождения (1 = первое)
    completed_at: datetime
    history: list[PsychoEmotionalHistoryItem] = Field(default_factory=list)  # предыдущие, новые сверху

    # Check-in — 3 ответа, в формулы не входят (форма — за контентом PRO-303)
    checkin: dict = Field(default_factory=dict)

    # Достоверность прохождения (§B7 / PRO-308) — считается отдельно от метрик,
    # на них не влияет. `None` / [] пока прохождение не посчитано.
    validity_flag: Literal["ok", "caution", "low"] | None = None
    validity_reasons: list[str] = Field(default_factory=list)

    # Списки выбора (цвета по позициям) + расхождение D (§B5.7)
    choice_1: list[int]
    choice_2: list[int]
    d_value: int  # 0–32, чётное
    d_memory: bool  # D = 0 — второй выбор по памяти
    d_situationally_unstable: bool  # D ≥ 20 — трактовать метрики осторожно

    # Функциональные пары (§B5.1–B5.2)
    positional_pairs: list[PsychoEmotionalPositionalPair]
    root_conflict: tuple[int, int]  # первый / последний цвет списка 2
    split_pairs: list[PsychoEmotionalSplitPair]
    split_count: int  # 0–4
    instability: bool  # ≥ 3 расщеплённых

    # Индексы
    anxiety: PsychoEmotionalAnxiety
    compensation: PsychoEmotionalCompensation
    so_value: int  # 0–32
    so_level: _PsychoSoLevel
    vk_value: float  # 0.2–5.0
    vk_level: _PsychoVkLevel

    # Отдельный красный флаг (§B6): чёрный (ID 7) на позиции 1 — подростковый
    # маркер риска, подсветка для беседы, не автоматический вывод.
    black_first: bool

    model_config = _model_config


class StudentStrengthCard(BaseModel):
    title: str
    description: str
    model_config = _model_config


class StudentThinkingStyleNote(BaseModel):
    title: str
    description: str
    model_config = _model_config


class StudentPersonalityNote(BaseModel):
    """"Твой характер" — one card per Big Five domain, always exactly 5
    (Field constraint below); wording from bigfive_content.personality_notes."""

    trait: str  # "openness" | "conscientiousness" | "extraversion" | "agreeableness" | "emotional_stability"
    label: str  # "Открытость новому" — for display
    description: str
    # Default (not required), same reasoning as EXPLORATION_CLOSING_NOTE
    # above: an already-cached response serialized before this field existed
    # must still deserialize cleanly (ResultV2Adapter.validate_json in
    # report_service.py) rather than raising. build_personality_notes
    # (via bigfive_content.relative_bands) always populates a real value on
    # every freshly-assembled response.
    level: Literal["low", "medium", "high"] = "medium"
    model_config = _model_config


class StudentInterestQuote(BaseModel):
    text: str
    answer: Literal["like", "dislike"]
    model_config = _model_config


class StudentInterestDetails(BaseModel):
    """"Why this level" breakdown for one RIASEC type (PRO-336) — built from
    the student's own answers, so a counsellor or parent can see what the
    level is made of instead of just the label."""

    answered: int
    # Answer counts, strongest liking first:
    # [очень нравится, нравится, не уверен, не нравится, совсем не нравится].
    distribution: list[int] = Field(min_length=5, max_length=5)
    likes: int
    dislikes: int
    # 0-100 share of the maximum possible score — positions the level meter
    # against the LEVEL_MEDIUM_MIN/LEVEL_HIGH_MIN marks. The UI shows counts
    # ("17 из 24"), never this value as a printed percentage.
    score: float
    means: str
    follows: str
    quotes: list[StudentInterestQuote] = []
    model_config = _model_config


class StudentInterestMapItem(BaseModel):
    code: str
    sphere: str
    level: Literal["low", "medium", "high"]  # render-state only
    # None for responses cached before PRO-336.
    details: StudentInterestDetails | None = None
    model_config = _model_config


class StudentInterestCombination(BaseModel):
    """How the two most pronounced RIASEC types sit on Holland's hexagon."""

    codes: list[str] = Field(min_length=2, max_length=2)
    relation: Literal["adjacent", "alternate", "opposite"]
    text: str
    model_config = _model_config


class StudentCareer(BaseModel):
    slug: str
    name: str
    rank: int
    tier: Literal["strong", "good", "worth_trying"]
    why: str = Field(min_length=1)  # never empty — TZ_Profi.md §18.2
    matched_strengths: list[str] = []  # legitimately empty when why falls back to the neutral phrase
    try_now: str = Field(min_length=1)  # never empty — always has a safe fallback, see riasec_content.NEUTRAL_TRY_NOW
    description: str | None = None
    skills_needed: list[str] = []
    subjects_to_develop: list[str] = []
    model_config = _model_config


class _ResultResponseBase(BaseModel):
    report_version: Literal[2] = 2
    assessment_id: uuid.UUID
    summary: str = Field(min_length=1)
    disclaimer: str = DISCLAIMER
    strength_cards: list[StudentStrengthCard]
    # 1-2 sentences summarizing the interest_map itself (which spheres are
    # most/least pronounced) — the numeric map (per-branch below) has no
    # prose at all on its own. Deterministic, server-authored (report_v2_
    # assembler.build_interest_map_note), not LLM — it's a straight read of
    # already-computed levels, nothing to personalize beyond that.
    interest_map_note: str = INTEREST_MAP_NOTE_FALLBACK
    thinking_style_notes: list[StudentThinkingStyleNote]
    personality_notes: list[StudentPersonalityNote] = Field(
        min_length=_PERSONALITY_TRAIT_COUNT, max_length=_PERSONALITY_TRAIT_COUNT
    )
    # 1-2 sentences of synthesis on top of the 5 static cards above — same
    # role as interest_map_note, closing the "just a lookup table, no
    # analysis" gap reported live for "Твой характер". Deterministic,
    # server-authored (report_v2_assembler.build_personality_note), not LLM.
    personality_note: str = PERSONALITY_NOTE_FALLBACK
    motivation_highlights: list[str]
    is_flat_profile: bool
    exploration_note: str = EXPLORATION_CLOSING_NOTE
    # Shown last on the page, after every other section — ties the report
    # together instead of repeating `summary` (written first). LLM-
    # personalized when available, same pipeline as summary/strength_cards
    # (report_narrative_service), with a deterministic fallback either way.
    final_analysis: str = FINAL_ANALYSIS_FALLBACK
    # Psychology block — see the *Section models above. `None` until the
    # matching phase ships; attached by report_service._attach_psych_sections
    # (isolated — a failing calculation is logged and leaves its section
    # `None`, never breaking the main report). A plain default, so an already
    # -cached response serialized before these fields existed still
    # deserializes cleanly (ResultV2Adapter.validate_json in
    # report_service.py) — same precedent as EXPLORATION_CLOSING_NOTE etc.

    psychoemotional: PsychoEmotionalSection | None = None
    created_at: datetime
    model_config = _model_config


class RiasecResultResponse(_ResultResponseBase):
    """`is_flat_profile` (TZ_Profi.md §16.6) no longer bounds
    `careers` — a flat profile gets the same ranked top-10 as everyone else
    (product decision, 2026-08-17); the honest disclaimer lives in `summary`
    instead, not in a shortened/uniform-tier career list."""

    interest_instrument: Literal["riasec"] = "riasec"
    interest_map: list[StudentInterestMapItem] = Field(
        min_length=_RIASEC_INTEREST_COUNT, max_length=_RIASEC_INTEREST_COUNT
    )
    # None when the second-most pronounced type is below "medium" — a pair
    # isn't meaningful then — and for responses cached before PRO-336.
    interest_combination: StudentInterestCombination | None = None
    careers: list[StudentCareer] = Field(max_length=_MAX_CAREERS)
    exploration_activities: list[str] = Field(default_factory=list, max_length=0)


ResultResponseV2 = RiasecResultResponse
ResultV2Schema = RiasecResultResponse
ResultV2Adapter: TypeAdapter[ResultResponseV2] = TypeAdapter(ResultV2Schema)


class ResultPendingReviewResponse(BaseModel):
    """What `GET /result/{id}` and `POST /result/generate` return while the
    report still waits for a psychologist to publish it
    (docs/psychologist-review-gate-plan.md §2). A 200 with its own `status`
    field rather than a 403/404: the frontend already treats 403 on this
    endpoint as a foreign/stale session and resets assessment state.

    Never cached — the report cache only ever holds published reports."""

    status: Literal["pending_review"] = "pending_review"
    assessment_id: uuid.UUID
    model_config = _model_config


ResultOrPendingSchema = Union[ResultV2Schema, ResultPendingReviewResponse]
