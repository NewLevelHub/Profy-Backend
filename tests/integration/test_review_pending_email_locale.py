"""PRO-430: the review-pending email goes out in the *psychologist's* language
(`users.locale`). It is sent from the student's request, so neither the email
nor its unnamed-student placeholder may follow that request's locale."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import use_locale
from app.i18n.catalog import tr
from app.models.user import User
from app.services import psychologist_service
from tests.integration.review_helpers import assign, capture_emails, make_other_student


@pytest.mark.parametrize(("psychologist_locale", "student_request_locale"), [("kk", "ru"), ("ru", "kk")])
async def test_email_follows_the_psychologist_not_the_request(
    db_session: AsyncSession,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
    psychologist_locale: str,
    student_request_locale: str,
) -> None:
    psychologist_user.locale = psychologist_locale
    student = await make_other_student(db_session)
    await assign(db_session, psychologist_user, student)
    emails = capture_emails(monkeypatch)

    with use_locale(student_request_locale):
        await psychologist_service.notify_review_pending(
            db_session, student_id=student.id, student_name=None, assessment_id=uuid.uuid4()
        )

    emails["pending"].assert_awaited_once()
    call = emails["pending"].await_args
    _, student_name = call.args
    assert call.kwargs["locale"] == psychologist_locale
    assert student_name == tr("report_copy", locale=psychologist_locale)["unnamed_student"]
