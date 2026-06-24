from dataclasses import dataclass

from app.models.artifact import Artifact, ArtifactType
from app.models.profile import Profile
from app.models.program import Program
from app.schemas.gap import GapAnalysisResponse, GapItem, GapStatus

_GPA_KEYS = {"gpa", "grade_point", "средний балл", "gpa_min"}
_LANGUAGE_KEYS = {"ielts", "toefl", "duolingo", "english", "language", "cefr", "язык", "английский"}
_EXAM_KEYS = {"sat", "act", "ent", "ege", "exam", "test", "экзамен", "олимпиада"}
_PORTFOLIO_KEYS = {"portfolio", "project", "портфолио", "проект", "cv", "resume"}

_LANGUAGE_ARTIFACT_TERMS = {
    "english", "ielts", "toefl", "duolingo", "french", "german", "spanish",
    "chinese", "японский", "английский", "немецкий", "французский", "язык",
    "language", "cefr",
}

_PORTFOLIO_TYPES = {ArtifactType.achievement, ArtifactType.profession}


def _classify_key(key: str) -> str:
    k = key.lower()
    if any(g in k for g in _GPA_KEYS):
        return "gpa"
    if any(lang in k for lang in _LANGUAGE_KEYS):
        return "language"
    if any(e in k for e in _EXAM_KEYS):
        return "exam"
    if any(p in k for p in _PORTFOLIO_KEYS):
        return "portfolio"
    return "generic"


def _has_language_artifacts(artifacts: list[Artifact]) -> bool:
    return any(
        any(term in artifact.value.lower() for term in _LANGUAGE_ARTIFACT_TERMS)
        for artifact in artifacts
    )


def _has_portfolio_artifacts(artifacts: list[Artifact]) -> bool:
    return any(a.type in _PORTFOLIO_TYPES for a in artifacts)


@dataclass
class GapAnalysisResult:
    met: list[GapItem]
    not_met: list[GapItem]
    in_progress: list[GapItem]
    unknown: list[GapItem]
    readiness_score: float


def analyze_gap(
    profile: Profile,
    artifacts: list[Artifact],
    assessment_scores: dict[str, float],
    program: Program,
) -> GapAnalysisResult:
    requirements: dict = program.requirements or {}
    has_language = _has_language_artifacts(artifacts)
    has_portfolio = _has_portfolio_artifacts(artifacts)

    items: list[GapItem] = []

    for req_key, req_value in requirements.items():
        category = _classify_key(req_key)

        if category == "gpa":
            items.append(GapItem(
                requirement=req_key,
                status=GapStatus.unknown,
                comment="Нет данных о среднем балле",
            ))

        elif category == "language":
            if has_language:
                items.append(GapItem(
                    requirement=req_key,
                    status=GapStatus.in_progress,
                    comment="Обнаружены языковые курсы или активности в профиле",
                ))
            else:
                items.append(GapItem(
                    requirement=req_key,
                    status=GapStatus.unknown,
                    comment="Нет данных об уровне языка",
                ))

        elif category == "exam":
            if profile.grade < 10:
                items.append(GapItem(
                    requirement=req_key,
                    status=GapStatus.in_progress,
                    comment=f"{profile.grade} класс — есть время подготовиться к экзаменам",
                ))
            else:
                items.append(GapItem(
                    requirement=req_key,
                    status=GapStatus.unknown,
                    comment="Нет данных о результатах экзаменов",
                ))

        elif category == "portfolio":
            if has_portfolio:
                items.append(GapItem(
                    requirement=req_key,
                    status=GapStatus.in_progress,
                    comment="Есть достижения или профессиональный опыт — основа для портфолио",
                ))
            else:
                items.append(GapItem(
                    requirement=req_key,
                    status=GapStatus.not_met,
                    comment="Нет портфолио, достижений или профессионального опыта",
                ))

        else:
            items.append(GapItem(
                requirement=req_key,
                status=GapStatus.unknown,
                comment="Недостаточно данных для оценки",
            ))

    met = [i for i in items if i.status == GapStatus.met]
    not_met = [i for i in items if i.status == GapStatus.not_met]
    in_progress = [i for i in items if i.status == GapStatus.in_progress]
    unknown = [i for i in items if i.status == GapStatus.unknown]

    total = len(items)
    if total == 0:
        readiness_score = 0.0
    else:
        score = len(met) * 1.0 + len(in_progress) * 0.5
        readiness_score = round((score / total) * 100, 1)

    return GapAnalysisResult(
        met=met,
        not_met=not_met,
        in_progress=in_progress,
        unknown=unknown,
        readiness_score=readiness_score,
    )


def to_response(program_id, result: GapAnalysisResult) -> GapAnalysisResponse:
    return GapAnalysisResponse(
        program_id=program_id,
        met=result.met,
        not_met=result.not_met,
        in_progress=result.in_progress,
        unknown=result.unknown,
        readiness_score=result.readiness_score,
    )
