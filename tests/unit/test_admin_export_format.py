"""PRO-262 §11: the CSV exports are opened in Excel, by people who are not
developers.

Checked byte-for-byte on live downloads at the time: no BOM anywhere, Python's
`True`/`False` in boolean columns, ISO timestamps with microseconds and an
offset that Excel does not read as dates, and raw enum keys where the screen
shows Russian (docs/admin-backend-requests-pro-242.md §11).
"""

import csv
import io
import uuid
import zipfile
from datetime import datetime, timezone

from app.schemas.admin import (
    AdminAssessmentDetailResponse,
    AdminResponseItem,
    AdminUserListItem,
)
from app.services import admin_export_service as export


def _user_item(**overrides) -> AdminUserListItem:
    defaults = dict(
        id=uuid.uuid4(),
        email="student@example.test",
        is_verified=True,
        is_active=True,
        is_admin=False,
        created_at=datetime(2026, 9, 3, 9, 29, 27, 80528, tzinfo=timezone.utc),
        last_active_at=datetime(2026, 9, 4, 11, 5, tzinfo=timezone.utc),
        has_profile=True,
        profile_name="Бекзат",
        age_group="senior",
        city="Алматы",
        grade=10,
        assessments_count=1,
        latest_assessment_status="completed",
        latest_assessment_goal="university",
    )
    defaults.update(overrides)
    return AdminUserListItem(**defaults)


def _rows(csv_text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(csv_text)))


def _cell(csv_text: str, column: str) -> str:
    header, row = _rows(csv_text)[:2]
    return row[header.index(column)]


# --- users_export.csv -------------------------------------------------------


def test_booleans_are_words_excel_understands() -> None:
    csv_text = export.users_to_csv([_user_item(is_verified=True, is_admin=False)])

    assert _cell(csv_text, "Почта подтверждена") == "да"
    assert _cell(csv_text, "Администратор") == "нет"
    assert "True" not in csv_text and "False" not in csv_text


def test_timestamps_are_readable_as_dates() -> None:
    """`2026-09-03T09:29:27.080528+00:00` is text to Excel — sorting and date
    filters on the column silently do nothing."""
    csv_text = export.users_to_csv([_user_item()])

    assert _cell(csv_text, "Регистрация (UTC)") == "2026-09-03 09:29"
    assert _cell(csv_text, "Последняя активность (UTC)") == "2026-09-04 11:05"


def test_enum_keys_are_localized_the_way_the_screen_shows_them() -> None:
    csv_text = export.users_to_csv([_user_item()])

    assert _cell(csv_text, "Класс (группа)") == "10–11 класс"
    assert _cell(csv_text, "Цель последнего") == "Поступить в вуз"
    assert _cell(csv_text, "Статус последнего") == "Завершён"


def test_an_unmapped_enum_value_falls_back_to_the_raw_key() -> None:
    """A blank cell would be worse than an untranslated one: it looks like
    missing data rather than a label the map has not caught up with."""
    csv_text = export.users_to_csv([_user_item(latest_assessment_goal="brand_new_goal")])

    assert _cell(csv_text, "Цель последнего") == "brand_new_goal"


def test_city_and_grade_are_exported() -> None:
    csv_text = export.users_to_csv([_user_item()])

    assert _cell(csv_text, "Город") == "Алматы"
    assert _cell(csv_text, "Класс") == "10"


def test_a_junior_row_says_which_instrument_it_was_measured_on() -> None:
    """Junior takes MI and never RIASEC, so its six RIASEC columns are empty
    by design — without naming the instrument, that row is indistinguishable
    from a broken one."""
    csv_text = export.users_to_csv(
        [_user_item(age_group="junior", riasec=None, mi={"logical": 82.0})]
    )

    assert _cell(csv_text, "Инструмент интересов") == "Множественный интеллект"
    assert _cell(csv_text, "MI: Логика и счёт") == "82.0"
    assert _cell(csv_text, "RIASEC: Артистичный") == ""


def test_users_csv_has_no_bom() -> None:
    """The frontend's downloadCsv() prepends one before saving; a second would
    show as a stray character in the first header cell, and a BOM also trips
    csv.reader and pandas."""
    assert not export.users_to_csv([_user_item()]).startswith("﻿")


# --- the assessment ZIP -----------------------------------------------------


def _detail(**overrides) -> AdminAssessmentDetailResponse:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        user_email="student@example.test",
        profile_name="Бекзат",
        goal="university",
        status="completed",
        answered_count=314,
        total_questions=314,
        created_at=datetime(2026, 9, 3, 9, 29, tzinfo=timezone.utc),
        responses=[
            AdminResponseItem(
                question_id=uuid.uuid4(),
                instrument="riasec",
                category="A",
                question_text="Мне нравится рисовать",
                question_order=1,
                answer_value=5,
                selected_answer_text="Очень нравится",
                created_at=datetime(2026, 9, 3, 9, 40, tzinfo=timezone.utc),
            ),
            AdminResponseItem(
                question_id=uuid.uuid4(),
                instrument="big_five",
                category="A",
                question_text="Я легко доверяю людям",
                question_order=2,
                answer_value=4,
                selected_answer_text="Скорее согласен",
                created_at=datetime(2026, 9, 3, 9, 40, tzinfo=timezone.utc),
            ),
        ],
    )
    defaults.update(overrides)
    return AdminAssessmentDetailResponse(**defaults)


def _zip_member(detail, name: str) -> str:
    archive = zipfile.ZipFile(io.BytesIO(export.assessment_detail_to_zip(detail)))
    return archive.read(name).decode("utf-8")


def test_every_file_in_the_zip_starts_with_a_bom() -> None:
    """These three could not be fixed on the client the way users_export.csv
    is — patching them would mean unpacking and rebuilding the archive in the
    browser — so they were still opening as mojibake in Excel."""
    detail = _detail()

    for name in ("summary.csv", "responses.csv"):
        assert _zip_member(detail, name).startswith("﻿")


def test_the_same_letter_on_two_different_scales_is_told_apart() -> None:
    """A, E and C exist in both RIASEC and Big Five: a pivot built on the code
    column alone merges "Артистичный" with "Доброжелательностью"."""
    body = _zip_member(_detail(), "responses.csv").lstrip("﻿")
    header, riasec_row, bigfive_row = _rows(body)[:3]

    scale = header.index("Шкала")
    code = header.index("Код шкалы")

    assert riasec_row[code] == bigfive_row[code] == "A"
    assert riasec_row[scale] == "Артистичный"
    assert bigfive_row[scale] == "Доброжелательность"


def test_summary_localizes_values_and_avoids_python_literals() -> None:
    body = _zip_member(_detail(), "summary.csv").lstrip("﻿")
    values = {row[0]: row[1] for row in _rows(body) if len(row) == 2}

    assert values["Цель"] == "Поступить в вуз"
    assert values["Статус"] == "Завершён"
    assert values["Начато (UTC)"] == "2026-09-03 09:29"
    assert values["Есть роадмап"] == "нет"


# --- the downloaded filename ------------------------------------------------


def test_export_filename_names_the_student_not_a_uuid() -> None:
    name = export.assessment_export_filename(_detail())

    assert name == "profy_Бекзат_2026-09-03.zip"


def test_export_filename_falls_back_to_the_email_local_part() -> None:
    name = export.assessment_export_filename(_detail(profile_name=None))

    assert name == "profy_student_2026-09-03.zip"


def test_export_filename_strips_characters_that_break_a_path() -> None:
    name = export.assessment_export_filename(_detail(profile_name='Бек/зат: "тест"'))

    assert "/" not in name and '"' not in name and ":" not in name
    assert name.endswith("_2026-09-03.zip")
