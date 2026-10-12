"""Belbin BTRSPI contracts (PRO-338 Ф2.4 / PROFY-012).

Each block, including unspent points, can be stored as a draft and restored on
another client. Scoring remains a separate one-shot submission of all seven
blocks, so partial progress can never be mistaken for a completed run.
"""
import uuid
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.validation import ANSWER_MAP_MAX_ITEMS, AnswerMapKey

# One block's `{item_id: points}`. Which items and how many points is checked
# against the bank afterwards; this only stops a map of any size getting there.
BlockAllocation = Annotated[dict[AnswerMapKey, int], Field(max_length=ANSWER_MAP_MAX_ITEMS)]


class SubmitBelbinRequest(BaseModel):
    # Exactly 7 blocks, in section order (I..VII) — each block a raw
    # `{item_id: points}` map, re-validated server-side by
    # ipsative_battery.validate_allocation (Ф0.6), never trusted as-is.
    allocations: list[BlockAllocation] = Field(min_length=7, max_length=7)

    model_config = {"extra": "forbid"}


class SubmitBelbinResponse(BaseModel):
    run_id: uuid.UUID
    role_totals: dict[str, int]


class SaveBelbinProgressRequest(BaseModel):
    allocation: BlockAllocation

    model_config = {"extra": "forbid"}


class BelbinProgressBlock(BaseModel):
    block_index: int
    allocation: dict[str, int]


class BelbinProgressResponse(BaseModel):
    completed: bool
    blocks: list[BelbinProgressBlock]


class BelbinContentItem(BaseModel):
    id: str
    text: str


class BelbinContentSection(BaseModel):
    section: str
    title: str
    items: list[BelbinContentItem]


class BelbinContentResponse(BaseModel):
    """PRO-338 Ф2.6's own prerequisite: the frontend needs the 56 item texts
    to render, and nothing exposed them over the API before this (only the
    submit contract above existed). Deliberately excludes each item's
    `role` — the whole point of an ipsative test is that the respondent
    never learns which statement counts toward which role, same
    non-disclosure principle already used for Elers' buffer items and
    Kondash's subscales elsewhere in this epic."""

    instruction: str
    block_total: int
    sections: list[BelbinContentSection]
