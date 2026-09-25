"""Versioned scoring formulas for АСТУР (`app/data/astur_scoring_rules.json`).

A result snapshot records `scoring_version`; the numbers behind that version
never change after release, so any snapshot can be explained later by
looking its version up here.
"""
import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "astur_scoring_rules.json"

LEGACY_SCORING_VERSION = "legacy-1"


class ScoringRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    # Subtests averaged (equal weight) into the overall percent.
    overall_subtests: tuple[str, ...]
    # Knowledge profile: the leader must beat the runner-up by at least
    # max(profile_leading_min_pp, profile_leading_min_items of the smaller
    # of the two compared areas, in pp) — one item must never decide it.
    profile_leading_min_pp: float
    profile_leading_min_items: int
    # Share of an area's items that must have a non-blank answer, else the
    # profile is "insufficient_data".
    profile_min_answered_share: float
    # |physics_math knowledge % − numeric series %| at or above this is shown
    # as a divergence between knowing terms and solving number problems.
    math_gap_min_pp: float
    # Fewer on-time quick commands than this → halves are not compared.
    quick_min_on_time: int
    # A subtest submitted later than its time limit + grace is flagged.
    subtest_overtime_grace_sec: int
    # A subtest with at least this share of blank answers is flagged.
    blank_share_flag: float
    # Own-name quick command: also treat Latin vowels as vowels (a name
    # typed in Latin). False in versions released before this fix.
    own_name_latin_vowels: bool = False


@lru_cache
def _load() -> dict:
    return json.loads(_RULES_PATH.read_text(encoding="utf-8"))


def current_version() -> str:
    return _load()["current"]


@lru_cache
def get_rules(version: str | None = None) -> ScoringRules:
    data = _load()
    version = version or data["current"]
    raw = data["versions"].get(version)
    if raw is None:
        raise KeyError(f"unknown АСТУР scoring version {version!r}")
    return ScoringRules(version=version, **raw)
