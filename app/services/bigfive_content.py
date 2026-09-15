"""
Big Five methodology reference — locale-aware accessors over
`app/i18n/catalog/bigfive.py` (KZ-307) plus the relative-tiering logic
(`relative_bands` and friends), which stays here because it's computation, not
copy.
"""
from typing import Literal

from app.i18n.catalog import tr

# Big Five tiering is RELATIVE, not absolute. There are no population norms
# for this instrument (nor age-appropriate ones for 14-18), so a raw min-max
# % like "62" has no interpretable meaning on its own — "answered 3 to
# everything" already lands at 50. Instead every trait is judged against the
# student's OWN average across their five traits: a trait `_REL_BAND` points
# above that average reads as "проявляется ярче", `_REL_BAND` below as
# "проявляется слабее", everything else as "заметно". `_FLAT_SPREAD` guards
# against labelling noise on a genuinely even profile. See relative_bands().
_REL_BAND = 8.0
_FLAT_SPREAD = 10.0

# Only 3 traits feed "Сильные стороны" (Openness, Conscientiousness, Emotional
# Stability) — Extraversion/Agreeableness aren't reliably "strengths". Same
# product decision on the low/"growth" side: a low score on extraversion or
# agreeableness is temperament, not a deficiency. Used by
# report_v2_assembler.build_personality_note to scope which low traits get named.
GROWTH_ELIGIBLE_TRAITS = frozenset({"openness", "conscientiousness", "emotional_stability"})


# ── locale-aware string tables (from app/i18n/catalog/bigfive.py) ──────────────

def bigfive_labels() -> dict[str, str]:
    """Domain label per N/E/O/A/C letter — admin/debug only."""
    return tr("bigfive")["labels"]


def likert_labels() -> list[str]:
    """The fixed 1-5 agreement scale (different wording from RIASEC's) —
    admin-panel display of raw answers."""
    return tr("bigfive")["likert"]


def thinking_style_labels() -> dict[str, str]:
    return tr("bigfive")["thinking_style_labels"]


def personality_labels() -> dict[str, str]:
    """"Твой характер" — descriptive-name label per trait (openness…)."""
    return tr("bigfive")["personality_labels"]


def relative_bands(profile: dict[str, float]) -> dict[str, Literal["low", "medium", "high"]]:
    """Per-trait band relative to the student's own five-trait average — the
    single source of the high/medium/low tier everything downstream uses.
    `profile` is the 5-key dict `build_personality_profile()` returns (or a
    stored `AnalysisResult.personality_profile` row). An even profile
    (spread < `_FLAT_SPREAD`) is all "medium"."""
    values = list(profile.values())
    if not values:
        return {}
    if max(values) - min(values) < _FLAT_SPREAD:
        return {trait: "medium" for trait in profile}
    mean = sum(values) / len(values)
    bands: dict[str, Literal["low", "medium", "high"]] = {}
    for trait, value in profile.items():
        delta = value - mean
        bands[trait] = "high" if delta >= _REL_BAND else "low" if delta <= -_REL_BAND else "medium"
    return bands


def _note_tier(band: str) -> str:
    """`relative_bands` speaks low/medium/high; the notes tables are keyed
    high/mid/low."""
    return {"high": "high", "low": "low", "medium": "mid"}[band]


def strength_phrases(profile: dict[str, float]) -> list[str]:
    """Admin-only `personality_highlights`. `profile` is the 5-trait dict
    (build_personality_profile), so Emotional Stability is already the
    positive direction — no separate low-Neuroticism check."""
    bands = relative_bands(profile)
    table = tr("bigfive")["strength_phrases"]
    return [table[t] for t in ("openness", "conscientiousness", "emotional_stability") if bands.get(t) == "high"]


def personality_notes_for_age(is_junior: bool, profile: dict[str, float]) -> dict[str, str]:
    """Age-appropriate tiered note per trait in `profile` — computed fresh from
    the numeric tier every time, not read from stored text. `profile` may be a
    stored `AnalysisResult.personality_profile` row just as well."""
    table = tr("bigfive")["notes_junior" if is_junior else "notes"]
    bands = relative_bands(profile)
    return {
        trait: table[trait][_note_tier(bands.get(trait, "medium"))]
        for trait in profile
    }


def build_personality_profile(
    bigfive_normalized: dict[str, float],
) -> tuple[dict[str, float], dict[str, str]]:
    """Display-ready 5-trait profile + one tiered (adult-worded) note per
    trait. Neuroticism is flipped to Emotional Stability (100 - N) so a high
    bar always reads positive. Tiering is relative (see relative_bands)."""
    profile = {
        "openness": bigfive_normalized.get("O", 0.0),
        "conscientiousness": bigfive_normalized.get("C", 0.0),
        "extraversion": bigfive_normalized.get("E", 0.0),
        "agreeableness": bigfive_normalized.get("A", 0.0),
        "emotional_stability": round(100.0 - bigfive_normalized.get("N", 0.0), 1),
    }
    return profile, personality_notes_for_age(is_junior=False, profile=profile)
