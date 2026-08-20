"""Shared 0-100 scoring-tier thresholds for RIASEC/MI instruments.

Single source of truth for what counts as "high"/"low" on this scale —
used both to label interest_map spheres (report_v2_assembler._level) and
to gate which types qualify as a vetted "strength"/"weakness"
(riasec_service/mi_service.strengths_weaknesses). Keeping these in one
place is what stops the two from disagreeing about whether a given score
is a real signal — found live: a type sitting at the scale's floor (tied
with three "weaknesses") was still surfaced as a strength by
strengths_weaknesses' old top-3-by-rank logic, while interest_map
correctly showed the same type as "low" — the report contradicted itself
between two sections built from the identical underlying score.
"""

LEVEL_HIGH_MIN: float = 70.0
LEVEL_MEDIUM_MIN: float = 50.0
LEVEL_LOW_MAX: float = 30.0
