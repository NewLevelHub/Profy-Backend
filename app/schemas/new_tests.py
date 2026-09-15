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
    способностей. 5 шкал: Ч-П/Ч-Т/Ч-Ч/Ч-З/Ч-Х."""

    scores: dict[str, float] | None = None
    top_type: str | None = None
    abilities_score: float | None = None
    model_config = _model_config


class TeamRoleSection(BaseModel):
    """Belbin BTRSPI — 7 блоков ипсативного распределения, own table
    (belbin_runs, Ф2.3), not Question-based. `methodological_note` carries
    the source's 18+/corporate-context caveat (epic decision table §2) as a
    note for the specialist, not a code-gated restriction."""

    scores: dict[str, float] | None = None
    top_roles: list[str] | None = None
    methodological_note: str | None = None
    model_config = _model_config


class TemperamentSection(BaseModel):
    """Eysenck EPI (адапт. Шмелева) — 57 Да/Нет. Экстраверсия/Нейротизм/
    шкала лжи, quadrant = один из 4 темпераментов (Scatter Plot)."""

    extraversion: float | None = None
    neuroticism: float | None = None
    lie_scale: float | None = None
    quadrant: str | None = None
    model_config = _model_config


class IntelligenceSection(BaseModel):
    """АСТУР (Акимова/Борисова/Гуревич и др., ПИ РАО 1995) — 98 заданий,
    7 из 8 субтестов, own table (Ф3.3), not Question-based."""

    spn_group: int | None = None
    subtest_scores: dict[str, float] | None = None
    learning_profile: str | None = None
    model_config = _model_config


class AspirationLevelSection(BaseModel):
    """Elers achievement motivation — 41 Да/Нет (9 буферных). 1 шкала."""

    score: int | None = None
    level: str | None = None
    model_config = _model_config


class EmpathyConfidenceSection(BaseModel):
    """Бойко (эмпатия, 6 каналов) + Кондаш/Прихожан (межличностная
    тревожность, инвертирована в "уверенность", стены 1-10)."""

    empathy_channels: dict[str, float] | None = None
    empathy_total: float | None = None
    confidence_stens: int | None = None
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
