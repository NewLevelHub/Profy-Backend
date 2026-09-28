"""PRO-430: the admin assessment export is Russian-only whatever the admin's
UI locale — labels and every exported value alike."""

import csv
import io
import zipfile

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.catalog import tr
from app.models.question import Question, QuestionInstrument
from app.models.user import User
from app.models.user_response import UserResponse
from tests.integration.astur_helpers import make_student


async def test_assessment_export_is_russian_for_a_kazakh_admin(
    client: httpx.AsyncClient,
    admin_user: User,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, assessment, _ = await make_student(db_session)
    question = (
        await db_session.execute(
            select(Question).where(Question.instrument == QuestionInstrument.riasec).order_by(Question.order).limit(1)
        )
    ).scalar_one()
    db_session.add(UserResponse(assessment_id=assessment.id, question_id=question.id, answer_value=5))
    admin_user.locale = "kk"
    await db_session.flush()

    response = await client.get(f"/api/v1/admin/assessments/{assessment.id}/export", headers=admin_headers)
    assert response.status_code == 200

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    rows = list(csv.reader(io.StringIO(archive.read("responses.csv").decode("utf-8").lstrip("\ufeff"))))
    header, row = rows[0], rows[1]
    assert row[header.index("Вопрос")] == question.text["ru"]
    # The answer label used to follow the admin's locale (Kazakh words next
    # to a Russian question in the same row).
    assert row[header.index("Ответ словами")] == tr("riasec", locale="ru")["likert"][4]
