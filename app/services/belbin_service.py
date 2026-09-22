"""Submit + score + interpret a Belbin BTRSPI run (PRO-338 Ф2.4/Ф2.5).

Submit (Ф2.4): validates all 7 blocks against `scripts/belbin_bank.py`'s
content (Ф2.2) via `ipsative_battery.validate_allocation` (Ф0.6 — 422 on any
mismatch, never trusts the client's own live-remaining-points UI), then
aggregates into `role_totals` via `ipsative_battery.aggregate_by_key`, and
persists one append-only `BelbinRun` row (Ф2.3 — `assessment_id` is not
unique, a resubmit is a new row, not an overwrite).

Interpretation (Ф2.5): `interpret_role_totals()` ranks the 8 roles by score
into dominant / supporting / avoidance per the spec's own rule. Deliberately
NOT built here: the spec's "composite team analysis" (overlaying several
employees' profiles, epic doc п.18) — explicitly out of MVP scope per the
Ф2.5 ticket, this product is per-student, not multi-user. Nothing in this
module accepts more than one `role_totals` at a time; adding that later is a
new function, not an extension of this one."""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BelbinThresholds, belbin_thresholds
from app.i18n import pick_locale, get_locale
from app.models.belbin_run import BelbinRun
from app.services import ipsative_battery
from scripts.belbin_bank import BLOCK_TOTAL, ITEM_ROLE, ROLES, SECTIONS, INSTRUCTION


async def get_belbin_config(db: AsyncSession, ignore_override: bool = False) -> dict:
    base = {
        "instruction": INSTRUCTION,
        "block_total": BLOCK_TOTAL,
        "sections": SECTIONS,
        "roles": ROLES,
        "item_role": ITEM_ROLE,
    }

    if ignore_override:
        return base

    from app.services.admin_content_service import get_content_override
    override = await get_content_override(db, "belbin")

    if override:
        locale = get_locale()
        override_data = override.content_ru if locale == "ru" else override.content_kk
        if not override_data and locale == "kk":
            override_data = override.content_ru
        if override_data:
            base.update(override_data)

    return base


async def build_content(db: AsyncSession, ignore_override: bool = False) -> dict:
    """`ignore_override` is the fallback path the router takes when a saved
    override doesn't resolve (admin's visual editor saved a section missing
    a locale) — rather than 500ing for every real test-taker until someone
    fixes the override, it re-renders straight from the bank."""
    config = await get_belbin_config(db, ignore_override=ignore_override)
            
    # Prepare sections for response
    sections_response = [
        {
            "section": section["section"],
            "title": pick_locale(section.get("title", "")),
            "items": [
                {"id": item["id"], "text": pick_locale(item.get("text", ""))} for item in section["items"]
            ],
        }
        for section in config["sections"]
    ]
    return {
        "instruction": pick_locale(config["instruction"]),
        "block_total": config["block_total"],
        "sections": sections_response,
    }


async def get_latest_run(assessment_id: uuid.UUID, db: AsyncSession) -> BelbinRun | None:
    """Append-only history (Ф2.3) — the specialist report (Ф2.7) always
    reads the most recent attempt, same "latest by created_at" convention
    as psychoemotional's `_latest_run`. `None` if Belbin was never
    assigned/completed for this assessment — a normal, common case (it's an
    optional psychologist-assigned block, not part of the main battery)."""
    return (
        await db.execute(
            select(BelbinRun)
            .where(BelbinRun.assessment_id == assessment_id)
            .order_by(BelbinRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def submit_run(
    assessment_id: uuid.UUID,
    allocations: list[dict[str, int]],
    *,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> BelbinRun:
    """`allocations` must be exactly 7 blocks in section order (I..VII) —
    schema-enforced length, block-to-section correspondence checked here.
    Raises HTTPException(422) via `validate_allocation` on the first block
    that doesn't sum to exactly `BLOCK_TOTAL` across exactly that section's
    8 item ids."""
    config = await get_belbin_config(db)
    for section, block in zip(config["sections"], allocations, strict=True):
        expected_items = [item["id"] for item in section["items"]]
        ipsative_battery.validate_allocation(block, expected_items=expected_items, total=config["block_total"])

    role_totals = ipsative_battery.aggregate_by_key(allocations, config["item_role"])

    run = BelbinRun(
        assessment_id=assessment_id,
        user_id=user_id,
        allocations=allocations,
        role_totals=role_totals,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def role_evidence(db: AsyncSession, run: BelbinRun) -> dict[str, dict]:
    """Per-role breakdown of the student's own point allocations across all
    7 blocks — the ipsative-battery equivalent of
    riasec_service.answer_evidence's "what is this score actually made of"
    evidence, for the psychologist report's "Почему такой результат" card.
    Pure function: `run.allocations` already carries every point the
    student assigned, no extra DB read needed (unlike the other 5 tests'
    evidence builders, all Question/UserResponse-based).

    Returns {role: {"points_by_block": [7 ints, block I..VII order],
    "items": [{"block", "text", "points"}, one per statement that role owns
    across all 7 blocks]}}.

    Tolerates fewer than 7 allocation blocks (a bare/partial `BelbinRun`,
    e.g. in a test fixture) by treating a missing block as unscored (0
    points for every item in it) rather than raising — a real submitted run
    always has exactly 7 (`submit_run` enforces it), so this only matters
    for incomplete data, which should degrade the evidence, not the whole
    report section."""
    config = await get_belbin_config(db)
    evidence: dict[str, dict] = {role: {"points_by_block": [], "items": []} for role in config["roles"]}
    for i, section in enumerate(config["sections"]):
        block = run.allocations[i] if i < len(run.allocations) else {}
        for item in section["items"]:
            role = item["role"]
            points = block.get(item["id"], 0)
            if role in evidence:
                evidence[role]["items"].append({
                    "block": section["section"],
                    "text": pick_locale(item["text"]),
                    "points": points,
                })

    for role, role_data in evidence.items():
        # Derive per-block totals for this role from the items we just grouped
        by_block = {item["block"]: 0 for item in role_data["items"]}
        for item in role_data["items"]:
            by_block[item["block"]] += item["points"]
        role_data["points_by_block"] = list(by_block.values())
    return evidence


@dataclass(frozen=True)
class BelbinInterpretation:
    # All 8 role codes, ranked highest score first. Ties broken by
    # `scripts/belbin_bank.ROLES`'s fixed key order — deterministic, not an
    # artifact of dict insertion order (which `aggregate_by_key` doesn't
    # guarantee is rank-meaningful).
    ranked_roles: list[str]
    dominant_role: str  # ranked_roles[0]
    supporting_roles: list[str]  # ranked_roles[1:3] — 2nd and 3rd place
    # Roles scoring at/below the configured cut-off (app/data/belbin_thresholds.json)
    # — a "delegate to others" zone. Independent of rank: a low-scoring role
    # can appear here regardless of where it lands in `ranked_roles`.
    avoidance_roles: list[str]


def interpret_role_totals(
    role_totals: dict[str, int],
    *,
    thresholds: BelbinThresholds = belbin_thresholds,
) -> BelbinInterpretation:
    """Ф2.5: доминирующая роль = максимум role_totals; 2-я и 3-я по рангу —
    поддерживающие; роли с баллом <= порога — зона избегания. Pure function,
    no DB — call with a `BelbinRun.role_totals` (or any dict shaped like
    it)."""
    canonical_order = list(ROLES.keys())
    ranked_roles = sorted(
        role_totals.keys(),
        key=lambda role: (-role_totals[role], canonical_order.index(role)),
    )
    avoidance_roles = [
        role for role in ranked_roles if thresholds.is_avoidance_zone(role_totals[role])
    ]
    return BelbinInterpretation(
        ranked_roles=ranked_roles,
        dominant_role=ranked_roles[0],
        supporting_roles=ranked_roles[1:3],
        avoidance_roles=avoidance_roles,
    )
