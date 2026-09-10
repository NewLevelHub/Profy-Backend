"""Student-facing /result v2 contract — see frontend-result-api-contract.md
(parent ProOf/ folder) for the agreed shape this mirrors exactly.

Deliberately separate from app/schemas/admin_result.py (the raw/admin
shape) — this is the only schema a student ever sees: no percentages, no
match_score, no raw category letters/keys outside of `interest_map[].code`
and `careers[].slug`, which are opaque identifiers, not scores.

Discriminated union on `interest_instrument` rather than one flat model:
"MI with a non-empty careers list" or "8 RIASEC interest items" must be
impossible to construct at all, not just something the assembler happens
to never do. `ResultResponseV2` (bare Union) is what code that needs
`isinstance()`/type hints should import — Python's isinstance() works on a
bare `Union`/`X | Y` since 3.10 but not on an `Annotated[...]` wrapper.
`ResultV2Schema` (Annotated + discriminator) is what FastAPI's
`response_model` and the cache (de)serializer (`ResultV2Adapter`) use — it's
the one that gets pydantic to actually pick the right branch instead of
just trying both.
"""
import uuid
from datetime import datetime
from typing import Annotated, Literal, Union

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

# Closing encouragement under junior's "Что можно попробовать" list — same
# pattern as DISCLAIMER: fixed, server-authored framing, not LLM text, so it
# can't be dropped/mangled by a bad generation. A *default*, not a required
# field, so an already-cached response serialized before this field existed
# still deserializes cleanly (ResultV2Adapter.validate_json in
# report_service.py) instead of raising on a missing key. Present on both
# branches (mirrors exploration_activities itself) even though it's only
# ever meaningful for junior — the frontend component already no-ops when
# exploration_activities is empty, which it always is for riasec.
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

_MI_INTEREST_COUNT = 8  # len(mi_content.MI_LABELS) — every MI category, always
_RIASEC_INTEREST_COUNT = 6  # len(riasec_content.RIASEC_LABELS) — every Holland letter, always
_PERSONALITY_TRAIT_COUNT = 5  # len(bigfive_content.PERSONALITY_LABELS) — every Big Five domain, always
_MAX_CAREERS = 10

_model_config = {"extra": "forbid"}


# --- Psychology block sections (PRO-282 epic) -------------------------------
# Skeleton only. Each section is `null` in /result until its phase lands the
# calculation (validity → Фаза 1 PRO-296…300, psychoemotional → Фаза 2
# PRO-307…309, mac → Фаза 3 PRO-314…318). Every phase extends its own model
# below with concrete fields. `consent_ok` is the one field defined now — it
# mirrors the stored parental consent (consent_service.has_consent, scope
# "psych_block") and is a *flag*, not a gate: MVP (PRO-282 §3/§4) shows the
# section regardless of its value. Section *visibility* is decided in
# exactly one place — report_service.psych_sections_for — never here.


class ValiditySection(BaseModel):
    """«Достоверность протокола» ("шкала лжи"). Assembled from the
    `assessment_validity` row (report_service._build_validity_section) — the
    whole section is `null` until validity_service (PRO-299) computes that
    row. Never cached: re-attached on every /result request, so an old
    cached report just carries `validity: null` and these required fields
    never have to deserialize from stale data.

    Specialist-facing verdict (PRO-300): traffic light + the numbers behind
    it. The traffic light itself is `traffic_light`; `sd_level` is the
    finer 0-8 / 9-15 / 16-20 band (9-15 is green — see psych-block-spec.md
    §A5). Interpretation copy for the three states lives on the frontend
    (psychValidity namespace)."""

    consent_ok: bool = False
    traffic_light: Literal["green", "yellow", "red"]
    sd_raw: int  # 0-20 MC-SDS matches
    sd_level: Literal["ok", "social_desirability", "high"]
    sd_bounds: tuple[int, int]  # [ok_max, sd_max] applied — сколько до жёлтого
    longstring_max: int
    irv: float
    infrequency_failed: int
    careless_flag: bool
    # Which app/data/validity_thresholds.json version produced the verdict —
    # surfaced with the "пороги ориентировочны до локальной калибровки" note.
    thresholds_version: int
    model_config = _model_config


class PsychoEmotionalSection(BaseModel):
    """«Психоэмоциональный тест» (МЦВ Собчик). Название «Люшер» в продукте
    не используется (PRO-282 §4). Assembled from the LATEST `psychoemotional_runs`
    row (report_service._build_psychoemotional_section); `null` until a run
    is scored. PRO-305 wires the row lookup + `thresholds_version` /
    `validity_flag`; the full metric display fields land with PRO-309."""

    consent_ok: bool = False
    thresholds_version: int | None = None
    # Достоверность прохождения (§B7) — считается отдельно от метрик.
    validity_flag: Literal["ok", "caution", "low"] | None = None
    model_config = _model_config


class MacSection(BaseModel):
    """МАК — метафорические ассоциативные карты. Без скоринга и
    ИИ-интерпретации (PRO-282 §4): Фаза 3 наполняет это лентой
    "стимул → карта → тексты", собранной из таблиц `mac_*`."""

    consent_ok: bool = False
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
    (Field constraint below), same for every age group/interest_instrument:
    unlike interests, the Big Five instrument itself never varies by age
    (only the *wording* does — junior gets simplified phrasing, see
    bigfive_content.personality_notes_for_age — the shape here is
    identical either way)."""

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


class StudentInterestMapItem(BaseModel):
    code: str
    sphere: str
    level: Literal["low", "medium", "high"]  # render-state only, never a number
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
    # Big Five is answered identically by all three age groups (only the
    # interest instrument/motivation format branch by age — TZ_Profi.md's
    # confirmed methodology: junior = MI + Big Five + Harter, middle =
    # RIASEC + Big Five + Harter, senior = RIASEC + Big Five + triplets),
    # so this lives on the common base, not per-branch.
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
    validity: ValiditySection | None = None
    psychoemotional: PsychoEmotionalSection | None = None
    mac: MacSection | None = None
    created_at: datetime
    model_config = _model_config


class MiResultResponse(_ResultResponseBase):
    """junior — TZ_Profi.md §4.1: not career-oriented at all. `careers` is
    pinned to an empty list at the schema level (max_length=0), not just
    "the assembler happens to always pass []" — constructing this class
    with any career is a ValidationError, not a silent bug."""

    interest_instrument: Literal["mi"] = "mi"
    interest_map: list[StudentInterestMapItem] = Field(min_length=_MI_INTEREST_COUNT, max_length=_MI_INTEREST_COUNT)
    careers: list[StudentCareer] = Field(default_factory=list, max_length=0)
    exploration_activities: list[str] = Field(min_length=1)


class RiasecResultResponse(_ResultResponseBase):
    """middle/senior. `is_flat_profile` (TZ_Profi.md §16.6) no longer bounds
    `careers` — a flat profile gets the same ranked top-10 as everyone else
    (product decision, 2026-08-17); the honest disclaimer lives in `summary`
    instead, not in a shortened/uniform-tier career list."""

    interest_instrument: Literal["riasec"] = "riasec"
    interest_map: list[StudentInterestMapItem] = Field(
        min_length=_RIASEC_INTEREST_COUNT, max_length=_RIASEC_INTEREST_COUNT
    )
    careers: list[StudentCareer] = Field(max_length=_MAX_CAREERS)
    exploration_activities: list[str] = Field(default_factory=list, max_length=0)


ResultResponseV2 = Union[MiResultResponse, RiasecResultResponse]
ResultV2Schema = Annotated[ResultResponseV2, Field(discriminator="interest_instrument")]
ResultV2Adapter: TypeAdapter[ResultResponseV2] = TypeAdapter(ResultV2Schema)
