"""Thinking-style methodology reference — locale-aware accessors over
`app/i18n/catalog/thinking_style.py` (KZ-307). Deterministic fallback source
for "Как легче думать".

No low/mid/high tier here — a style is evidence only when
`report_narrative_context._thinking_style_evidence` finds real signal
(value > 0, top 2), so one descriptive note per style is enough.

Pieces: `thinking_style_notes()` (cue + concrete example, standalone single
signal), `thinking_style_adj()` / `thinking_style_impact()` (middle/senior only
— title label + real-world-relevance phrase), `thinking_style_cue_short()`
(junior only — cue without the abstract label, TZ_Profi.md §4.1).
"""

from app.i18n.catalog import tr


def thinking_style_notes() -> dict[str, str]:
    return tr("thinking_style")["notes"]


def thinking_style_adj() -> dict[str, str]:
    return tr("thinking_style")["adj"]


def thinking_style_cue_short() -> dict[str, str]:
    return tr("thinking_style")["cue_short"]


def thinking_style_impact() -> dict[str, str]:
    return tr("thinking_style")["impact"]
