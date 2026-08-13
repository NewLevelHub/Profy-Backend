"""Thinking-style methodology reference table — mirrors riasec_content.py/
mi_content.py's role, deterministic fallback source for "Как легче думать".

Unlike bigfive_content._NOTES, there's no low/mid/high tier here — a
thinking style only becomes evidence at all when report_narrative_context's
_thinking_style_evidence finds real signal (value > 0, top 2), so a single
descriptive note per style is enough: "was this observed" is the only
distinction that exists.

TZ_Profi.md §18.2 п.4 wants this section to carry "конкретные примеры
задач, а не абстракции" — each phrase below ends with one concrete example,
deliberately distinct in wording from riasec_content/mi_content's
STRENGTH_PHRASES so this section doesn't just repeat the "Сильные стороны"
formulation for the same trait (see report_narrative_context.
STRENGTH_CARD_EXCLUDED_SOURCE_TYPES for the other half of that separation —
these facts are excluded from strength_cards entirely, only ever shown here).

Two signals (1 or 2 detected styles) are merged into a single card, not one
card each — see report_narrative_fallback._thinking_style_notes(). This
module supplies the raw pieces that gets merged from: THINKING_STYLE_NOTES
(the original per-style cue+example, still used standalone for a single
signal), THINKING_STYLE_ADJ/THINKING_STYLE_IMPACT (middle/senior only —
title label and real-world-relevance phrase), THINKING_STYLE_CUE_SHORT
(junior only — same cue idea without an abstract label or career-adjacent
framing, TZ_Profi.md §4.1).
"""

THINKING_STYLE_NOTES: dict[str, str] = {
    "creative_think": (
        "Тебе легко придумывать несколько разных вариантов решения одной "
        "задачи — например, найти два-три способа сделать одно и то же."
    ),
    "systematic": (
        "Тебе удобнее, когда есть чёткий порядок действий — например, "
        "сначала расписать шаги по порядку, а потом уже начинать делать."
    ),
    "strategic": (
        "Ты видишь картину целиком и заранее продумываешь шаги вперёд — "
        "например, прикидываешь результат ещё до того, как начал."
    ),
    "practical": (
        "Тебе важно довести идею до результата, который реально работает — "
        "например, быстрее перейти от плана к делу, чем долго его обсуждать."
    ),
}

# Short adjective for middle/senior's merged title ("Тебе близко {adj}
# мышление" / "Тебе близки {adj1} и {adj2} мышление") — never shown to
# junior, who gets no abstract style labels at all (TZ_Profi.md §4.1).
THINKING_STYLE_ADJ: dict[str, str] = {
    "creative_think": "творческое",
    "systematic": "системное",
    "strategic": "стратегическое",
    "practical": "практическое",
}

# Junior-only: same idea as THINKING_STYLE_NOTES but a bare behavioral
# clause (lowercase, no trailing period, no "например" example) meant to be
# joined with report_narrative_fallback._join_ru when there are two signals
# — junior's sentences must stay short even when merging two styles into one
# card (TZ_Profi.md §4.1: "очень короткие предложения").
THINKING_STYLE_CUE_SHORT: dict[str, str] = {
    "creative_think": "тебе легко придумывать несколько разных способов сделать одно и то же",
    "systematic": "тебе удобнее, когда сначала есть понятный порядок действий",
    "strategic": "тебе нравится заранее продумывать, что будет дальше",
    "practical": "тебе важно быстро попробовать и увидеть результат",
}

# middle/senior only — one short verb-phrase per style, joined with "и" into
# "Люди с таким сочетанием часто умеют {impact1} и {impact2}." when there
# are two signals, or used alone for one. Deliberately not junior-facing:
# framed around roles/traits that show up in work and projects, which is
# exactly the career-adjacent abstraction junior must never see.
THINKING_STYLE_IMPACT: dict[str, str] = {
    "creative_think": "предлагать новые идеи",
    "systematic": "наводить порядок в сложных задачах",
    "strategic": "вести дело к продуманной заранее цели",
    "practical": "быстро превращать план в реальный результат",
}
