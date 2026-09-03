"""Per-locale catalog for methodology reference strings (KZ-307).

Every string that used to be a Russian literal in the deterministic content
services — `app/services/{riasec,bigfive,mi,thinking_style}_content.py`,
`gap_analysis_service.py`, `university_requirements.py`, `goal_overlay_service.py`
and `app/data/resource_catalog.py` — now lives here as an area module with
identical-shape ``RU`` and ``KK`` trees. Callers get the request-locale tree
via :func:`tr`.

Fallback is **per top-level key**: if the requested locale's tree is missing a
key, that key's ``ru`` value is used and an ``i18n.fallback`` hit is recorded
(so a dropped `kk` key is served as `ru`, never blank — contract §5). Nested
values (dicts / lists under a top-level key) are all-or-nothing per key, which
matches how each area is structured: one top-level key = one logical table.
"""

from __future__ import annotations

from typing import Any

from app.i18n import DEFAULT_LOCALE, get_locale, record_fallback

from . import (
    bigfive,
    email,
    gap_analysis,
    goal_overlay,
    mi,
    motivation,
    resource_catalog,
    riasec,
    thinking_style,
    university_requirements,
)

_AREAS: dict[str, Any] = {
    "riasec": riasec,
    "bigfive": bigfive,
    "mi": mi,
    "motivation": motivation,
    "thinking_style": thinking_style,
    "gap_analysis": gap_analysis,
    "university_requirements": university_requirements,
    "resource_catalog": resource_catalog,
    "goal_overlay": goal_overlay,
    "email": email,
}


def tr(area: str, *, locale: str | None = None) -> dict[str, Any]:
    """The whole ``{key: value}`` tree for ``area`` in the request locale
    (``ru`` fill-in per missing top-level key, with a fallback tally)."""
    mod = _AREAS[area]
    loc = locale or get_locale()
    ru: dict[str, Any] = mod.RU
    if loc == DEFAULT_LOCALE:
        return ru

    other: dict[str, Any] = getattr(mod, loc.upper(), {})
    resolved: dict[str, Any] = {}
    fell_back = False
    for key, ru_value in ru.items():
        if key in other:
            resolved[key] = other[key]
        else:
            resolved[key] = ru_value
            fell_back = True
    if fell_back:
        record_fallback(loc)
    return resolved


def key(area: str, *path: str, locale: str | None = None) -> Any:
    """Convenience: ``tr(area)[path[0]][path[1]]…``."""
    node: Any = tr(area, locale=locale)
    for step in path:
        node = node[step]
    return node
