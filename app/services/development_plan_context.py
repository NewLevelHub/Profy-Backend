"""Assemble the full generation input for the development plan.

Everything the two LLM phases need: the student context (reused from
`student_context.build_student_context`), the backend-computed admission facts
(reused from `university_requirements.map_program_requirement`), the curriculum
slices per required subject, and the stage slots derived from the student's
grade. No LLM calls here — pure data assembly.
"""
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.kz_curriculum_bank import CANONICAL_SUBJECTS, CURRICULUM_BANK
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment
from app.models.direction import Direction
from app.models.profile import Profile
from app.models.program import Program
from app.models.university import University
from app.prompts.development_plan import MANDATORY_ENT_SUBJECTS, stage_slots_for_grade
from app.schemas.development_plan import AdmissionFacts
from app.schemas.student_context import StudentContext
from app.services import direction_service
from app.services.student_context import build_student_context
from app.services.university_requirements import map_program_requirement

_KZ_COUNTRY_NAMES = {"казахстан", "kazakhstan", "қазақстан", "kz"}

# General, per-country admission-route text (NOT per-university). Only used when
# `is_foreign`. Deliberately vague — the exact route is on the university's site.
_FOREIGN_ROUTE_BY_COUNTRY: dict[str, str] = {
    "великобритания": (
        "после 11 классов РК напрямую на английский бакалавриат в UK обычно "
        "не берут — нужен подготовительный год (foundation year) при вузе или "
        "колледже-партнёре, либо международные экзамены (A-levels / IB)"
    ),
    "сша": (
        "в вузы США поступают после 11 классов, но обычно нужны стандартные "
        "тесты (SAT/ACT) и языковой экзамен (TOEFL/IELTS); часть вузов просит "
        "дополнительный год подготовки"
    ),
    "нидерланды": (
        "часть программ в Нидерландах принимает после 11 классов РК напрямую, "
        "часть требует год foundation или первый курс местного вуза — уточняй "
        "по каждой программе"
    ),
}
_DEFAULT_FOREIGN_ROUTE = (
    "после 11 классов РК на английский бакалавриат за рубежом часто нельзя "
    "напрямую — уточни на сайте вуза, нужен ли подготовительный год "
    "(foundation), международные экзамены (A-levels / IB) или год местного вуза"
)

_LANGUAGE_EXAM_BY_COUNTRY: dict[str, str] = {
    "великобритания": "IELTS Academic",
    "нидерланды": "IELTS Academic",
    "сша": "TOEFL iBT",
    "канада": "IELTS Academic",
    "германия": "TestDaF или IELTS Academic",
}
_DEFAULT_LANGUAGE_EXAM = "IELTS Academic или TOEFL iBT"


@dataclass
class GenerationInput:
    assessment_id: uuid.UUID
    program_id: uuid.UUID
    direction_slug: str
    direction_name: str
    grade: int
    city: str
    university_name: str
    specialty: str
    is_foreign: bool
    foreign_route: str | None
    language_exam: str | None
    stage_slots: list[tuple[str, str]]
    subjects_needed: list[str]
    student_context: StudentContext
    admission_facts: dict
    curriculum_slices: dict = field(default_factory=dict)


def curriculum_slice(subject: str, grade: int) -> dict | None:
    """A few EARLY-GRADE foundation topics for one subject — used only as
    concrete *examples* of "check your base bottom-up" anchor points, not to
    build a plan from. `None` if the bank has nothing for this subject.

    ENT prep is "review from grades 5-9 upward, find where it gets hard"
    (a method), so we hand the model 2 topics from grade 8 + 1 from grade 9
    to illustrate ("проверь 'Квадратные уравнения' за 8 класс"). No quarter
    logic, no "topics for your grade" — that made the plan too shallow.
    """
    g8 = sorted(CURRICULUM_BANK.get((subject, 8)) or [], key=lambda e: e["order"])
    g9 = sorted(CURRICULUM_BANK.get((subject, 9)) or [], key=lambda e: e["order"])
    anchors: list[str] = []
    anchors += [f'{e["topic"]} (за 8 класс)' for e in g8[:2]]
    anchors += [f'{e["topic"]} (за 9 класс)' for e in g9[:1]]
    if not anchors:
        return None
    return {"anchor_examples": anchors}


def _normalize_subject(raw: str) -> str | None:
    """Map a free-text exam name onto a CANONICAL_SUBJECTS entry, or None."""
    low = raw.strip().lower()
    for subject in CANONICAL_SUBJECTS:
        if subject in low or low in subject:
            return subject
    return None


def _subjects_needed(exams: list[str], *, is_foreign: bool) -> list[str]:
    """Profile-exam subjects (normalized). For a LOCAL university also add the
    compulsory ENT subject (история Казахстана). A foreign plan has no ЕНТ
    line (only an optional backup), so nothing is injected there. The ЕНТ
    literacy sections are never subjects — see ENT_LITERACY_NOTE."""
    out: list[str] = []
    for exam in exams or []:
        norm = _normalize_subject(exam)
        if norm and norm not in out:
            out.append(norm)
    if not is_foreign:
        for subject in MANDATORY_ENT_SUBJECTS:
            if subject not in out:
                out.append(subject)
    return out




def _provenance(program: Program, university: University) -> tuple[str | None, str | None]:
    """Best available source_url + last_verified date (YYYY-MM-DD)."""
    checked: list[str] = []
    for sources in (program.fact_sources or {}, university.fact_sources or {}):
        for entry in sources.values():
            if isinstance(entry, dict) and entry.get("checked_at"):
                checked.append(str(entry["checked_at"]))
    last_verified = max(checked) if checked else None
    source_url = program.source_url or university.source_url or university.website
    return source_url, last_verified


async def build_generation_input(
    assessment_id: uuid.UUID, program_id: uuid.UUID, db: AsyncSession
) -> GenerationInput | None:
    assessment = (
        await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    ).scalar_one_or_none()
    if assessment is None:
        return None

    profile = (
        await db.execute(select(Profile).where(Profile.id == assessment.profile_id))
    ).scalar_one_or_none()
    if profile is None:
        return None

    row = (
        await db.execute(
            select(Program, University)
            .join(University, Program.university_id == University.id)
            .where(Program.id == program_id)
        )
    ).first()
    if row is None:
        return None
    program, university = row

    analysis = (
        await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
        )
    ).scalar_one_or_none()
    if analysis is None:
        return None

    slug = direction_service.best_matching_slug(
        program.profession_slugs or [], list(analysis.careers or [])
    )
    if slug is None:
        return None
    direction = await direction_service.get_direction_by_slug(slug, db)
    direction_name = direction.name if direction else slug

    student_context = await build_student_context(assessment_id, db)
    if student_context is None:
        return None

    req = map_program_requirement(program, university)
    is_foreign = university.country.strip().lower() not in _KZ_COUNTRY_NAMES
    country_key = university.country.strip().lower()
    foreign_route = (
        _FOREIGN_ROUTE_BY_COUNTRY.get(country_key, _DEFAULT_FOREIGN_ROUTE)
        if is_foreign
        else None
    )
    language_exam = (
        _LANGUAGE_EXAM_BY_COUNTRY.get(country_key, _DEFAULT_LANGUAGE_EXAM)
        if is_foreign
        else None
    )
    source_url, last_verified = _provenance(program, university)

    facts = AdmissionFacts(
        **req.model_dump(),
        is_foreign=is_foreign,
        foreign_route=foreign_route,
        language_exam=language_exam,
        source_url=source_url,
        last_verified=last_verified,
    )

    subjects_needed = _subjects_needed(req.exams, is_foreign=is_foreign)
    slices: dict[str, dict] = {}
    for subject in subjects_needed:
        sl = curriculum_slice(subject, profile.grade)
        if sl is not None:
            slices[subject] = sl

    return GenerationInput(
        assessment_id=assessment_id,
        program_id=program_id,
        direction_slug=slug,
        direction_name=direction_name,
        grade=profile.grade,
        city=profile.city,
        university_name=university.name,
        specialty=program.name,
        is_foreign=is_foreign,
        foreign_route=foreign_route,
        language_exam=language_exam,
        stage_slots=stage_slots_for_grade(profile.grade),
        subjects_needed=subjects_needed,
        student_context=student_context,
        admission_facts=facts.model_dump(mode="json"),
        curriculum_slices=slices,
    )
