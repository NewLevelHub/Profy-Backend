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
