"""Request-locale resolution.

The locale of a request resolves as:

    users.locale (when authenticated and set) -> Accept-Language -> DEFAULT_LOCALE

See docs/i18n-contract.md for the full contract.

`kk` is intentionally absent from ``SUPPORTED_LOCALES`` until the final enable PR
(ticket KZ-603) — there is no feature flag, so a partially translated ``kk`` must
stay unreachable for users. While ``kk`` is unsupported, ``normalize_locale("kk")``
returns ``"ru"`` and ``set_locale("kk")`` stores ``"ru"``.
"""

from __future__ import annotations

import contextvars
import logging
import re
from collections.abc import Mapping

logger = logging.getLogger("app.i18n")

DEFAULT_LOCALE = "ru"

# KZ-603 adds "kk" here (rollout without a feature flag). Keep this the single
# gate: every other module asks SUPPORTED_LOCALES / normalize_locale, never
# hardcodes the set.
SUPPORTED_LOCALES: tuple[str, ...] = ("ru",)

# Every locale the DB / persistence layer accepts, regardless of the runtime
# gate above. A user's stored choice may be "kk" before KZ-603 — it just isn't
# honored by get_locale() yet. Used by the write paths (PATCH /auth/me,
# registration), not by request resolution.
KNOWN_LOCALES: tuple[str, ...] = ("ru", "kk")

# Free-text values of profiles.language that imply a Kazakh UI preference.
_KK_LANGUAGE_FIELD_RE = re.compile(r"каз[аоя]|qaz|kaz|қаз", re.IGNORECASE)

_current_locale: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_locale", default=DEFAULT_LOCALE
)


def normalize_locale(raw: str | None, *, allowed: tuple[str, ...] | None = None) -> str:
    """Map an ``Accept-Language`` value (or a bare code) to an allowed locale.

    Parses comma-separated entries with optional ``;q=`` weights and returns the
    highest-weighted entry whose base language is in ``allowed`` (default
    ``SUPPORTED_LOCALES`` — the runtime gate); falls back to ``DEFAULT_LOCALE``.
    Pass ``allowed=KNOWN_LOCALES`` on write paths that may persist "kk" before
    KZ-603. Never raises.
    """
    allowed = SUPPORTED_LOCALES if allowed is None else allowed
    if not raw:
        return DEFAULT_LOCALE

    candidates: list[tuple[float, int, str]] = []
    for idx, part in enumerate(raw.split(",")):
        token, _, params = part.strip().partition(";")
        code = token.strip().lower().split("-", 1)[0]
        if not code:
            continue
        q = 1.0
        params = params.strip()
        if params.startswith("q="):
            try:
                q = float(params[2:])
            except ValueError:
                q = 1.0
        candidates.append((q, idx, code))

    for _q, _idx, code in sorted(candidates, key=lambda c: (-c[0], c[1])):
        if code in allowed:
            return code
    return DEFAULT_LOCALE


def guess_locale_from_language_field(value: str | None) -> str:
    """Best-effort UI locale from the free-text ``profiles.language`` field.

    ``"kk"`` when the value looks like it names Kazakh, else ``DEFAULT_LOCALE``.
    Only used to pre-fill ``users.locale`` when the user has not set it yet.
    """
    if value and _KK_LANGUAGE_FIELD_RE.search(value):
        return "kk"
    return DEFAULT_LOCALE


def set_locale(locale: str | None) -> str:
    """Store ``locale`` as the current request locale, clamped to a supported
    value. Returns what was actually stored."""
    resolved = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    _current_locale.set(resolved)
    return resolved


def get_locale() -> str:
    """Current request locale. Safe to call from any service without a ``Request``."""
    return _current_locale.get()


# ── Localized-content selection ─────────────────────────────────────────────────

# Coarse in-process tally of "asked for X, served ru instead" events, keyed by
# the requested locale. KZ-604 wires this to real metrics/analytics; for now it
# is enough to expose it for tests and a periodic log.
_fallback_counts: dict[str, int] = {}


def record_fallback(locale: str) -> None:
    """Note that a `locale` lookup fell back to ``DEFAULT_LOCALE``."""
    _fallback_counts[locale] = _fallback_counts.get(locale, 0) + 1
    logger.debug("i18n fallback: locale=%s -> %s", locale, DEFAULT_LOCALE)


def fallback_counts() -> dict[str, int]:
    """Snapshot of fallback tallies so far (test/inspection hook)."""
    return dict(_fallback_counts)


def reset_fallback_counts() -> None:
    _fallback_counts.clear()


def pick_locale(mapping: Mapping[str, str] | None, locale: str | None = None) -> str:
    """Pick the text for ``locale`` from a ``{locale: text}`` mapping.

    Falls back to ``DEFAULT_LOCALE`` when the requested locale is missing or
    blank, recording an ``i18n.fallback`` hit. ``locale`` defaults to the
    current request locale.

    Returns ``""`` only when even ``DEFAULT_LOCALE`` is absent — a data-integrity
    problem (``ru`` is the source of truth), surfaced via the fallback tally
    rather than an exception so a page still renders.
    """
    loc = locale or get_locale()

    if mapping:
        value = mapping.get(loc)
        if value:
            return value
        ru_value = mapping.get(DEFAULT_LOCALE)
        if ru_value:
            if loc != DEFAULT_LOCALE:
                record_fallback(loc)
            return ru_value

    record_fallback(loc)
    return ""
