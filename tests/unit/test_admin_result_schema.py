"""Contract tests for the admin-only raw result schema (app/schemas/admin_result.py).

Pure schema validation against in-memory `AnalysisResult` ORM objects — no DB
round trip needed, since pydantic's `from_attributes=True` just reads
attributes off whatever object it's given. Proves the schema stays valid for
both interest instruments (MI for junior, RIASEC for middle/senior) and
keeps every admin-only numeric/raw field, independent of whatever the
student-facing schema in app/schemas/result.py does later.
"""

import uuid
from datetime import datetime, timezone

from app.models.analysis_result import AnalysisResult
from app.schemas.admin_result import AdminAnalysisResultResponse


def _analysis(*, profile: dict, code: list[str], meta: dict, careers: list[dict] | None = None) -> AnalysisResult:
    return AnalysisResult(
        id=uuid.uuid4(),
        assessment_id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        summary="Тестовое резюме",
        profile=profile,
        code=code,
        meta=meta,
        careers=careers or [],
        strengths=[],
        weaknesses=[],
        development_plan={"reinforce": [], "compensate": []},
        big_five={"N": 40.0, "E": 60.0, "O": 70.0, "A": 55.0, "C": 65.0},
        thinking_style={"creative_think": 50.0, "systematic": 40.0, "strategic": 30.0, "practical": 60.0},
        personality_highlights=[],
        motivation={"interest": 6, "money": 2},
        motivation_top=["interest"],
        motivation_highlights=[],
        personality_profile={"openness": 70.0},
        personality_notes={"openness": "..."},
        strength_cards=[],
        thinking_style_notes=[],
        report_version=1,
    )


def test_junior_mi_raw_profile_validates_without_assuming_holland_keys() -> None:
    analysis = _analysis(
        profile={"logical": 80.0, "musical": 20.0},
        code=["logical", "verbal"],
        meta={"differentiation": 60.0, "consistency": "high", "aversion": {"musical": 1}},
    )

    validated = AdminAnalysisResultResponse.model_validate(analysis)

    assert validated.code == ["logical", "verbal"]
    assert validated.profile["logical"] == 80.0
    assert validated.meta.consistency == "high"


def test_middle_senior_riasec_raw_profile_validates() -> None:
    analysis = _analysis(
        profile={"R": 80.0, "I": 60.0},
        code=["R", "I"],
        meta={"differentiation": 20.0, "consistency": "medium", "aversion": {"C": 2}},
    )

    validated = AdminAnalysisResultResponse.model_validate(analysis)

    assert validated.code == ["R", "I"]
    assert validated.profile["R"] == 80.0
    assert validated.meta.consistency == "medium"


def test_admin_response_keeps_numeric_and_raw_fields() -> None:
    analysis = _analysis(
        profile={"R": 80.0},
        code=["R"],
        meta={"differentiation": 20.0, "consistency": "medium", "aversion": {}},
        careers=[{
            "slug": "it", "name": "IT", "holland_code": "RIA", "match_score": 42,
            "description": "", "professions": [], "skills_needed": [],
            "subjects_to_develop": [], "first_steps": [],
        }],
    )

    validated = AdminAnalysisResultResponse.model_validate(analysis)

    # These are exactly the fields the eventual student-schema cleanup is
    # expected to drop — asserting they still round-trip here is what keeps
    # that future change from silently breaking the admin panel.
    assert validated.big_five == {"N": 40.0, "E": 60.0, "O": 70.0, "A": 55.0, "C": 65.0}
    assert validated.motivation == {"interest": 6, "money": 2}
    assert validated.personality_profile == {"openness": 70.0}
    assert validated.careers[0].match_score == 42
