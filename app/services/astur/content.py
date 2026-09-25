"""Public АСТУР content for the test-taker: one bank version, resolved to the
request locale, stripped of every key/tier/reviewer field."""
import random
import uuid

from app.i18n import pick_locale, pick_locale_list
from app.services.astur.bank import (
    LOCALIZED_LIST_FIELDS,
    LOCALIZED_SCALAR_FIELDS,
    PUBLIC_ITEM_FIELDS,
    AsturBank,
)


def _public_value(field: str, value: object) -> object:
    if field in LOCALIZED_SCALAR_FIELDS:
        return pick_locale(value)
    if field in LOCALIZED_LIST_FIELDS:
        # A copy: the bank object is cached and shared across requests.
        return list(pick_locale_list(value))
    return value


def build_content(bank: AsturBank, *, bank_version: int, run_id: uuid.UUID | None) -> dict:
    subtests = []
    for subtest in sorted(bank.subtests, key=lambda s: s.number):
        fields = PUBLIC_ITEM_FIELDS[subtest.key]
        items = [{f: _public_value(f, item.get(f)) for f in fields} for item in subtest.items]
        if subtest.scoring_method == "chain_links":
            # The bank stores the correct order — hand out a shuffled copy.
            for item in items:
                random.shuffle(item["concepts"])
        subtests.append({
            "number": subtest.number,
            "key": subtest.key,
            "name": pick_locale(subtest.name),
            "instruction": pick_locale(subtest.instruction),
            "item_count": len(subtest.items),
            "time_limit_sec": subtest.time_limit_sec,
            "items": items,
        })
    return {
        "run_id": run_id,
        "bank_version": bank_version,
        "subtests": subtests,
        "lability_item_limit_ms": bank.lability_item_limit_ms,
    }
