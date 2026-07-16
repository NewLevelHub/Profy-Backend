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

from app.services.akinator_engine import StopDecision

# Extra alternates surfaced alongside a confident single winner, so a later
# rejection (see reject_leaf) has somewhere to go without restarting the walk.
BACKUP_COUNT = 2

REPORT_MESSAGES: dict[str, str] = {
    "confident": "Похоже, это направление может тебе подойти — но не единственное, вот ещё пара вариантов на заметку.",
    "uncertain": "Пока не набралось уверенности в одном варианте — вот несколько направлений, которые стоит изучить.",
    "confident_after_rejection": "Раз предыдущий вариант не откликнулся, вот другое направление, которое стоит рассмотреть.",
    "uncertain_after_rejection": "После твоего отклика уверенности пока меньше — вот несколько направлений на выбор.",
}


@dataclass(frozen=True, slots=True)
class RevealReport:
    kind: Literal["confident", "uncertain"]
    leaves: list[str] = field(default_factory=list)
    backups: list[str] = field(default_factory=list)
    followed_rejection: bool = False
    message: str = ""


def build_reveal_report(
    decision: StopDecision, belief: dict[str, float], rejected_leaves: list[str] | None = None
) -> RevealReport:
    """Branch a reveal StopDecision into a report: "confident" (single
    winner, plus backups from the belief tail) vs "uncertain" (cluster, no
    ranking implied — the engine genuinely doesn't have a favorite). Also
    flags whether this reveal followed a rejection, purely to pick the right
    message template (a fresh confident reveal reads differently from one
    offered right after the user said no to something else)."""
    followed_rejection = bool(rejected_leaves)

    if decision.status == "reveal_cluster":
        kind = "uncertain"
        key = "uncertain_after_rejection" if followed_rejection else "uncertain"
        return RevealReport(
            kind=kind,
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
