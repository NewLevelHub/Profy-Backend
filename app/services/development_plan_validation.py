"""Structural guards for the two generation phases.

Strict-mode Structured Outputs can't express "exactly 4 stages, 3-5 tasks",
so those counts are checked here. A failed HARD check triggers one corrective
retry in `development_plan_service`; a second failure is a 503. SOFT checks are
logged only (quality nudges for prompt tuning), they don't reject a plan.
"""
from app.prompts.development_plan import (
    FORBIDDEN_MARKERS,
    PROFESSION_ARCHETYPES,
    stage_slots_for_grade,
)

# A simplified local plan stage is often just ent + one light profession task.
_MIN_TASKS = 2
_MAX_TASKS = 5
_MIN_STEPS_PER_TASK = 1
_MIN_ACTIONS_PER_STEP = 1

# Keyword buckets a `profession` action text is expected to hit at least one of
# (soft check — a miss is logged, not rejected). Kept to the LIGHT archetypes.
_ARCHETYPE_KEYWORDS: tuple[tuple[str, ...], ...] = (
    ("лекци", "документал", "видео", "разбор", "посмотри", "послушай"),
    ("статья", "статью", "главу", "прочит", "прочти", "книг"),
    ("набросок", "набросай", "зарисов", "этюд", "замер", "наблюд", "заметк"),
    ("олимпиад", "учител", "школьн"),
    ("разговор", "спроси", "интервью", "специалист", "поговори"),
)

# Heavy formats track=profession must NOT use (soft — logged, not rejected).
_PROFESSION_TOO_HEAVY = (
    "пройди курс", "пройти курс", "серию видео", "серия видео", "серии видео",
    "портфолио", "каждую неделю", "еженедельн", "мини-проект",
    "по одной в неделю", "практикуйся",
)


def _has_forbidden(text: str) -> bool:
    low = text.lower().replace("бесплатн", "")
    return any(marker in low for marker in FORBIDDEN_MARKERS)


# Vague ENT phrasings that give the student nothing concrete (soft-flagged).
_VAGUE_ENT = (
    "повтори программу", "повтори темы за", "повторяй темы за",
    "начни повторять темы", "пройди программу за", "повтори весь материал",
    "повтори все темы",
)


def _looks_vague_ent(text: str) -> bool:
    return any(m in text.lower() for m in _VAGUE_ENT)


def _looks_like_archetype(text: str) -> bool:
    low = text.lower()
    return any(any(k in low for k in bucket) for bucket in _ARCHETYPE_KEYWORDS)


def skeleton_problems(data: dict, *, grade: int, is_foreign: bool) -> list[str]:
    """Hard structural problems with a phase-1 skeleton. Empty list = ok."""
    problems: list[str] = []
    stages = data.get("stages") or []
    expected_slots = [s for s, _ in stage_slots_for_grade(grade)]
    if [s.get("slot") for s in stages] != expected_slots:
        problems.append(
            f"slots {[s.get('slot') for s in stages]} != expected {expected_slots}"
        )
        return problems  # nothing else is meaningful once the shape is wrong

    about = data.get("about_you") or {}
    if not about.get("strengths"):
        problems.append("about_you.strengths empty")
    growth = about.get("growth")
    if growth is not None and not growth.get("evidence"):
        problems.append("about_you.growth present but evidence empty")

    saw_language = False
    last_idx = len(stages) - 1
    for i, stage in enumerate(stages):
        slot = stage.get("slot")
        tasks = stage.get("tasks") or []
        if not (_MIN_TASKS <= len(tasks) <= _MAX_TASKS):
            problems.append(f"stage '{slot}': {len(tasks)} tasks (want {_MIN_TASKS}-{_MAX_TASKS})")
        if not stage.get("outcome"):
            problems.append(f"stage '{slot}': no outcome")
        tracks = set()
        for task in tasks:
            if not (task.get("title") and task.get("why") and task.get("done_when")):
                problems.append(f"stage '{slot}': task missing title/why/done_when")
            tracks.add(task.get("track"))
            if task.get("track") == "language":
                saw_language = True
        # track=profession — a light task in EVERY stage.
        if "profession" not in tracks:
            problems.append(f"stage '{slot}': no profession task")
        # ENT spine — first 3 stages, LOCAL university only (foreign runs on
        # `language`; the last stage is exam-sit + document submission).
        if i < last_idx and not is_foreign and "ent" not in tracks:
            problems.append(f"stage '{slot}': no ent task")
        # `growth` is conditional (only when there's a real growth point) —
        # not enforced here.

    if is_foreign and not saw_language:
        problems.append("foreign university but no language task anywhere")
    return problems


def valid_skeleton(data: dict, *, grade: int, is_foreign: bool) -> bool:
    return not skeleton_problems(data, grade=grade, is_foreign=is_foreign)


def stage_problems(data: dict, *, tracks_by_title: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return (hard, soft). `hard` non-empty -> retry/reject. `soft` -> log only."""
    hard: list[str] = []
    soft: list[str] = []

    tasks = data.get("tasks") or []
    if not tasks:
        hard.append("no tasks returned")
        return hard, soft

    saw_repeat = False
    for task in tasks:
        title = task.get("title", "")
        track = tracks_by_title.get(title)
        steps = task.get("steps") or []
        if len(steps) < _MIN_STEPS_PER_TASK:
            hard.append(f"task '{title}': no steps")
            continue
        ent_has_repeat = False
        for step in steps:
            actions = step.get("actions") or []
            if len(actions) < _MIN_ACTIONS_PER_STEP:
                hard.append(f"task '{title}' step '{step.get('title', '')}': no actions")
                continue
            for action in actions:
                text = action.get("text") or ""
                if not text or not action.get("time"):
                    hard.append(f"task '{title}': action missing text/time")
                    continue
                kind = action.get("kind")
                if kind not in ("once", "repeat", "project"):
                    hard.append(f"task '{title}': bad kind '{kind}'")
                    continue
                if kind == "repeat":
                    saw_repeat = True
                    if track == "ent":
                        ent_has_repeat = True
                    ct = action.get("count_target")
                    if not isinstance(ct, int) or ct <= 0:
                        hard.append(f"task '{title}': repeat without count_target")
                if _has_forbidden(text):
                    hard.append(f"task '{title}': forbidden phrasing — {text[:60]!r}")
                if track == "ent" and _looks_vague_ent(text):
                    soft.append(f"task '{title}': vague ENT action — {text[:70]!r}")
                if track == "profession":
                    if not _looks_like_archetype(text):
                        soft.append(f"task '{title}': profession action off-archetype — {text[:60]!r}")
                    heavy = next((m for m in _PROFESSION_TOO_HEAVY if m in text.lower()), None)
                    if heavy:
                        soft.append(f"task '{title}': profession action too heavy ('{heavy}') — {text[:60]!r}")
        # The ENT task IS the weekly prep regime — it must carry a counted drill.
        if track == "ent" and not ent_has_repeat:
            hard.append(f"task '{title}': ENT task has no kind=repeat (weekly drill)")

    if not saw_repeat:
        soft.append("stage has no kind=repeat action")

    return hard, soft


def valid_stage(data: dict, *, tracks_by_title: dict[str, str]) -> bool:
    hard, _ = stage_problems(data, tracks_by_title=tracks_by_title)
    return not hard


__all__ = [
    "valid_skeleton", "skeleton_problems", "valid_stage", "stage_problems",
    "PROFESSION_ARCHETYPES",
]
