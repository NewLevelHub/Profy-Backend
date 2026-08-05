"""Derive the "Стиль мышления" report block from Big Five facet scores.

TZ_Profi.md defines 9 thinking-style categories; only 4 map honestly onto
Big Five (a personality instrument, not a cognitive-ability test) — the rest
(logical/mathematical/verbal/spatial/social_think) would need an ability
test, which this product doesn't have. Deliberately not faked here."""

Facet = tuple[str, int]


def compute(facet_normalized: dict[Facet, float]) -> dict[str, float]:
    o1 = facet_normalized.get(("O", 1), 0.0)  # Imagination
    o2 = facet_normalized.get(("O", 2), 0.0)  # Artistic Interests
    return {
        "creative_think": round((o1 + o2) / 2, 1),
        "systematic": facet_normalized.get(("C", 2), 0.0),  # Orderliness
        "strategic": facet_normalized.get(("C", 4), 0.0),  # Achievement-Striving
        "practical": facet_normalized.get(("C", 1), 0.0),  # Self-Efficacy
    }
