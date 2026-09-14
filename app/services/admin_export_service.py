"""CSV serialization for the admin users/assessments panel. Pure functions,
no DB access — keeps admin_service.py focused on data assembly, this module
on presentation. See docs/frontend-admin-users-api-contract.md for the
column layout this produces."""

import csv
import io
import re
import zipfile
from datetime import datetime

from app.schemas.admin import AdminAssessmentDetailResponse, AdminUserListItem
from app.services.bigfive_content import BIGFIVE_LABELS
from app.services.mi_content import MI_LABELS
from app.services.riasec_content import RIASEC_LABELS

# Excel does not sniff UTF-8 in a .csv: without a BOM it reads the file in the
# system codepage and every Cyrillic name turns into mojibake ("Бекзат" ->
# "Ð‘ÐµÐºÐ·Ð°Ñ‚"). These files are full of Cyrillic — profile names, cities,
# and, since this change, localized goals and statuses.
_BOM = "\ufeff"

# Excel does not recognise an ISO timestamp with microseconds and an offset as
# a date either, so sorting and date filters silently do nothing on the
# column. Minutes are as precise as an admin export needs.
#
# Dropping the offset is what makes the value parse as a date, so the zone
# has to be stated in the column heading instead: everything is stored and
# written in UTC, and an admin in Almaty (UTC+5) would otherwise read every
# timestamp five hours early with nothing on screen saying so.
_DATETIME_FORMAT = "%Y-%m-%d %H:%M"
_UTC_SUFFIX = " (UTC)"

# Python's True/False are not booleans to Excel, just words.
_YES, _NO = "да", "нет"

# Localized exactly as the admin UI shows them
# (Profy-Frontend/src/shared/lib/assessmentLabels.ts and
# shared/config/constants.ts): an export that says `age_group=senior` while
# the screen says "10–11 класс" makes the reader translate by hand.
_AGE_GROUP_LABELS = {
    "junior": "5–7 класс",
    "middle": "8–9 класс",
    "senior": "10–11 класс",
}
_GOAL_LABELS = {
    "explore": "Исследовать",
    "profession": "Выбрать профессию",
    "university": "Поступить в вуз",
    "unsure": "Не уверен",
}
_STATUS_LABELS = {
    "in_progress": "В процессе",
    "completed": "Завершён",
}
_ROLE_LABELS = {
    "student": "Ученик",
    "admin": "Администратор",
    "psychologist": "Психолог",
}
_INSTRUMENT_LABELS = {
    "riasec": "RIASEC",
    "big_five": "Big Five",
    "mi": "Множественный интеллект",
}


def _yes_no(value: bool) -> str:
    return _YES if value else _NO


def _at(value: datetime | None) -> str:
    return value.strftime(_DATETIME_FORMAT) if value else ""


def _label(labels: dict[str, str], value: str | None) -> str:
    """Falls back to the raw key rather than blanking it: a value the map has
    not caught up with is still information, an empty cell is not."""
    if not value:
        return ""
    return labels.get(value, value)


# Fixed order matches HollandType (app/models/question.py) — AdminUserListItem.riasec
# is only ever populated for middle/senior (admin_service._build_user_list_items
# deliberately leaves it None for junior, whose instrument is MI, not RIASEC),
# so a fixed RIASEC column set is safe here.
_RIASEC_KEYS = ("R", "I", "A", "S", "E", "C")
_BIG_FIVE_KEYS = ("N", "E", "O", "A", "C")
_MI_KEYS = tuple(MI_LABELS)

# Every header is the human name of what the column holds. The file is opened
# in Excel by people who are not the developers who named the fields.
_USER_COLUMNS = (
    "ID",
    "Email",
    "Почта подтверждена",
    "Аккаунт активен",
    "Роль",
    "Администратор",
    "Регистрация" + _UTC_SUFFIX,
    "Последняя активность" + _UTC_SUFFIX,
    "Есть профиль",
    "Имя",
    "Класс (группа)",
    "Класс",
    "Город",
    "Тестирований",
    "Статус последнего",
    "Цель последнего",
    "Инструмент интересов",
    *(f"RIASEC: {RIASEC_LABELS[k]}" for k in _RIASEC_KEYS),
    *(f"MI: {MI_LABELS[k]}" for k in _MI_KEYS),
    *(f"Big Five: {BIGFIVE_LABELS[k]}" for k in _BIG_FIVE_KEYS),
)


def users_to_csv(items: list[AdminUserListItem]) -> str:
    """No BOM here on purpose, unlike the files inside the assessment ZIP: the
    frontend's downloadCsv() already prepends one before saving, and a second
    would show up as a stray character in the first header cell. A BOM also
    trips csv.reader/pandas, so the endpoint itself stays clean."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_USER_COLUMNS)

    for item in items:
        riasec = item.riasec or {}
        mi = item.mi or {}
        big_five = item.big_five or {}
        # Which interest instrument this user was actually measured on. Junior
        # takes MI and never RIASEC, so without this column a completed junior
        # row reads as "finished, but no scores" — identical to a broken one.
        instrument = _INSTRUMENT_LABELS["mi"] if item.age_group == "junior" else (
            _INSTRUMENT_LABELS["riasec"] if item.age_group else ""
        )
        writer.writerow(
            [
                str(item.id),
                item.email,
                _yes_no(item.is_verified),
                _yes_no(item.is_active),
                _label(_ROLE_LABELS, item.role.value),
                _yes_no(item.is_admin),
                _at(item.created_at),
                _at(item.last_active_at),
                _yes_no(item.has_profile),
                item.profile_name or "",
                _label(_AGE_GROUP_LABELS, item.age_group),
                item.grade if item.grade is not None else "",
                item.city or "",
                item.assessments_count,
                _label(_STATUS_LABELS, item.latest_assessment_status),
                _label(_GOAL_LABELS, item.latest_assessment_goal),
                instrument,
                *(riasec.get(k, "") for k in _RIASEC_KEYS),
                *(mi.get(k, "") for k in _MI_KEYS),
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

    writer.writerow(["Показатель", "Значение"])
    writer.writerow(["Email", detail.user_email])
    writer.writerow(["Имя", detail.profile_name or ""])
    writer.writerow(["Цель", _label(_GOAL_LABELS, detail.goal)])
    writer.writerow(["Статус", _label(_STATUS_LABELS, detail.status)])
    writer.writerow(["Начато" + _UTC_SUFFIX, _at(detail.created_at)])
    writer.writerow(["Завершено" + _UTC_SUFFIX, _at(detail.completed_at)])
    writer.writerow(["Отвечено вопросов", detail.answered_count])
    writer.writerow(["Всего вопросов", detail.total_questions])
    writer.writerow(["Есть роадмап", _yes_no(detail.roadmap is not None)])
    if detail.analysis_result is not None:
        for metric, value in _analysis_result_rows(detail.analysis_result.model_dump()):
            writer.writerow([metric, value])

    return buffer.getvalue()


def _scale_name(instrument: str, category: str) -> str:
    """A/E/C exist in both RIASEC and Big Five, so `category` alone silently
    merges "Артистичный" with "Доброжелательность" in any pivot built on that
    column. The neighbouring instrument column separates them, but only if the
    reader knows to look — this states the scale outright."""
    if instrument == "riasec":
        return RIASEC_LABELS.get(category, category)
    if instrument == "big_five":
        return BIGFIVE_LABELS.get(category, category)
    if instrument == "mi":
        return MI_LABELS.get(category, category)
    return category


def _responses_csv(detail: AdminAssessmentDetailResponse) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "№ вопроса",
            "Инструмент",
            "Код шкалы",
            "Шкала",
            "Вопрос",
            "Ответ (1-5)",
            "Ответ словами",
            "Время ответа" + _UTC_SUFFIX,
        ]
    )
    for response in detail.responses:
        writer.writerow(
            [
                response.question_order,
                _label(_INSTRUMENT_LABELS, response.instrument),
                response.category,
                _scale_name(response.instrument, response.category),
                response.question_text,
                response.answer_value,
                response.selected_answer_text,
                _at(response.created_at),
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
            "№ триплета",
            "Выбрано как важное",
            "Категория важного",
            "Выбрано как неважное",
            "Категория неважного",
            "Не выбрано",
            "Категория невыбранного",
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
        # The BOM has to be written here: a file inside a ZIP cannot be fixed
        # up by the browser the way the frontend patches users_export.csv, so
        # these three were the ones still opening as mojibake in Excel.
        zf.writestr("summary.csv", _BOM + _summary_csv(detail))
        zf.writestr("responses.csv", _BOM + _responses_csv(detail))
        if detail.motivation_responses:
            zf.writestr("motivation.csv", _BOM + _motivation_csv(detail))
    return buffer.getvalue()


_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w.-]+", re.UNICODE)


def assessment_export_filename(detail: AdminAssessmentDetailResponse) -> str:
    """`assessment_<uuid>.zip` told the person who downloaded it nothing. The
    frontend already renames the file it saves; this fixes the name a direct
    link gets, which the frontend cannot touch.

    Non-word characters are collapsed so the name survives
    Content-Disposition and any filesystem; Cyrillic is kept, since the
    pattern is Unicode-aware and the names are Russian."""
    who = detail.profile_name or detail.user_email.split("@")[0]
    stem = _UNSAFE_FILENAME_CHARS.sub("_", who).strip("_") or "assessment"
    return f"profy_{stem}_{detail.created_at:%Y-%m-%d}.zip"
