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

from pydantic import BaseModel, Field, TypeAdapter, model_validator

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

_MI_INTEREST_COUNT = 8  # len(mi_content.MI_LABELS) — every MI category, always
_RIASEC_INTEREST_COUNT = 6  # len(riasec_content.RIASEC_LABELS) — every Holland letter, always
_MAX_CAREERS = 5
_FLAT_PROFILE_CAREER_COUNT = 3

_model_config = {"extra": "forbid"}


class StudentStrengthCard(BaseModel):
    title: str
    description: str
    model_config = _model_config


class StudentThinkingStyleNote(BaseModel):
    title: str
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
    thinking_style_notes: list[StudentThinkingStyleNote]
    motivation_highlights: list[str]
    is_flat_profile: bool
    exploration_note: str = EXPLORATION_CLOSING_NOTE
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
    """middle/senior. Flat profile (TZ_Profi.md §16.6) forces exactly 3
    careers, all tier="worth_trying" — enforced here, not just by whatever
    report_v2_assembler.py happens to build, so a future assembler bug
    can't silently ship 2 or 4."""

    interest_instrument: Literal["riasec"] = "riasec"
    interest_map: list[StudentInterestMapItem] = Field(
        min_length=_RIASEC_INTEREST_COUNT, max_length=_RIASEC_INTEREST_COUNT
    )
    careers: list[StudentCareer] = Field(max_length=_MAX_CAREERS)
    exploration_activities: list[str] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def _flat_profile_has_exactly_three_worth_trying_careers(self) -> "RiasecResultResponse":
        if not self.is_flat_profile:
            return self
        if len(self.careers) != _FLAT_PROFILE_CAREER_COUNT or any(c.tier != "worth_trying" for c in self.careers):
            raise ValueError(
                f"flat profile must have exactly {_FLAT_PROFILE_CAREER_COUNT} worth_trying careers, "
                f"got {[(c.slug, c.tier) for c in self.careers]}"
            )
        return self


ResultResponseV2 = Union[MiResultResponse, RiasecResultResponse]
ResultV2Schema = Annotated[ResultResponseV2, Field(discriminator="interest_instrument")]
ResultV2Adapter: TypeAdapter[ResultResponseV2] = TypeAdapter(ResultV2Schema)
