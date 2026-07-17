"""Turns a StopDecision into a user-facing reveal report.

Distinguishes the two "не подошло" scenarios from profi_axes_phase1.md: the
engine itself being unsure (StopDecision.status == "reveal_cluster", a close
race with no clear winner) vs the user having explicitly rejected a prior
suggestion (akinator_session_service.reject_leaf re-deriving a new decision
afterwards) — the same StopDecision shape covers both, so `rejected_leaves`
is what tells them apart here.

Copy checklist (see ticket AC3): no absolutist verdicts like "твоя профессия
— X" — every message is hedged/suggestive ("возможно", "похоже", "стоит
рассмотреть"), matching the tone already used for wellbeing zone messages in
ai_service.py.
"""
from dataclasses import dataclass, field
from typing import Literal

from app.core.axes import AXIS_CATALOG
from app.services.akinator_engine import StopDecision

# Extra alternates surfaced alongside a confident single winner, so a later
# rejection (see reject_leaf) has somewhere to go without restarting the walk.
BACKUP_COUNT = 2

# How many axis strengths to surface on the honest "couldn't narrow it down"
# screen (see summarize_strengths) — enough to feel specific, not a data dump.
STRENGTHS_COUNT = 3

REPORT_MESSAGES: dict[str, str] = {
    "confident": "Похоже, это направление может тебе подойти — но не единственное, вот ещё пара вариантов на заметку.",
    "uncertain": "Пока не набралось уверенности в одном варианте — вот несколько направлений, которые стоит изучить.",
    "confident_after_rejection": "Раз предыдущий вариант не откликнулся, вот другое направление, которое стоит рассмотреть.",
    "uncertain_after_rejection": "После твоего отклика уверенности пока меньше — вот несколько направлений на выбор.",
    "inconclusive": "Если честно, нам не хватило вопросов, чтобы уверенно выделить один вариант. Зато мы разглядели вот что в тебе:",
    "inconclusive_after_rejection": "Даже после уточнений уверенного варианта не нашлось — но кое-что важное о тебе мы всё же поняли:",
}


@dataclass(frozen=True, slots=True)
class RevealReport:
    kind: Literal["confident", "uncertain", "inconclusive"]
    leaves: list[str] = field(default_factory=list)
    backups: list[str] = field(default_factory=list)
    followed_rejection: bool = False
    message: str = ""
    strengths: list[str] = field(default_factory=list)


def summarize_strengths(
    belief: dict[str, float],
    leaf_profiles: dict[str, dict[str, int]],
    top_n: int = STRENGTHS_COUNT,
) -> list[str]:
    """Turn the current belief into a friendly list of strengths, for the
    honest "couldn't narrow it down" screen — used when there's no single
    profession to point at, but the session still carries real signal.

    Weighted-averages every remaining candidate's own axis profile by how
    much belief mass it still holds (the same Direction.profile the engine
    scores answers against — see akinator_engine.match_score), then reports
    the axes with the strongest positive weighted score as plain labels
    (AxisDefinition.label_ru). No new data collection: this is the same
    signal the engine already uses to rank leaves, just read the other way
    round — "what kind of profile does the belief that's left describe?"."""
    weighted: dict[str, float] = {axis.code: 0.0 for axis in AXIS_CATALOG}
    for slug, prob in belief.items():
        profile = leaf_profiles.get(slug, {})
        for axis_code, value in profile.items():
            if axis_code in weighted:
                weighted[axis_code] += prob * value

    label_by_code = {axis.code: axis.label_ru for axis in AXIS_CATALOG}
    ranked = sorted(weighted.items(), key=lambda item: item[1], reverse=True)
    return [label_by_code[code] for code, score in ranked if score > 0][:top_n]


def build_reveal_report(
    decision: StopDecision,
    belief: dict[str, float],
    rejected_leaves: list[str] | None = None,
    leaf_profiles: dict[str, dict[str, int]] | None = None,
) -> RevealReport:
    """Branch a reveal StopDecision into a report: "confident" (single
    winner, plus backups from the belief tail), "uncertain" (cluster, no
    ranking implied — the engine genuinely doesn't have a favorite among a
    few close contenders), or "inconclusive" (cluster forced by the question
    ceiling, reason="ceiling" — the engine never actually converged, so this
    reads as an honest "couldn't pin it down" instead of "a few good options").
    Also flags whether this reveal followed a rejection, purely to pick the
    right message template (a fresh reveal reads differently from one
    offered right after the user said no to something else)."""
    followed_rejection = bool(rejected_leaves)

    if decision.status == "reveal_cluster":
        if decision.reason == "ceiling":
            key = "inconclusive_after_rejection" if followed_rejection else "inconclusive"
            return RevealReport(
                kind="inconclusive",
                leaves=list(decision.leaves),
                backups=[],
                followed_rejection=followed_rejection,
                message=REPORT_MESSAGES[key],
                strengths=summarize_strengths(belief, leaf_profiles or {}),
            )

        key = "uncertain_after_rejection" if followed_rejection else "uncertain"
        return RevealReport(
            kind="uncertain",
            leaves=list(decision.leaves),
            backups=[],
            followed_rejection=followed_rejection,
            message=REPORT_MESSAGES[key],
        )

    ranked = sorted(belief.items(), key=lambda item: item[1], reverse=True)
    backups = [slug for slug, _ in ranked if slug not in decision.leaves][:BACKUP_COUNT]
    key = "confident_after_rejection" if followed_rejection else "confident"
    return RevealReport(
        kind="confident",
        leaves=list(decision.leaves),
        backups=backups,
        followed_rejection=followed_rejection,
        message=REPORT_MESSAGES[key],
    )
