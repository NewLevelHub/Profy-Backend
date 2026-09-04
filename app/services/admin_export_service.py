"""CSV serialization for the admin users/assessments panel. Pure functions,
no DB access — keeps admin_service.py focused on data assembly, this module
on presentation. See docs/frontend-admin-users-api-contract.md for the
column layout this produces."""

import csv
import io
import zipfile

from app.schemas.admin import AdminAssessmentDetailResponse, AdminUserListItem

# Fixed order matches HollandType (app/models/question.py) — AdminUserListItem.riasec
# is only ever populated for middle/senior (admin_service._build_user_list_items
# deliberately leaves it None for junior, whose instrument is MI, not RIASEC),
# so a fixed RIASEC column set is safe here.
_RIASEC_KEYS = ("R", "I", "A", "S", "E", "C")
_BIG_FIVE_KEYS = ("N", "E", "O", "A", "C")

_USER_COLUMNS = (
    "id",
    "email",
    "is_verified",
    "is_active",
    "is_admin",
    "created_at",
    "has_profile",
    "profile_name",
    "age_group",
    "assessments_count",
    "latest_assessment_status",
    "latest_assessment_goal",
    *(f"riasec_{k}" for k in _RIASEC_KEYS),
    *(f"big_five_{k}" for k in _BIG_FIVE_KEYS),
)


def users_to_csv(items: list[AdminUserListItem]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_USER_COLUMNS)

    for item in items:
        riasec = item.riasec or {}
        big_five = item.big_five or {}
        writer.writerow(
            [
                str(item.id),
                item.email,
                item.is_verified,
                item.is_active,
                item.is_admin,
                item.created_at.isoformat(),
                item.has_profile,
                item.profile_name or "",
                item.age_group or "",
                item.assessments_count,
                item.latest_assessment_status or "",
                item.latest_assessment_goal or "",
                *(riasec.get(k, "") for k in _RIASEC_KEYS),
                *(big_five.get(k, "") for k in _BIG_FIVE_KEYS),
            ]
        )

    return buffer.getvalue()


def _analysis_result_rows(analysis: dict) -> list[tuple[str, str]]:
    """Flattens AdminAnalysisResultResponse into metric/value pairs. `profile`
    keys are dynamic on purpose — RIASEC letters for middle/senior, MI
    category keys for junior (see AdminAnalysisResultResponse's docstring),
    unlike the fixed RIASEC columns used in `users_to_csv` (which only ever
    sees the middle/senior shape)."""
    rows: list[tuple[str, str]] = [
        ("report_version", str(analysis["report_version"])),
        ("summary", analysis["summary"]),
        ("code", ", ".join(analysis["code"])),
    ]
    rows += [(f"profile_{k}", str(v)) for k, v in analysis["profile"].items()]
    rows += [(f"big_five_{k}", str(v)) for k, v in analysis["big_five"].items()]
    rows.append(("meta_differentiation", str(analysis["meta"]["differentiation"])))
    rows.append(("meta_consistency", analysis["meta"]["consistency"]))
    rows += [(f"meta_aversion_{k}", str(v)) for k, v in analysis["meta"]["aversion"].items()]
    rows.append(("strengths", ", ".join(analysis["strengths"])))
    rows.append(("weaknesses", ", ".join(analysis["weaknesses"])))
    rows.append(("development_plan_reinforce", ", ".join(analysis["development_plan"]["reinforce"])))
    rows.append(("development_plan_compensate", ", ".join(analysis["development_plan"]["compensate"])))
    rows += [(f"thinking_style_{k}", str(v)) for k, v in analysis["thinking_style"].items()]
    rows += [(f"personality_profile_{k}", str(v)) for k, v in analysis["personality_profile"].items()]
    rows += [(f"personality_note_{k}", v) for k, v in analysis["personality_notes"].items()]
    rows.append(("personality_highlights", ", ".join(analysis["personality_highlights"])))
    rows += [(f"motivation_{k}", str(v)) for k, v in analysis["motivation"].items()]
    rows.append(("motivation_top", ", ".join(analysis["motivation_top"])))
    rows.append(("motivation_highlights", ", ".join(analysis["motivation_highlights"])))
    rows.append(("careers_count", str(len(analysis["careers"]))))
    rows.append(
        (
            "careers_top",
            ", ".join(f"{c['name']} ({c['match_score']})" for c in analysis["careers"][:5]),
        )
    )
    return rows


def _summary_csv(detail: AdminAssessmentDetailResponse) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["Metric", "Value"])
    writer.writerow(["user_email", detail.user_email])
    writer.writerow(["profile_name", detail.profile_name or ""])
    writer.writerow(["goal", detail.goal])
    writer.writerow(["status", detail.status])
    writer.writerow(["created_at", detail.created_at.isoformat()])
    writer.writerow(["completed_at", detail.completed_at.isoformat() if detail.completed_at else ""])
    writer.writerow(["answered_count", detail.answered_count])
    writer.writerow(["total_questions", detail.total_questions])
    writer.writerow(["has_roadmap", detail.roadmap is not None])
    if detail.analysis_result is not None:
        for metric, value in _analysis_result_rows(detail.analysis_result.model_dump()):
            writer.writerow([metric, value])

    return buffer.getvalue()


def _responses_csv(detail: AdminAssessmentDetailResponse) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "question_order",
            "instrument",
            "category",
            "question_text",
            "answer_value",
            "selected_answer_text",
            "created_at",
        ]
    )
    for response in detail.responses:
        writer.writerow(
            [
                response.question_order,
                response.instrument,
                response.category,
                response.question_text,
                response.answer_value,
                response.selected_answer_text,
                response.created_at.isoformat(),
            ]
        )
    return buffer.getvalue()


def _motivation_csv(detail: AdminAssessmentDetailResponse) -> str:
    """Each row is one answered triplet: 3 statements were shown, the user
    picked one as MOST important and one as LEAST important.
    `picked_most_*`/`picked_least_*` are that real answer, not static
    triplet content; `not_picked_*` is the 3rd statement the user left
    untouched (inferred, never its own stored choice)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "triplet_index",
            "picked_most_text",
            "picked_most_category",
            "picked_least_text",
            "picked_least_category",
            "not_picked_text",
            "not_picked_category",
        ]
    )
    for row in detail.motivation_responses:
        writer.writerow(
            [
                row.triplet_index,
                row.picked_most_text,
                row.picked_most_category,
                row.picked_least_text,
                row.picked_least_category,
                row.not_picked_text,
                row.not_picked_category,
            ]
        )
    return buffer.getvalue()


def assessment_detail_to_zip(detail: AdminAssessmentDetailResponse) -> bytes:
    """3 SEPARATE single-table CSVs zipped together, instead of one CSV with
    3 stacked blocks of different widths — a "ragged" CSV like that parses
    fine in Excel/Numbers (scroll past the narrower Metric/Value block to see
    the wide responses table) but breaks naive single-table CSV viewers
    (e.g. web csv-preview tools), which read the first row's column count as
    the header and truncate/misalign everything after it. Each file here is
    a normal, uniform-width table on its own."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("summary.csv", _summary_csv(detail))
        zf.writestr("responses.csv", _responses_csv(detail))
        if detail.motivation_responses:
            zf.writestr("motivation.csv", _motivation_csv(detail))
    return buffer.getvalue()
