"""PRO-338 — specialist-only report sections for the 6 new tests
(Тикеты-новые-тесты/00-ЭПИК-PRO-338.md). Deliberately separate from
app/schemas/result_v2.py: that file's docstring states result_v2 is "the
only schema a student ever sees" — these 6 sections never reach a student,
only the psychologist/admin specialist report (Ф0.3's
GET /psychologist/students/{id}/assessments/{assessment_id}/report).

Every field is optional and defaults to None, same "all-None-way until the
real scoring service lands" convention as PRO-291's ValiditySection before
PRO-299/300 populated it — Ф1/Ф2/Ф3 phases fill these in per test as each
scoring engine ships, without a schema-breaking change. `extra="forbid"`
throughout so a builder can never accidentally pass through a stray raw
field from a JSONB container.
"""
from pydantic import BaseModel

_model_config = {"extra": "forbid"}


class ProfessionalTypesSection(BaseModel):
    """ДДО (Климов + Йовайши/Резапкина) — 20 форс-чойс пар + 5 Likert-пунктов
    способностей. 5 шкал (Latin keys, PRO-338 Ф1.2): practical (Ч-П),
    technical (Ч-Т), social (Ч-Ч), sign (Ч-З), artistic (Ч-Х).

    `interest_scores` (1 point per А/Б pick, from the 20 pairs) and
    `abilities_scores` (5 raw 0-3 Likert values) are deliberately two
    separate arrays, never merged into one "score" — the Radar Chart draws
    them as two overlaid polygons (Ф1.3), the delta between them is a
    frontend rendering concern, not something this section pre-computes.

    `hybrid_profile` is a bare [scale_a, scale_b] flag (top two interest
    scales within <=1 point of each other) with NO pre-baked list of
    example professions — the source document's "инженер-программист" is
    illustrative only, never a lookup table; the specialist interprets the
    flag themselves."""

    interest_scores: dict[str, int] | None = None
    hybrid_profile: list[str] | None = None
    abilities_scores: dict[str, int] | None = None
    model_config = _model_config


class TeamRoleSection(BaseModel):
    """Belbin BTRSPI — 7 блоков ипсативного распределения, own table
    (belbin_runs, Ф2.3), not Question-based. `methodological_note` carries
    the source's 18+/corporate-context caveat (epic decision table §2) as a
    note for the specialist, not a code-gated restriction.

    `ranked_roles` is all 8 role codes sorted by score descending (ties
    broken by belbin_bank.ROLES' fixed order, same as
    belbin_service.interpret_role_totals) — the Bar Chart (Ф2.7) renders
    bars in exactly this order, not `scores`' own (unordered) key order.
    `dominant_role`/`supporting_roles`/`avoidance_roles` are the same 3
    groups `interpret_role_totals` (Ф2.5) computes, carried through
    unchanged so the frontend colors bars by group without re-deriving the
    ranking or threshold logic itself."""

    scores: dict[str, int] | None = None
    ranked_roles: list[str] | None = None
    dominant_role: str | None = None
    supporting_roles: list[str] | None = None
    avoidance_roles: list[str] | None = None
    methodological_note: str | None = None
    model_config = _model_config


class TemperamentSection(BaseModel):
    """Eysenck EPI (адапт. Шмелева) — 57 Да/Нет, 3 scales. PRO-338 Ф1.5:
    raw sums + band labels + the lie-scale traffic-light flag
    (app/data/eysenck_thresholds.json — same versioned-config contract as
    ValidityThresholds/PsychoEmotionalThresholds). Ф1.6 adds `quadrant`.

    `extraversion_level`/`neuroticism_level` are plain band labels (Latin
    keys: deep_introvert/introvert/ambivert/extravert/bright_extravert;
    low/medium/high/very_high) — independent from `quadrant` (Latin keys:
    choleric/sanguine/phlegmatic/melancholic), a coarser 2x2 split at the
    (12, 12) midpoint of the same two raw scores, per the source's
    "сильный/слабый × уравновешенный/неуравновешенный × подвижный/инертный"
    formula — rendered as the Scatter Plot's 4 quadrants (Ф1.6)."""

    extraversion_raw: int | None = None
    neuroticism_raw: int | None = None
    lie_scale_raw: int | None = None
    extraversion_level: str | None = None
    neuroticism_level: str | None = None
    protocol_flagged: bool | None = None
    quadrant: str | None = None
    model_config = _model_config


class IntelligenceSection(BaseModel):
    """АСТУР (Акимова/Борисова/Гуревич и др., ПИ РАО 1995) — 98 заданий,
    7 из 8 субтестов, own table (astur_runs, Ф3.3), not Question-based.

    Ф3.7 extends the Ф0.2 stub (which only had spn_group/subtest_scores/
    learning_profile) with the fields astur_scoring.score_run() (Ф3.5)
    actually produces: `raw_score` (Line Chart needs a total, not just the
    per-subtest breakdown), `learning_profile_shares` (the ticket's own
    "с долями" requirement — `learning_profile` alone is just the winning
    subject key, not the 3-way split), and the 2 lability accuracy figures
    + `lability_fatigue_signal` (the JSON-boolean form of
    astur_scoring.is_fatigue_signal(), pre-computed here so the frontend
    never re-implements the >25%-drop rule) — lability is deliberately
    rendered as its own block, outside the Line Chart (Ф3.7's own
    "Отдельно" instruction), same as it's excluded from `raw_score`."""

    raw_score: int | None = None
    subtest_scores: dict[str, float] | None = None
    spn_group: int | None = None
    learning_profile: str | None = None
    learning_profile_shares: dict[str, float] | None = None
    lability_first_half_accuracy: float | None = None
    lability_second_half_accuracy: float | None = None
    lability_fatigue_signal: bool | None = None
    model_config = _model_config


class AspirationLevelSection(BaseModel):
    """Elers achievement motivation — 41 Да/Нет (9 буферных). 1 шкала."""

    score: int | None = None
    level: str | None = None
    model_config = _model_config


class EmpathyConfidenceSection(BaseModel):
    """Бойко (эмпатия, 6 каналов) + Кондаш/Прихожан (межличностная
    тревожность, инвертирована в "уверенность", стены 1-10). Ф1.11:
    `empathy_level`/`confidence_level` are band labels from
    app.config.boyko_empathy_thresholds/kondash_anxiety_thresholds — same
    "backend computes the label, frontend only maps it to copy" convention
    as every other scored section (elers' `level`, eysenck's
    `*_level`/`quadrant`)."""

    empathy_channels: dict[str, float] | None = None
    empathy_total: float | None = None
    empathy_level: str | None = None
    confidence_stens: int | None = None
    confidence_level: str | None = None
    model_config = _model_config


class NewTestsSections(BaseModel):
    """Bundle handed to the specialist report response (Ф0.3,
    PsychologistReportResponse) — one field per test, `None` when that
    test's builder had nothing to report (not yet taken, not yet scored, or
    its own build failed — new_tests_report_service isolates each builder
    so one failure never blanks the others)."""

    professional_types: ProfessionalTypesSection | None = None
    team_role: TeamRoleSection | None = None
    temperament: TemperamentSection | None = None
    intelligence: IntelligenceSection | None = None
    aspiration_level: AspirationLevelSection | None = None
    empathy_confidence: EmpathyConfidenceSection | None = None
    model_config = _model_config
