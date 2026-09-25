"""Public АСТУР content for the test-taker: one bank version in the
attempt's own locale, stripped of every key/tier/reviewer field."""
import random
import uuid

from app.i18n import pick_locale, pick_locale_list
from app.services.astur.bank import (
    LOCALIZED_LIST_FIELDS,
    LOCALIZED_SCALAR_FIELDS,
    PUBLIC_ITEM_FIELDS,
    STIMULUS_KEYS,
    AsturBank,
    stimulus_for,
)


def _public_value(field: str, value: object, locale: str) -> object:
    if field in LOCALIZED_SCALAR_FIELDS:
        return pick_locale(value, locale)
    if field in LOCALIZED_LIST_FIELDS:
        # A copy: the bank object is cached and shared across requests.
        return list(pick_locale_list(value, locale))
    return value


def _public_stimulus(item: dict) -> dict | None:
    stimulus = stimulus_for(item)
    if stimulus is None:
        return None
    return {
        "target": stimulus["target"]["path"],
        "options": {letter: entry["path"] for letter, entry in stimulus["options"].items()},
    }


def build_content(bank: AsturBank, *, bank_version: int, run_id: uuid.UUID, locale: str) -> dict:
    """`locale` is the attempt's own (`AsturRun.locale`), never the current
    request's — switching the app language mid-attempt must not swap the
    language of items the attempt is scored in."""
    subtests = []
    for subtest in sorted(bank.subtests, key=lambda s: s.number):
        fields = PUBLIC_ITEM_FIELDS[subtest.key]
        items = []
        for item in subtest.items:
            public = {"item_id": item["item_id"], **{f: _public_value(f, item.get(f), locale) for f in fields}}
            if subtest.key in STIMULUS_KEYS:
                public["stimulus"] = _public_stimulus(item)
            items.append(public)
        if subtest.scoring_method == "chain_links":
            # The bank stores the correct order — hand out a shuffled copy.
            for item in items:
                random.shuffle(item["concepts"])
        subtests.append({
            "number": subtest.number,
            "key": subtest.key,
            "name": pick_locale(subtest.name, locale),
            "instruction": pick_locale(subtest.instruction, locale),
            "item_count": len(subtest.items),
            "time_limit_sec": subtest.time_limit_sec,
            "items": items,
        })
    return {
        "run_id": run_id,
        "bank_version": bank_version,
        "locale": locale,
        "subtests": subtests,
        "lability_item_limit_ms": bank.lability_item_limit_ms,
    }
