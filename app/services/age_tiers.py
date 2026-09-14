"""Shared age-branch visibility rule — junior/middle/senior nesting.

A shorter test is always a PREFIX of a longer one (junior ⊆ middle ⊆ senior),
not a separate curated set — see scripts/riasec_question_bank.py and
scripts/bigfive_question_bank.py for how age_tier is assigned per item."""

from app.models.profile import AgeGroup
from app.models.question import QuestionInstrument

_ORDER: list[AgeGroup] = [AgeGroup.junior, AgeGroup.middle, AgeGroup.senior]

# Instruments no longer served to new assessments (docs/big-five-retirement.md).
# Deliberately a query-layer exclusion, not a bank/seed-script change — the
# bank/DB rows stay untouched forever so historical UserResponse rows never
# cascade-delete (see scripts/seed_bigfive_questions.py's orphan-delete pass).
RETIRED_INSTRUMENTS: frozenset[QuestionInstrument] = frozenset({QuestionInstrument.big_five})


def visible_tiers(age_group: AgeGroup) -> list[AgeGroup]:
    """Age tiers of questions visible to a user in `age_group` — junior sees
    only junior-tier questions, middle sees junior+middle, senior sees all."""
    return _ORDER[: _ORDER.index(age_group) + 1]
