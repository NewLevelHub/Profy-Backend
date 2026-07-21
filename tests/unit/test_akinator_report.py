from app.services.akinator_engine import StopDecision
from app.services.akinator_report_service import (
    REPORT_MESSAGES, build_reveal_report, summarize_strengths,
)

# AC3 copy checklist: no absolutist verdicts ("твоя профессия — X", "ты
# будешь X", "точно"/"стопроцентно") — every reveal message must read as a
# suggestion, not a decree.
BANNED_PHRASES = [
    "твоя профессия",
    "ты будешь",
    "ты — ",
    "стопроцентно",
    "точно подходит",
    "однозначно",
]


def test_cluster_decision_is_uncertain_not_rejection():
    """AC1: the engine's own low confidence (cluster, no rejection involved)
    branches to "uncertain" — this is "движок не уверен", not "ребёнок отверг"."""
    decision = StopDecision(status="reveal_cluster", leaves=["a", "b"], reason="confidence")
    belief = {"a": 0.4, "b": 0.35, "c": 0.25}

    report = build_reveal_report(decision, belief, rejected_leaves=[])

    assert report.kind == "uncertain"
    assert report.followed_rejection is False
    assert report.backups == []


def test_single_decision_after_rejection_is_flagged_distinctly():
    """AC1: a confident single winner reached right after a rejection is
    still "confident" (the engine did converge), but flagged
    followed_rejection=True so it reads as "here's another idea", not a
    fresh, out-of-the-blue verdict — the "ребёнок отверг" branch."""
    decision = StopDecision(status="reveal_single", leaves=["b"], reason="confidence")
    belief = {"b": 0.7, "c": 0.3}

    fresh = build_reveal_report(decision, belief, rejected_leaves=[])
    after_rejection = build_reveal_report(decision, belief, rejected_leaves=["a"])

    assert fresh.kind == after_rejection.kind == "confident"
    assert fresh.followed_rejection is False
    assert after_rejection.followed_rejection is True
    assert fresh.message != after_rejection.message


def test_confident_reveal_carries_backup_alternates():
    decision = StopDecision(status="reveal_single", leaves=["b"], reason="confidence")
    belief = {"b": 0.7, "c": 0.2, "d": 0.1}

    report = build_reveal_report(decision, belief, rejected_leaves=[])

    assert report.backups == ["c", "d"]


def test_uncertain_reveal_has_no_backups():
    decision = StopDecision(status="reveal_cluster", leaves=["a", "b"], reason="confidence")
    belief = {"a": 0.4, "b": 0.35, "c": 0.25}

    report = build_reveal_report(decision, belief, rejected_leaves=[])

    assert report.backups == []


def test_ceiling_cluster_is_inconclusive_not_uncertain():
    """A cluster forced by the question ceiling (reason="ceiling") is a real
    engine failure to converge — distinct from a genuine close 2-3-way race
    (reason="confidence", still "uncertain") — and must carry strengths."""
    decision = StopDecision(status="reveal_cluster", leaves=["a", "b"], reason="ceiling")
    belief = {"a": 0.4, "b": 0.35, "c": 0.25}
    leaf_profiles = {
        "a": {"People": 2, "Care": 1},
        "b": {"People": 1, "Data": 2},
        "c": {"Data": 1},
    }

    report = build_reveal_report(decision, belief, rejected_leaves=[], leaf_profiles=leaf_profiles)

    assert report.kind == "inconclusive"
    assert report.strengths
    assert report.message == REPORT_MESSAGES["inconclusive"]


def test_confidence_cluster_stays_uncertain_but_now_carries_strengths():
    """A genuine close race (reason="confidence") deserves the same "why
    these came up" signal as a ceiling-forced cluster — only the message
    template and `kind` differ between the two, not whether strengths get
    computed. (Older behavior had confidence-clusters carry no strengths at
    all; changed as part of the "почему предложены" reveal-screen ticket.)"""
    decision = StopDecision(status="reveal_cluster", leaves=["a", "b"], reason="confidence")
    belief = {"a": 0.4, "b": 0.35, "c": 0.25}
    leaf_profiles = {
        "a": {"People": 2, "Care": 1},
        "b": {"People": 1, "Data": 2},
        "c": {"Data": 1},
    }

    report = build_reveal_report(decision, belief, rejected_leaves=[], leaf_profiles=leaf_profiles)

    assert report.kind == "uncertain"
    assert report.strengths


def test_summarize_strengths_picks_top_positive_axes():
    belief = {"a": 0.6, "b": 0.4}
    leaf_profiles = {
        "a": {"People": 2, "Data": -1},
        "b": {"People": 1, "Ideas": 2},
    }

    strengths = summarize_strengths(belief, leaf_profiles, top_n=2)

    # People: 0.6*2 + 0.4*1 = 1.6 (top); Ideas: 0.4*2 = 0.8; Data is negative.
    assert strengths[0] == "Ориентация на людей, общение"
    assert len(strengths) == 2


def test_summarize_strengths_ignores_nonpositive_axes():
    belief = {"a": 1.0}
    strengths = summarize_strengths(belief, {"a": {"Data": -2}})
    assert strengths == []


def test_report_messages_avoid_categorical_verdicts():
    """AC3: copy checklist, enforced — no absolutist phrasing in any template."""
    for key, text in REPORT_MESSAGES.items():
        lowered = text.lower()
        for banned in BANNED_PHRASES:
            assert banned not in lowered, f"{key!r} contains a verdict-like phrase: {banned!r}"
