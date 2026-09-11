import uuid
from typing import Any

from pydantic import BaseModel, model_validator

from app.models.motivation import MotivationCategory
from app.models.profile import AgeGroup
from app.models.question import BigFiveDomain, HollandType, Keyed, MIType, QuestionInstrument


class AdminFieldOverride(BaseModel):
    """One admin edit to a bank-seeded field, with what it replaced.

    `bank_value` is what the content bank had at the time, kept so the UI can
    show "было / стало" and offer a revert that works immediately.

    It is absent on overrides written before that was recorded, where the
    original is unknown; reverting those still drops the override and lets the
    next seed run restore the bank's own value. Absence and null are different
    things here — several overridable columns (icon, short_text, frame) are
    nullable, so a null bank_value is a real value to put back.

    JSON has no way to say "absent" once this is serialized — a missing key
    and a null one both arrive as null — so `bank_value_known` carries that
    distinction explicitly. Without it the UI would show "было: (пусто)" for
    every override migrated from the old flat shape and offer a revert that
    restores nothing."""

    value: Any = None
    bank_value: Any = None
    bank_value_known: bool = False

    @model_validator(mode="before")
    @classmethod
    def _record_whether_the_original_is_known(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {**data, "bank_value_known": "bank_value" in data}
        return data


# --- Questions (RIASEC / Big Five / MI, one shared table) ---


class AdminQuestionListItem(BaseModel):
    id: uuid.UUID
    instrument: QuestionInstrument
    text: str
    order: int
    age_tier: AgeGroup
    riasec_type: HollandType | None
    bigfive_domain: BigFiveDomain | None
    mi_category: MIType | None
    has_overrides: bool

    model_config = {"from_attributes": True}


class AdminQuestionListResponse(BaseModel):
    items: list[AdminQuestionListItem]
    total: int
    page: int
    limit: int

    model_config = {"from_attributes": True}


class AdminQuestionDetail(BaseModel):
    id: uuid.UUID
    instrument: QuestionInstrument
    riasec_type: HollandType | None
    bigfive_domain: BigFiveDomain | None
    mi_category: MIType | None
    facet: int | None
    keyed: Keyed | None
    text: str
    short_text: str | None
    icon: str | None
    order: int
    age_tier: AgeGroup
    overrides: dict[str, AdminFieldOverride]

    model_config = {"from_attributes": True}


class AdminQuestionUpdateRequest(BaseModel):
    riasec_type: HollandType | None = None
    bigfive_domain: BigFiveDomain | None = None
    mi_category: MIType | None = None
    facet: int | None = None
    keyed: Keyed | None = None
    text: str | None = None
    age_tier: AgeGroup | None = None
    short_text: str | None = None
    icon: str | None = None


# --- Question pairs (forced-choice) ---


class AdminQuestionPairListItem(BaseModel):
    """`option_a_text`/`option_b_text` here are the **effective** option texts
    — what the student actually sees — resolved through the same fallback
    chain as question_pair_service._to_option(): pair override, else the
    linked Question's short_text, else its text. They are never null, unlike
    the same-named *raw override* columns on AdminQuestionPairDetail below,
    which are what a PATCH writes. Editing forms must read the detail
    endpoint: prefilling a form from this list would turn a displayed
    fallback into a real override on the first save."""

    id: uuid.UUID
    instrument: QuestionInstrument
    age_tier: AgeGroup
    pair_index: int
    frame: str | None
    option_a_text: str
    option_b_text: str
    has_overrides: bool

    model_config = {"from_attributes": True}


class AdminQuestionPairListResponse(BaseModel):
    items: list[AdminQuestionPairListItem]
    total: int
    page: int
    limit: int

    model_config = {"from_attributes": True}


class AdminLinkedQuestion(BaseModel):
    """The Question a pair option points at, inlined so the admin can see the
    fallback text/icon an empty override resolves to without a second request
    per option."""

    id: uuid.UUID
    text: str
    short_text: str | None
    icon: str | None

    model_config = {"from_attributes": True}


class AdminQuestionPairDetail(BaseModel):
    id: uuid.UUID
    instrument: QuestionInstrument
    age_tier: AgeGroup
    pair_index: int
    question_a_id: uuid.UUID
    question_b_id: uuid.UUID
    question_a: AdminLinkedQuestion | None = None
    question_b: AdminLinkedQuestion | None = None
    frame: str | None
    option_a_text: str | None
    option_b_text: str | None
    option_a_icon: str | None
    option_b_icon: str | None
    overrides: dict[str, AdminFieldOverride]

    model_config = {"from_attributes": True}


class AdminQuestionPairUpdateRequest(BaseModel):
    frame: str | None = None
    option_a_text: str | None = None
    option_b_text: str | None = None
    option_a_icon: str | None = None
    option_b_icon: str | None = None


# --- Motivation statements (senior's MOST/LEAST triplets) ---


class AdminMotivationStatementListItem(BaseModel):
    id: uuid.UUID
    triplet_index: int
    order: int
    category: MotivationCategory
    text: str
    has_overrides: bool

    model_config = {"from_attributes": True}


class AdminMotivationStatementListResponse(BaseModel):
    items: list[AdminMotivationStatementListItem]
    total: int
    page: int
    limit: int

    model_config = {"from_attributes": True}


class AdminMotivationStatementDetail(BaseModel):
    id: uuid.UUID
    triplet_index: int
    order: int
    category: MotivationCategory
    text: str
    text_junior: str | None
    overrides: dict[str, AdminFieldOverride]

    model_config = {"from_attributes": True}


class AdminMotivationStatementUpdateRequest(BaseModel):
    category: MotivationCategory | None = None
    text: str | None = None
    text_junior: str | None = None


# --- Motivation pairs (junior/middle Harter-style pairs) ---


class AdminMotivationPairListItem(BaseModel):
    """Nine categories over eighteen pairs means category_a/category_b alone
    identify no row uniquely — each label pair occurs exactly twice. text_a/
    text_b are the only fields that tell two rows apart in a list."""

    id: uuid.UUID
    pair_index: int
    category_a: MotivationCategory
    category_b: MotivationCategory
    text_a: str
    text_b: str
    has_overrides: bool

    model_config = {"from_attributes": True}


class AdminMotivationPairListResponse(BaseModel):
    items: list[AdminMotivationPairListItem]
    total: int
    page: int
    limit: int

    model_config = {"from_attributes": True}


class AdminMotivationPairDetail(BaseModel):
    id: uuid.UUID
    pair_index: int
    category_a: MotivationCategory
    category_b: MotivationCategory
    text_a: str
    text_b: str
    overrides: dict[str, AdminFieldOverride]

    model_config = {"from_attributes": True}


class AdminMotivationPairUpdateRequest(BaseModel):
    category_a: MotivationCategory | None = None
    category_b: MotivationCategory | None = None
    text_a: str | None = None
    text_b: str | None = None


# --- Directions (career/profession catalog) ---


class AdminDirectionListItem(BaseModel):
    """`empty_catalog_fields` names the descriptive fields that are still
    empty on this row (of description/professions/skills_needed/
    subjects_to_develop/first_steps), so the list can mark half-filled
    directions instead of hiding the gap until someone opens the detail.
    `catalog_filled` is just "that list is empty"."""

    id: uuid.UUID
    name: str
    slug: str
    holland_code: str
    programs_count: int
    catalog_filled: bool
    empty_catalog_fields: list[str]
    has_overrides: bool

    model_config = {"from_attributes": True}


class AdminDirectionListResponse(BaseModel):
    items: list[AdminDirectionListItem]
    total: int
    page: int
    limit: int

    model_config = {"from_attributes": True}


class AdminDirectionProgram(BaseModel):
    """A program mapped to this direction through `program_directions`. The
    mapping drives career matching, so an admin editing a direction needs to
    see what it currently pulls in — until now the table existed but was
    invisible from the admin side."""

    id: uuid.UUID
    name: str
    university_id: uuid.UUID
    university_name: str

    model_config = {"from_attributes": True}


class AdminDirectionDetail(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    holland_code: str
    description: str
    professions: list
    skills_needed: list
    subjects_to_develop: list
    first_steps: list
    programs: list[AdminDirectionProgram] = []
    overrides: dict[str, AdminFieldOverride]

    model_config = {"from_attributes": True}


class AdminDirectionUpdateRequest(BaseModel):
    name: str | None = None
    holland_code: str | None = None
    description: str | None = None
    professions: list | None = None
    skills_needed: list | None = None
    subjects_to_develop: list | None = None
    first_steps: list | None = None
