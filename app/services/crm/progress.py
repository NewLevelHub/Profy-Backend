"""After-sale stages that follow the student's account (ТЗ §3.3, §5.2).

Once a deal is linked to a Profile account (app/services/crm/invites.py), the
platform moves it on its own: a finished test is 7 «Диагностика пройдена», a
published report is 8 «Отчёт опубликован» and «Успешно реализовано»
(ТЗ §3.3.1). The platform calls `student_progressed` at the moment either
happens; linking calls `sync_deal` to catch up with what already happened.

The second call, which the specialist sets (app/services/scheduling/
second_meeting.py), comes after: once the report is published, a set
second call is 9 «Разбор назначен» and a held one 10 «Разбор проведён».
«Успешно» stays with the publication.

`report_needs_review` is the other direction: the deal's tariff decides
whether the student's new report waits for a psychologist.

Both only move forward, so a repeated call changes nothing. A stage that a
supervisor already moved past is left alone. A deal that is not paid does
not move: the manager gets one «Проверить оплату» task instead (ТЗ §3.3 п.5).
Only tests finished after the deal was created count — an older account
brings its old results with it.
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.catalog import key as i18n_key
from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.assessment import Assessment, AssessmentStatus
from app.models.crm import STAGE_ORDER, CrmDeal, CrmDealEvent, CrmTask, DealResult, DealStage, TaskType
from app.models.profile import Profile
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.scheduling import Meeting, MeetingStatus
from app.models.user import User, UserRole
from app.services import audit, tz

logger = logging.getLogger(__name__)


def _event(db: AsyncSession, deal: CrmDeal, kind: str, data: dict) -> None:
    # No actor: the system made the change.
    db.add(CrmDealEvent(deal_id=deal.id, actor_id=None, kind=kind, data=data))


async def _progress(db: AsyncSession, user_id: uuid.UUID, since: datetime) -> tuple[bool, bool]:
    """(test finished, report published) for tests finished after `since`."""
    finished = (
        select(Assessment.id)
        .join(Profile, Profile.id == Assessment.profile_id)
        .where(
            Profile.user_id == user_id,
            Assessment.status == AssessmentStatus.completed,
            Assessment.completed_at >= since,
        )
    )
    completed = await db.scalar(select(func.count()).select_from(finished.subquery()))
    if not completed:
        return False, False
    published = await db.scalar(
        select(func.count())
        .select_from(AnalysisResult)
        .where(AnalysisResult.assessment_id.in_(finished), AnalysisResult.review_status == ReviewStatus.published)
    )
    return True, bool(published)


async def calls(db: AsyncSession, deal_id: uuid.UUID) -> tuple[Meeting | None, Meeting | None]:
    """(first, second): the deal's earliest live call — the one the manager
    booked — and the one after it, which the specialist set."""
    rows = (
        await db.execute(
            select(Meeting)
            .where(Meeting.deal_id == deal_id, Meeting.status != MeetingStatus.cancelled)
            .order_by(Meeting.start_at)
            .limit(2)
        )
    ).scalars().all()
    return (rows[0] if rows else None), (rows[1] if len(rows) > 1 else None)


async def _second_call(db: AsyncSession, deal_id: uuid.UUID) -> Meeting | None:
    return (await calls(db, deal_id))[1]


async def consultation_deal(db: AsyncSession, student_id: uuid.UUID) -> CrmDeal | None:
    """The student's latest not lost deal, if it was sold with the
    specialist's calls. A client who came back for a tariff without them is
    not held by the calls of an earlier deal."""
    deal = await db.scalar(
        select(CrmDeal)
        .where(CrmDeal.student_user_id == student_id, CrmDeal.result != DealResult.lost)
        .order_by(CrmDeal.created_at.desc())
        .limit(1)
    )
    return deal if deal is not None and deal.psychologist_review is True else None


async def test_opens_at(db: AsyncSession, student_id: uuid.UUID) -> tuple[bool, datetime | None]:
    """(open, when): with a specialist's calls the test opens as the first
    call begins — the specialist introduces it there. `when` is that call's
    start, None while it is not booked. Without such a deal it is open."""
    deal = await consultation_deal(db, student_id)
    if deal is None:
        return True, None
    first, _ = await calls(db, deal.id)
    if first is not None and first.start_at <= tz.now_utc():
        return True, None
    return False, first.start_at if first is not None else None


async def publish_blocker(db: AsyncSession, student_id: uuid.UUID) -> tuple[str, datetime | None] | None:
    """Why the specialist cannot publish the report yet: with a specialist's
    calls the report is published on the second call, from its start."""
    deal = await consultation_deal(db, student_id)
    if deal is None:
        return None
    _, second = await calls(db, deal.id)
    if second is None:
        return "publish_second_call_missing", None
    if second.start_at > tz.now_utc():
        return "publish_second_call_not_started", second.start_at
    return None


async def _payment_check(db: AsyncSession, deal: CrmDeal) -> None:
    """One open «Проверить оплату» task per deal, for its manager (or the owner)."""
    if await db.scalar(
        select(CrmTask.id).where(
            CrmTask.deal_id == deal.id, CrmTask.type == TaskType.payment_check, CrmTask.done_at.is_(None)
        )
    ):
        return
    assignee_id = deal.manager_id or await db.scalar(
        select(User.id).where(User.role == UserRole.owner, User.is_active.is_(True)).order_by(User.created_at).limit(1)
    )
    if assignee_id is None:
        return
    task = CrmTask(
        deal_id=deal.id,
        assignee_id=assignee_id,
        type=TaskType.payment_check,
        text=i18n_key("api_messages", "crm_task_payment_check", locale="ru"),
        due_at=tz.now_utc(),
    )
    db.add(task)
    await db.flush()
    _event(db, deal, "payment_check", {"task_id": str(task.id)})


async def sync_deal(db: AsyncSession, deal: CrmDeal) -> None:
    """Bring stages 7–8 and the result in line with the linked account. No commit."""
    if deal.student_user_id is None or deal.result == DealResult.lost:
        return
    finished, published = await _progress(db, deal.student_user_id, deal.created_at)
    if not finished:
        return
    if deal.paid_at is None:
        await _payment_check(db, deal)
        return
    target = DealStage.report_published if published else DealStage.diagnostics_done
    if published:
        second = await _second_call(db, deal.id)
        if second is not None:
            target = DealStage.review_done if second.status == MeetingStatus.done else DealStage.review_scheduled
    if STAGE_ORDER.index(deal.stage) < STAGE_ORDER.index(target):
        audit.record(
            db, actor=None, action="crm.stage_changed", entity_type="crm_deal", entity_id=deal.id,
            before={"stage": deal.stage.value}, after={"stage": target.value},
        )
        _event(db, deal, "stage", {"from": deal.stage.value, "to": target.value, "auto": True})
        deal.stage = target
    if published and deal.result == DealResult.open:
        deal.result = DealResult.won
        deal.closed_at = tz.now_utc()
        audit.record(
            db, actor=None, action="crm.deal_closed", entity_type="crm_deal", entity_id=deal.id,
            before={"result": "open"}, after={"result": "won", "reason": None},
        )
        _event(db, deal, "closed", {"result": "won", "reason": None, "auto": True})


async def report_needs_review(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Whether the student's new report waits for a psychologist.

    The student's latest not lost deal decides — the one this test was sold
    with; a client who came back for a tariff without a review gets the
    report at once even if an earlier deal had one. It goes to the student
    at once only when that deal is paid and its tariff was sold without a
    review. Any doubt (no deal, not paid, no tariff) keeps the review:
    publishing is the step that cannot be taken back."""
    deal = await db.scalar(
        select(CrmDeal)
        .where(CrmDeal.student_user_id == user_id, CrmDeal.result != DealResult.lost)
        .order_by(CrmDeal.created_at.desc())
        .limit(1)
    )
    return deal is None or deal.paid_at is None or deal.psychologist_review is not False


async def assign_specialist(db: AsyncSession, deal: CrmDeal) -> None:
    """The specialist the booking picked sees the linked student in Profile
    (their list, results and review queue). No commit."""
    if deal.student_user_id is None or deal.specialist_id is None:
        return
    exists = await db.scalar(
        select(PsychologistStudentAssignment.id).where(
            PsychologistStudentAssignment.psychologist_id == deal.specialist_id,
            PsychologistStudentAssignment.student_id == deal.student_user_id,
        )
    )
    if not exists:
        db.add(PsychologistStudentAssignment(psychologist_id=deal.specialist_id, student_id=deal.student_user_id))


async def student_progressed(db: AsyncSession, user_id: uuid.UUID) -> None:
    """The platform's hook: the student finished a test or got a report
    published. Runs in the caller's transaction, before its commit, so the
    deal moves together with the change that moved it.

    Best-effort: a failure here is logged and rolled back to a savepoint —
    the student's test or the specialist's publication must go through."""
    # Flush the caller's own change first: a rollback of the savepoint below
    # must not take it along.
    await db.flush()
    try:
        async with db.begin_nested():
            deals = (
                await db.execute(
                    select(CrmDeal)
                    .where(CrmDeal.student_user_id == user_id, CrmDeal.result != DealResult.lost)
                    .with_for_update()
                )
            ).scalars()
            for deal in deals:
                await sync_deal(db, deal)
    except Exception:
        logger.exception("crm: syncing deals of student %s failed", user_id)
