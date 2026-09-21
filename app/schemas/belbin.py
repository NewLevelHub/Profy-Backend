"""Belbin BTRSPI submit contract (PRO-338 Ф2.4). One-shot submission —
unlike psychoemotional's checkin/circle1/circle2 two-phase contract, Belbin
has no natural "before/after the main battery" split (Ф2.3's own decision
not to mirror that structure), so the whole 7-block allocation is sent and
scored in a single call."""
import uuid

from pydantic import BaseModel, Field


class SubmitBelbinRequest(BaseModel):
    # Exactly 7 blocks, in section order (I..VII) — each block a raw
    # `{item_id: points}` map, re-validated server-side by
    # ipsative_battery.validate_allocation (Ф0.6), never trusted as-is.
    allocations: list[dict[str, int]] = Field(min_length=7, max_length=7)

    model_config = {"extra": "forbid"}


class SubmitBelbinResponse(BaseModel):
    run_id: uuid.UUID
    role_totals: dict[str, int]


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
