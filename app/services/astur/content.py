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
    BankSubtest,
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


def _shuffle_off_key(concepts: list[str], rng: random.Random) -> None:
    """The bank stores the correct order, so a plain shuffle hands the
    solved chain back 1 time in n! — for bank v1 (items of 4–5 concepts)
    about one attempt in four got a pre-solved item worth full marks
    (PRO-430). Reshuffle until the served order differs from the key."""
    if len(set(concepts)) < 2:
        return
    key = list(concepts)
    while concepts == key:
        rng.shuffle(concepts)


def _shuffle_public_item(item: dict, subtest: BankSubtest, rng: random.Random) -> None:
    """Shuffle the served copy of an item in place (PRO-441). The bank lists
    the right answer near the top — in v1 the classification pair is almost
    always words 1–2, the awareness/analogies option mostly 2nd — so served
    in bank order the position gives the answer away. Scoring matches by
    text, never by position, so any order scores the same.

    Left in bank order: geometric figures (options А–Г are bound to their
    images and letters, see STIMULUS_KEYS), lability, numeric series and
    generalization (nothing to pick from)."""
    if subtest.key in STIMULUS_KEYS:
        return
    if subtest.scoring_method == "chain_links":
        _shuffle_off_key(item["concepts"], rng)
    elif subtest.scoring_method == "pick_pair":
        rng.shuffle(item["words"])
    elif subtest.scoring_method == "single_choice":
        rng.shuffle(item["options"])


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
            # Seeded per attempt and item: a reload or a resume on another
            # device gets the same order, another attempt a different one.
            _shuffle_public_item(public, subtest, random.Random(f"{run_id}:{item['item_id']}"))
            items.append(public)
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
