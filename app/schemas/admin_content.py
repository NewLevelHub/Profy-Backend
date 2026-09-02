import uuid

from pydantic import BaseModel

from app.models.motivation import MotivationCategory
from app.models.profile import AgeGroup
from app.models.question import BigFiveDomain, HollandType, Keyed, MIType, QuestionInstrument


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
    overrides: dict

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
    id: uuid.UUID
    instrument: QuestionInstrument
    age_tier: AgeGroup
    pair_index: int
    has_overrides: bool

    model_config = {"from_attributes": True}


class AdminQuestionPairListResponse(BaseModel):
    items: list[AdminQuestionPairListItem]
    total: int
    page: int
    limit: int

    model_config = {"from_attributes": True}


class AdminQuestionPairDetail(BaseModel):
    id: uuid.UUID
    instrument: QuestionInstrument
    age_tier: AgeGroup
    pair_index: int
    question_a_id: uuid.UUID
    question_b_id: uuid.UUID
    frame: str | None
    option_a_text: str | None
    option_b_text: str | None
    option_a_icon: str | None
    option_b_icon: str | None
    overrides: dict

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
    overrides: dict

    model_config = {"from_attributes": True}


class AdminMotivationStatementUpdateRequest(BaseModel):
    category: MotivationCategory | None = None
    text: str | None = None
    text_junior: str | None = None


# --- Motivation pairs (junior/middle Harter-style pairs) ---


class AdminMotivationPairListItem(BaseModel):
    id: uuid.UUID
    pair_index: int
    category_a: MotivationCategory
    category_b: MotivationCategory
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
    overrides: dict

    model_config = {"from_attributes": True}


class AdminMotivationPairUpdateRequest(BaseModel):
    category_a: MotivationCategory | None = None
    category_b: MotivationCategory | None = None
    text_a: str | None = None
    text_b: str | None = None


# --- Directions (career/profession catalog) ---


class AdminDirectionListItem(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    holland_code: str
    has_overrides: bool

    model_config = {"from_attributes": True}


class AdminDirectionListResponse(BaseModel):
    items: list[AdminDirectionListItem]
    total: int
    page: int
    limit: int

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
    overrides: dict

    model_config = {"from_attributes": True}


class AdminDirectionUpdateRequest(BaseModel):
    name: str | None = None
    holland_code: str | None = None
    description: str | None = None
    professions: list | None = None
    skills_needed: list | None = None
    subjects_to_develop: list | None = None
    first_steps: list | None = None
