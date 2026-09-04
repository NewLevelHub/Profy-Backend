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

import contextlib
import contextvars
import logging
import re
from collections.abc import Iterator, Mapping

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
#
# ⚠ This set is the SQL enum `locale_enum`. `app/models/user.py` builds its
# `Enum(...)` from these values, but the Postgres type itself was created by
# Alembic (migration d80fbf5d1f43). Adding a value here WITHOUT a companion
# migration that runs `ALTER TYPE locale_enum ADD VALUE '<new>'` makes PATCH
# /auth/me pass Pydantic validation and then 500 on commit. Change both together.
KNOWN_LOCALES: tuple[str, ...] = ("ru", "kk")

# Free-text values of profiles.language that name Kazakh. Full roots only:
# a bare "kaz"/"каз" substring also matches ordinary words ("показать",
# "рассказать", "kazan"). Matches docs/i18n-contract.md §6.
_KK_LANGUAGE_FIELD_RE = re.compile(r"казах|kazakh|qaz|қаз", re.IGNORECASE)

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
        segments = part.split(";")
        code = segments[0].strip().lower().split("-", 1)[0]
        if not code:
            continue
        # Scan every ";"-separated parameter for a "q" weight, case-insensitively
        # ("q=0.9", "Q=0.9"), taking only the numeric value of that one segment —
        # "ru;q=0.1;x=1" must not feed "0.1;x=1" to float().
        q = 1.0
        for seg in segments[1:]:
            key, sep, value = seg.partition("=")
            if sep and key.strip().lower() == "q":
                try:
                    q = float(value.strip())
                except ValueError:
                    q = 1.0
                break
        q = max(0.0, min(1.0, q))
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


@contextlib.contextmanager
def use_locale(locale: str | None) -> Iterator[str]:
    """Force the current-locale contextvar for a block, **bypassing the
    ``SUPPORTED_LOCALES`` runtime gate** (clamps to ``KNOWN_LOCALES`` instead).

    For server-side artifact generation — the report narrative and its
    deterministic fallback — which must render in the *artifact owner's*
    locale (``users.locale``, which may be ``"kk"`` before KZ-603), not the
    locale of whoever triggered the request (an admin on ``ru`` opening a
    ``kk`` student's ``/results`` must still get the ``kk`` report). Every
    KZ-307 accessor (``mi_labels()`` …) reads ``get_locale()``, so wrapping
    the whole build in this is what makes the deterministic path actually
    Kazakh. Restores the previous value on exit, exception-safe.
    """
    resolved = locale if locale in KNOWN_LOCALES else DEFAULT_LOCALE
    token = _current_locale.set(resolved)
    try:
        yield resolved
    finally:
        _current_locale.reset(token)


# ── Localized-content selection ─────────────────────────────────────────────────


class MissingLocalizedText(LookupError):
    """A ``{locale: text}`` mapping carried neither the requested locale nor the
    ``ru`` source-of-truth value (or was empty / ``None``).

    ``ru`` is the source of truth and the content banks self-heal on deploy, so
    this is a data-integrity bug, not a routine fallback — contract §5 forbids
    returning ``""`` / ``None`` where text is expected, so ``pick_locale`` raises
    this instead. The fallback tally is still incremented before the raise.
    """

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

    Raises :class:`MissingLocalizedText` when even ``DEFAULT_LOCALE`` is absent
    (or the mapping is empty / ``None``) — contract §5 forbids returning ``""``
    where text is expected. The fallback tally is incremented first.
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
    raise MissingLocalizedText(
        f"no text for locale {loc!r} and no {DEFAULT_LOCALE!r} fallback "
        f"in mapping with keys {sorted(mapping) if mapping else []}"
    )
