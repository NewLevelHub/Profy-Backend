"""
Seed script: question bank for the subject readiness quiz (see
app/services/subject_readiness_service.py). Entirely separate feature from
the Akinator engine/taxonomy seeded by seed_akinator_content.py — this script
only touches the `subject_questions` table plus `Direction.subjects_required`
(see seed_akinator_content.py's SPECIALTIES for that latter part).

Catalog: 14 school subjects x 2 questions each (level, interest) = 28 rows.
A subject is shared across every specialty that lists it in
Direction.subjects_required, so it is never duplicated per specialty.

Idempotent: SubjectQuestion rows are upserted by (subject, kind).

Run inside Docker:
    docker-compose exec api python scripts/seed_subject_questions.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.subject_question import SubjectQuestion, SubjectQuestionKind

# ---------------------------------------------------------------------------
# Shared 4-tier option scale, reused per subject with subject-specific question
# text (not an abstract 1-5 slider — concrete, descriptive options per the
# already-accepted SJT style).
# ---------------------------------------------------------------------------


def _level_options(verb_phrase: str) -> list[dict]:
    """`verb_phrase` describes the kind of task the subject involves, e.g.
    'решать задачи по алгебре и геометрии'."""
    return [
        {"text": f"Мне трудно {verb_phrase}, даже когда объясняют — приходится спрашивать снова и снова", "score": 0},
        {"text": f"Могу {verb_phrase}, если кто-то объясняет пошагово; сам справляюсь с трудом", "score": 1},
        {"text": f"Обычно справляюсь сам, изредка нужна подсказка", "score": 2},
        {"text": f"Легко справляюсь и могу объяснить это одноклассникам", "score": 3},
    ]


def _interest_options(activity_phrase: str) -> list[dict]:
    """`activity_phrase` describes engaging with the subject outside class,
    e.g. 'почитать что-то по математике или порешать задачи для интереса'."""
    return [
        {"text": "Стараюсь избегать — на уроках отвлекаюсь, дома к этому не возвращаюсь", "score": 0},
        {"text": "Отношусь нормально, но сам бы этим заниматься не стал", "score": 1},
        {"text": f"Мне интересно — иногда сам решаю {activity_phrase} сверх домашнего задания", "score": 2},
        {"text": f"Увлекаюсь — регулярно {activity_phrase} без напоминаний со стороны", "score": 3},
    ]


# ---------------------------------------------------------------------------
# Catalog — subject -> (level question, interest question)
# ---------------------------------------------------------------------------

_CATALOG: dict[str, dict] = {
    "Математика": {
        "level_text": "Когда на уроке математики дают новую тему (уравнения, функции, геометрия), как это обычно происходит у тебя?",
        "level_verb": "решать задачи по алгебре и геометрии",
        "interest_text": "Как ты относишься к решению математических задач вне урока?",
        "interest_activity": "нахожу и решаю задачи по математике",
    },
    "Информатика": {
        "level_text": "Когда нужно написать программу или разобраться в новом инструменте на компьютере, как у тебя это выходит?",
        "level_verb": "писать код или настраивать программы",
        "interest_text": "Как ты относишься к программированию и работе за компьютером сверх уроков информатики?",
        "interest_activity": "пишу код или разбираюсь в новых программах",
    },
    "Физика": {
        "level_text": "Когда на уроке физики нужно решить задачу на движение, силы или электричество, как это у тебя проходит?",
        "level_verb": "решать задачи по физике",
        "interest_text": "Как ты относишься к физическим явлениям и экспериментам вне урока?",
        "interest_activity": "смотрю ролики или читаю про физические явления",
    },
    "Химия": {
        "level_text": "Когда на уроке химии нужно решить задачу по реакциям или составить уравнение, как это у тебя проходит?",
        "level_verb": "решать задачи по химии",
        "interest_text": "Как ты относишься к химическим опытам и реакциям вне урока?",
        "interest_activity": "читаю или смотрю про химические опыты",
    },
    "Биология": {
        "level_text": "Когда на уроке биологии нужно разобраться в строении организма или процессах в клетке, как это у тебя проходит?",
        "level_verb": "разбираться в темах по биологии",
        "interest_text": "Как ты относишься к темам про живые организмы и природу вне урока?",
        "interest_activity": "читаю или смотрю про живые организмы и природу",
    },
    "История": {
        "level_text": "Когда нужно разобраться в причинах и последствиях исторических событий, как это у тебя проходит?",
        "level_verb": "разбираться в причинах и датах исторических событий",
        "interest_text": "Как ты относишься к историческим темам вне урока?",
        "interest_activity": "читаю или смотрю про исторические события",
    },
    "Обществознание": {
        "level_text": "Когда нужно разобраться, как устроены законы, государство или экономика в теме урока, как это у тебя проходит?",
        "level_verb": "разбираться в темах про общество и государство",
        "interest_text": "Как ты относишься к новостям и темам про общество, право, экономику?",
        "interest_activity": "слежу за новостями или обсуждаю такие темы",
    },
    "Литература": {
        "level_text": "Когда нужно разобрать художественное произведение и объяснить его смысл, как это у тебя проходит?",
        "level_verb": "разбирать смысл и приёмы в художественных текстах",
        "interest_text": "Как ты относишься к чтению художественной литературы вне школьной программы?",
        "interest_activity": "читаю книги, которых нет в школьной программе",
    },
    "Русский язык": {
        "level_text": "Когда нужно написать грамотный связный текст (сочинение, изложение), как это у тебя проходит?",
        "level_verb": "писать грамотные связные тексты",
        "interest_text": "Как ты относишься к тому, чтобы писать тексты (посты, истории, эссе) вне уроков?",
        "interest_activity": "пишу тексты для себя или для других",
    },
    "Английский язык": {
        "level_text": "Когда нужно понять или составить текст на английском языке, как это у тебя проходит?",
        "level_verb": "понимать и составлять тексты на английском",
        "interest_text": "Как ты относишься к английскому языку вне уроков (фильмы, игры, переписка)?",
        "interest_activity": "смотрю, читаю или переписываюсь на английском",
    },
    "География": {
        "level_text": "Когда нужно разобраться с картой, климатом или устройством территорий, как это у тебя проходит?",
        "level_verb": "разбираться в картах и устройстве территорий",
        "interest_text": "Как ты относишься к темам про страны, карты и путешествия вне урока?",
        "interest_activity": "читаю или смотрю про страны и путешествия",
    },
    "Экономика": {
        "level_text": "Когда нужно разобраться, как считаются расходы, доходы или работает рынок, как это у тебя проходит?",
        "level_verb": "разбираться в расчётах доходов, расходов и рынка",
        "interest_text": "Как ты относишься к темам про деньги, бизнес и рынок вне урока?",
        "interest_activity": "читаю или обсуждаю темы про деньги и бизнес",
    },
    "Физическая культура": {
        "level_text": "Когда на уроке физкультуры нужно освоить новое упражнение или норматив, как это у тебя проходит?",
        "level_verb": "осваивать новые упражнения и нормативы",
        "interest_text": "Как ты относишься к спорту и тренировкам вне уроков физкультуры?",
        "interest_activity": "тренируюсь или занимаюсь спортом",
    },
    "Искусство": {
        "level_text": "Когда нужно нарисовать, оформить или создать что-то визуальное на уроке, как это у тебя проходит?",
        "level_verb": "рисовать или оформлять визуальные работы",
        "interest_text": "Как ты относишься к рисованию, творчеству и визуальным искусствам вне урока?",
        "interest_activity": "рисую или занимаюсь творчеством",
    },
}


def _build_questions() -> list[dict]:
    questions = []
    order = 0
    for subject, spec in _CATALOG.items():
        questions.append({
            "subject": subject,
            "kind": SubjectQuestionKind.level,
            "text": spec["level_text"],
            "options": _level_options(spec["level_verb"]),
            "order": order,
        })
        order += 1
        questions.append({
            "subject": subject,
            "kind": SubjectQuestionKind.interest,
            "text": spec["interest_text"],
            "options": _interest_options(spec["interest_activity"]),
            "order": order,
        })
        order += 1
    return questions


QUESTIONS: list[dict] = _build_questions()


async def seed_subject_questions(db: AsyncSession) -> tuple[int, int, int]:
    """Upsert SubjectQuestion rows by (subject, kind). Returns (inserted, updated, skipped)."""
    inserted = updated = skipped = 0

    for q in QUESTIONS:
        result = await db.execute(
            select(SubjectQuestion).where(
                SubjectQuestion.subject == q["subject"], SubjectQuestion.kind == q["kind"]
            )
        )
        existing = result.scalar_one_or_none()

        fields = {"text": q["text"], "options": q["options"], "order": q["order"]}

        if existing is not None:
            changed = False
            for field, value in fields.items():
                if getattr(existing, field) != value:
                    setattr(existing, field, value)
                    changed = True
            updated += 1 if changed else 0
            skipped += 0 if changed else 1
            continue

        db.add(SubjectQuestion(subject=q["subject"], kind=q["kind"], **fields))
        inserted += 1

    return inserted, updated, skipped


async def main() -> None:
    async with async_session() as db:
        inserted, updated, skipped = await seed_subject_questions(db)
        await db.commit()
        print(
            f"Subject questions: inserted {inserted}, updated {updated}, skipped {skipped} "
            f"(total {len(QUESTIONS)}, {len(_CATALOG)} subjects)"
        )


if __name__ == "__main__":
    asyncio.run(main())
