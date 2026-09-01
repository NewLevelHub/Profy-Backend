"""Structural guards for the two generation phases — pure functions."""
import pytest

from app.services.development_plan_validation import (
    skeleton_problems,
    stage_problems,
    valid_skeleton,
    valid_stage,
)


def _task(track="profession", title="t"):
    return {"track": track, "title": title, "why": "w", "done_when": "d"}


def _stage(slot, tracks=("ent", "profession", "growth")):
    return {
        "slot": slot,
        "label": slot,
        "outcome": "готово",
        "tasks": [_task(t, f"{slot}-{t}") for t in tracks],
    }


def _skeleton(grade=11, is_foreign=False):
    from app.prompts.development_plan import stage_slots_for_grade

    slots = [s for s, _ in stage_slots_for_grade(grade)]
    tracks = ("ent", "profession", "growth")
    stages = [_stage(s, tracks) for s in slots]
    if is_foreign:
        stages[0]["tasks"].append(_task("language", f"{slots[0]}-language"))
    return {
        "target": {"role": "r", "why": "y", "university_name": "u", "specialty": "s"},
        "about_you": {"strengths": ["a"], "growth": {"area": "x", "why": "y", "evidence": "низкая C"}},
        "skills": ["навык"],
        "stages": stages,
    }


# ── valid_skeleton ────────────────────────────────────────────────────────────
def test_skeleton_happy_path():
    assert valid_skeleton(_skeleton(), grade=11, is_foreign=False)


def test_skeleton_rejects_wrong_stage_count():
    sk = _skeleton()
    sk["stages"] = sk["stages"][:3]
    assert not valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_rejects_wrong_slot_order():
    sk = _skeleton()
    sk["stages"][0]["slot"] = "bogus"
    assert not valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_rejects_empty_growth_evidence():
    sk = _skeleton()
    sk["about_you"]["growth"]["evidence"] = ""
    assert not valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_rejects_missing_ent_track_in_an_early_stage():
    sk = _skeleton()
    sk["stages"][1]["tasks"] = [_task("profession"), _task("growth"), _task("growth")]
    assert not valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_last_stage_needs_no_ent_but_still_needs_profession():
    sk = _skeleton()
    sk["stages"][-1]["tasks"] = [_task("admission"), _task("admission"), _task("profession")]
    assert valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_rejects_stage_without_a_profession_task():
    sk = _skeleton()
    sk["stages"][1]["tasks"] = [_task("ent"), _task("growth"), _task("admission")]
    assert not valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_requires_profession_in_every_stage_including_last():
    sk = _skeleton()
    sk["stages"][-1]["tasks"] = [_task("admission"), _task("admission"), _task("ent")]
    assert not valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_growth_is_optional():
    sk = _skeleton()
    for st in sk["stages"]:
        st["tasks"] = [_task("ent"), _task("profession"), _task("admission")]
    sk["stages"][-1]["tasks"] = [_task("admission"), _task("profession"), _task("admission")]
    assert valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_requires_language_track_when_foreign():
    sk = _skeleton(is_foreign=False)  # no language task
    assert not valid_skeleton(sk, grade=11, is_foreign=True)
    assert valid_skeleton(_skeleton(is_foreign=True), grade=11, is_foreign=True)


def test_skeleton_foreign_does_not_require_ent_tasks():
    sk = _skeleton(is_foreign=True)
    for st in sk["stages"]:
        st["tasks"] = [_task("language"), _task("profession"), _task("growth")]
    assert valid_skeleton(sk, grade=11, is_foreign=True)


def test_skeleton_rejects_too_many_tasks():
    sk = _skeleton()
    sk["stages"][0]["tasks"] = [_task("ent")] + [_task("profession") for _ in range(5)]  # 6
    assert not valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_allows_two_task_stage():
    sk = _skeleton()
    sk["stages"][1]["tasks"] = [_task("ent"), _task("profession")]
    assert valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_rejects_one_task_stage():
    sk = _skeleton()
    sk["stages"][1]["tasks"] = [_task("profession")]
    assert not valid_skeleton(sk, grade=11, is_foreign=False)


def test_skeleton_allows_five_tasks():
    sk = _skeleton()
    sk["stages"][0]["tasks"] = [
        _task("ent"), _task("profession"), _task("growth"), _task("growth"), _task("admission"),
    ]
    assert valid_skeleton(sk, grade=11, is_foreign=False)


# ── valid_stage ──────────────────────────────────────────────────────────────
def _action(kind="once", text="Разбери тему по бесплатному видео и реши 10 задач", ct=None):
    a = {"text": text, "time": "30 мин", "kind": kind}
    a["count_target"] = ct
    return a


def _expanded(track="ent", extra_actions=None):
    actions = [_action("repeat", "Реши 15 задач по теме", 6), _action("once")]
    if extra_actions:
        actions = extra_actions
    return {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": actions}]}]}


def test_stage_happy_path():
    assert valid_stage(_expanded("ent"), tracks_by_title={"t": "ent"})


def test_ent_task_without_repeat_is_a_hard_failure():
    data = {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": [_action("once")]}]}]}
    hard, _ = stage_problems(data, tracks_by_title={"t": "ent"})
    assert any("no kind=repeat" in h for h in hard)
    assert not valid_stage(data, tracks_by_title={"t": "ent"})


def test_ent_task_with_weekly_repeat_passes():
    actions = [_action("once", "Пройди пробный ЕНТ"), _action("repeat", "Каждую неделю разбирай 2-3 темы из своего списка пробелов", 11)]
    data = {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": actions}]}]}
    assert valid_stage(data, tracks_by_title={"t": "ent"})


def test_non_ent_stage_without_repeat_is_only_soft():
    data = {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": [_action("once")]}]}]}
    hard, soft = stage_problems(data, tracks_by_title={"t": "admission"})
    assert hard == []
    assert any("repeat" in s for s in soft)


def test_vague_ent_action_is_soft_flagged():
    actions = [_action("repeat", "Повтори темы за 10-11 класс по математике", 10), _action("once")]
    data = {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": actions}]}]}
    hard, soft = stage_problems(data, tracks_by_title={"t": "ent"})
    assert hard == []  # not rejected, just noted
    assert any("vague ENT" in s for s in soft)


def test_stage_repeat_needs_positive_count_target():
    data = {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": [_action("repeat", "x", None), _action("once")]}]}]}
    assert not valid_stage(data, tracks_by_title={"t": "ent"})


def test_stage_allows_step_with_one_action():
    data = {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": [_action("repeat", "x", 5)]}]}]}
    assert valid_stage(data, tracks_by_title={"t": "ent"})


def test_stage_rejects_task_with_no_steps():
    data = {"tasks": [{"title": "t", "steps": []}]}
    assert not valid_stage(data, tracks_by_title={"t": "ent"})


def test_stage_rejects_forbidden_marker():
    bad = [_action("repeat", "Найди репетитора и занимайся с ним", 5), _action("once")]
    data = {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": bad}]}]}
    assert not valid_stage(data, tracks_by_title={"t": "profession"})


def test_stage_off_archetype_profession_action_is_soft_not_hard():
    from app.services.development_plan_validation import stage_problems
    vague = [_action("repeat", "Стань увереннее в себе и своих силах", 5), _action("once", "Просто будь собой")]
    data = {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": vague}]}]}
    hard, soft = stage_problems(data, tracks_by_title={"t": "profession"})
    assert hard == []
    assert any("off-archetype" in s for s in soft)


def test_stage_heavy_profession_action_is_soft_flagged():
    from app.services.development_plan_validation import stage_problems
    heavy = [
        _action("repeat", "Пройди курс по архитектуре для начинающих", 3),
        _action("project", "Собери портфолио своих работ по архитектуре"),
    ]
    data = {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": heavy}]}]}
    hard, soft = stage_problems(data, tracks_by_title={"t": "profession"})
    assert hard == []  # not rejected — tuning phase
    assert any("too heavy" in s for s in soft)


def test_stage_allows_non_archetype_text_for_non_profession_tracks():
    ok = [_action("repeat", "Раз в неделю записывай 2-минутный питч на телефон", 8), _action("once", "Послушай себя")]
    data = {"tasks": [{"title": "t", "steps": [{"title": "s", "actions": ok}]}]}
    assert valid_stage(data, tracks_by_title={"t": "growth"})
