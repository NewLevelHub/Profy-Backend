"""Thinking-style methodology reference table — mirrors riasec_content.py/
mi_content.py's role, deterministic fallback source for "Как легче думать".

Unlike bigfive_content._NOTES, there's no low/mid/high tier here — a
thinking style only becomes evidence at all when report_narrative_context's
_thinking_style_evidence finds real signal (value > 0, top 2), so a single
descriptive note per style is enough: "was this observed" is the only
distinction that exists.
"""

THINKING_STYLE_NOTES: dict[str, str] = {
    "creative_think": "Тебе легко придумывать несколько разных вариантов решения одной задачи.",
    "systematic": "Тебе удобнее, когда есть чёткий порядок и понятная структура действий.",
    "strategic": "Ты видишь картину целиком и заранее продумываешь шаги вперёд.",
    "practical": "Тебе важно довести идею до результата, который реально работает.",
}
