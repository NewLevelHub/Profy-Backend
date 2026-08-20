"""Shared age-branch visibility rule — junior/middle/senior nesting.

A shorter test is always a PREFIX of a longer one (junior ⊆ middle ⊆ senior),
not a separate curated set — see scripts/riasec_question_bank.py and
scripts/bigfive_question_bank.py for how age_tier is assigned per item."""

from app.models.profile import AgeGroup

_ORDER: list[AgeGroup] = [AgeGroup.junior, AgeGroup.middle, AgeGroup.senior]


def visible_tiers(age_group: AgeGroup) -> list[AgeGroup]:
    """Age tiers of questions visible to a user in `age_group` — junior sees
    only junior-tier questions, middle sees junior+middle, senior sees all."""
    return _ORDER[: _ORDER.index(age_group) + 1]
