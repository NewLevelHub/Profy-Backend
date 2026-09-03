"""Single source of truth for turning a Program's raw `requirements`/`deadlines`/
`grants` JSON into clean, typed facts — used both by the direction-roadmap prompt
(`roadmap_builder.py`) and by the plain program-detail screen (`university_service.py`
-> `ProgramDetail.requirements_summary`). Previously each caller read the raw dicts
its own way; the plain program-detail page fell back to dumping unknown keys
(`notes`, `admission_scores_2026`) as raw joined text because it never went through
this mapping at all — see `ProgramDetailPage.tsx`'s `RequirementsTable`.

Program.requirements is heterogeneous by seed source (see app/models/direction.py-
style docstrings elsewhere): an older, richer hand-picked batch
(min_ent/min_gpa/min_sat/min_ielts/needs_*/extracurriculars) and the current bulk
`scripts/seed_kz_universities.py` batch (sparser: exams/notes, sometimes
min_ent_threshold or admission_scores_2026 from scripts/apply_grant_admission_data_2026.py).
`None` always means "no data", never "not required" — `dict.get` already gives us
that distinction, so never coerce a missing key to `False`.
"""
from app.i18n.catalog import tr
from app.models.program import Program
from app.models.university import University
from app.schemas.roadmap import ProgramGrant, UniversityRequirement

# The raw requirement flags this maps; labels resolve per locale (KZ-307).
_DOCUMENT_FLAGS = ("needs_essay", "needs_recommendations", "needs_interview")


def admission_scores_2026_brief(requirements: dict) -> list[str]:
    """Human-readable lines from the 2026-2027 grant-competition scores
    (scripts/apply_grant_admission_data_2026.py) — real min/max scores that
    won a grant this admission cycle, per quota/specialty."""
    entries = requirements.get("admission_scores_2026") or []
    briefs = []
    for e in entries:
        specialty = e.get("specialty_name", "")
        quota = e.get("quota", "")
        min_score = e.get("min_score")
        max_score = e.get("max_score")
        year = e.get("year", "")
        if min_score is None:
            continue
        score_range = f"{min_score}–{max_score}" if max_score is not None and max_score != min_score else str(min_score)
        briefs.append(
            tr("university_requirements")["admission_score_brief"].format(
                specialty=specialty, quota=quota, year=year, score_range=score_range
            )
        )
    return briefs


def _note_hint_for_program(notes: list[str], program_name: str) -> str | None:
    """`notes` is university-wide, not per-program (see module docstring) — we
    generally refuse to claim any one line is "the" requirement for a specific
    program. This is the one narrow, conservative exception: many notes lines
    are shaped "Category: subjects." (e.g. "Архитектура/дизайн: рисунок
    (творческий экзамен)."), and when the program's own name shares a real
    word with that category label, it's a genuine keyword match, not a guess
    — e.g. program "Архитектура" <-> note category "Архитектура/дизайн".
    Only ever consulted when `exams` came back empty; never overrides real
    per-program data."""
    name_words = {w.lower() for w in program_name.replace('/', ' ').split() if len(w) > 3}
    if not name_words:
        return None
    for note in notes:
        if ':' not in note:
            continue
        category = note.split(':', 1)[0]
        category_words = {w.lower() for w in category.replace('/', ' ').split() if len(w) > 3}
        if name_words & category_words:
            return note
    return None


def map_program_requirement(program: Program, university: University) -> UniversityRequirement:
    """Pure mapping, no I/O — kept separate from any query so it's unit-testable
    without a database."""
    requirements: dict = program.requirements or {}
    deadlines: dict = program.deadlines or {}
    grants_raw: list = program.grants or []

    min_ielts = requirements.get("min_ielts")
    language_level = f"IELTS {min_ielts}" if min_ielts is not None else None

    required_documents: list[str] | None = None
    if any(flag in requirements for flag in _DOCUMENT_FLAGS):
        _doc_labels = tr("university_requirements")["document_labels"]
        required_documents = [
            _doc_labels[flag] for flag in _DOCUMENT_FLAGS if requirements.get(flag)
        ]
    # Raw document names from an external source (jinaq) — a real list of
    # actual document names, not the fixed 3-boolean-flag labels above.
    # Appended rather than replacing, so both sources' documents show up if
    # a program somehow has both.
    source_documents = requirements.get("source_required_documents")
    if source_documents:
        required_documents = (required_documents or []) + list(source_documents)

    # min_ent_threshold (new bulk-seed key) and min_ent (older hand-picked key)
    # are the same real-world fact under two different historical names —
    # never both present on the same program, but read either. Both represent
    # the grant-competition eligibility bar from the MES RK reference data,
    # not a generic "minimum to enroll at all" — see the field's own label.
    min_ent_threshold = requirements.get("min_ent_threshold")
    if min_ent_threshold is None:
        min_ent_threshold = requirements.get("min_ent")

    exams = list(requirements.get("exams") or [])
    notes = list(requirements.get("notes") or [])
    exam_hint_from_notes = _note_hint_for_program(notes, program.name) if not exams else None

    return UniversityRequirement(
        program_name=program.name,
        university_name=university.name,
        city=university.city,
        country=university.country,
        website=university.website,
        program_language=program.language,
        exams=exams,
        exam_hint_from_notes=exam_hint_from_notes,
        application_deadline=deadlines.get("application_close"),
        grants=[
            ProgramGrant(
                name=g.get("name", ""),
                amount=g.get("amount"),
                conditions=g.get("conditions"),
            )
            for g in grants_raw
        ],
        language_level=language_level,
        portfolio_needed=requirements.get("needs_portfolio"),
        required_documents=required_documents,
        min_ent_threshold=min_ent_threshold,
        min_ent_paid=requirements.get("min_ent_paid"),
        min_gpa=requirements.get("min_gpa"),
        min_sat=requirements.get("min_sat"),
        extracurriculars=list(requirements.get("extracurriculars") or []),
        admission_scores_2026=admission_scores_2026_brief(requirements),
        grant_scores=requirements.get("grant_scores", {}),
        grants_allocated_count=requirements.get("grants_allocated_count"),
        duration_years=requirements.get("duration_years"),
        has_dual_degree=requirements.get("has_dual_degree"),
        has_dormitory=university.facilities.get("has_dormitory") if university.facilities else None,
        dormitory_cost_label=university.facilities.get("dormitory_cost_label") if university.facilities else None,
        has_military_department=university.facilities.get("has_military_department") if university.facilities else None,
        admissions_contacts=university.contacts or {},
        notes=notes,
        requires_ent=university.facilities.get("requires_ent") if university.facilities else None,
    )
