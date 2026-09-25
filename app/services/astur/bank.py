"""The АСТУР bank document — one immutable version of the whole test.

A version carries everything that has to change together (PRO-427): RU/KK
wording, options, answer keys, open-answer synonym tiers, scoring method per
subtest, timers and stable item ids. Scoring an attempt only ever reads the
version the attempt was pinned to, so publishing a new version never changes
a past result.

Items stay plain dicts: their shape depends on the subtest's `scoring_method`
and is enforced by `bank_validation`, not by a model per method — the bank is
authored as JSON (admin editor / `app/data/astur_bank_v1.json`), and a dict
round-trips through JSONB and the editor without a lossy model in between.
"""
import hashlib
import json
from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

ScoringMethod = Literal[
    "single_choice",      # pick one option; answer = option text
    "pick_pair",          # pick exactly 2 words out of `words`
    "open_text_tiers",    # free text matched against score_2 / score_1 synonym tiers
    "chain_links",        # reorder `concepts`; 1 point per restored adjacent link
    "number_pair",        # type the next 2 numbers of `sequence`
    "quick_instruction",  # timed 2-way commands (lability); never in the overall percent
]

# Each subtest key is rendered by its own frontend component, so a key is
# bound to exactly one scoring method — a version can reword/re-key items but
# cannot turn, say, "analogies" into an open-text subtest.
METHOD_BY_KEY: dict[str, ScoringMethod] = {
    "awareness": "single_choice",
    "analogies": "single_choice",
    "lability": "quick_instruction",
    "classification": "pick_pair",
    "generalization": "open_text_tiers",
    "logical_schemas": "chain_links",
    "numeric_series": "number_pair",
    "geometric_figures": "single_choice",
}

QUICK_INSTRUCTIONS_KEY = "lability"
# Subtests whose items carry a subject-area tag feeding the knowledge profile.
SUBJECT_TAGGED_KEYS = ("awareness", "generalization")
NUMERIC_SERIES_KEY = "numeric_series"
SPATIAL_KEY = "geometric_figures"

# Localized fields, per item, that the test-taker sees. Everything else on an
# item is a key, a synonym tier or reviewer metadata and never leaves the server.
PUBLIC_ITEM_FIELDS: dict[str, tuple[str, ...]] = {
    "awareness": ("text", "options"),
    "analogies": ("pair", "third", "options"),
    "lability": ("instruction", "answer_format", "options"),
    "classification": ("words",),
    "generalization": ("pair",),
    "logical_schemas": ("concepts",),
    "numeric_series": ("sequence",),
    # Stimulus is a static frontend image addressed by item position.
    "geometric_figures": (),
}
LOCALIZED_SCALAR_FIELDS = frozenset({"text", "third", "instruction"})
LOCALIZED_LIST_FIELDS = frozenset({"options", "pair", "words", "concepts", "answer", "score_2", "score_1"})

V1_PATH = Path(__file__).resolve().parents[2] / "data" / "astur_bank_v1.json"


class BankSubtest(BaseModel):
    model_config = ConfigDict(frozen=True)

    number: int
    key: str
    name: dict[str, str]
    instruction: dict[str, str]
    scoring_method: ScoringMethod
    # None only for quick instructions — they use a per-command limit.
    time_limit_sec: int | None
    items: list[dict]

    def item_max(self, item: dict) -> int:
        if self.scoring_method == "open_text_tiers":
            return 2
        if self.scoring_method == "chain_links":
            return len(item["concepts"]["ru"]) - 1
        return 1

    @property
    def max_score(self) -> int:
        return sum(self.item_max(item) for item in self.items)


class AsturBank(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int
    subjects: dict[str, dict[str, str]]
    lability_item_limit_ms: int
    subtests: list[BankSubtest]

    @cached_property
    def _by_key(self) -> dict[str, BankSubtest]:
        return {s.key: s for s in self.subtests}

    @cached_property
    def _by_number(self) -> dict[int, BankSubtest]:
        return {s.number: s for s in self.subtests}

    def subtest(self, key: str) -> BankSubtest | None:
        return self._by_key.get(key)

    def subtest_by_number(self, number: int) -> BankSubtest | None:
        return self._by_number.get(number)

    @property
    def required_keys(self) -> set[str]:
        """Every subtest must be submitted before an attempt can be finalized."""
        return set(self._by_key)

    def max_scores(self) -> dict[str, int]:
        return {s.key: s.max_score for s in self.subtests if s.scoring_method != "quick_instruction"}


def canonical_json(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(document: dict) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def parse_bank(document: dict) -> AsturBank:
    return AsturBank.model_validate(document)


def load_v1_document() -> dict:
    return json.loads(V1_PATH.read_text(encoding="utf-8"))
