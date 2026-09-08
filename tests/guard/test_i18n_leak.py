"""KZ-602 — CI guards against Russian leaking into `kk` responses.

Two surfaces:
  * the AI report narrative (`/results`) — every text field MUST be Kazakh
    (checked with the same heuristic the runtime validator uses);
  * the university/program catalog — `description` / `who_its_for` are still
    Russian until KZ-504, everything else that is UI copy must be Kazakh.

The skip-list lives in `tests/data/i18n_guard_config.json`, not here.
"""
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import use_locale
from app.i18n.catalog import tr
from app.models.assessment import Assessment, AssessmentGoal
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.models.program import Program
from app.models.university import University
from app.models.user import User
from app.prompts._locale import glossary_block
from app.services import (
    assessment_shared,
    llm_client,
    motivation_service,
    report_service,
    university_service,
)
from app.services.report_narrative_validator import _check_language_kk

_CONFIG = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "i18n_guard_config.json").read_text("utf-8")
)
_RAW_KEYS = set(_CONFIG["always_raw_fields"]["keys"])
_TEMP_KEYS = set(_CONFIG["catalog_temp_allowlist"]["keys"])
_RU_WORDS = set(_CONFIG["ru_marker_words"]["words"])
_ENT_RU = _CONFIG["ent_terms"]["ru"]
_ENT_KK = _CONFIG["ent_terms"]["kk"]

_KK_CHARS = set("әғқңөұүһі")
_WORD_RE = __import__("re").compile(r"[а-яёұүөқғңһәі]+", __import__("re").IGNORECASE)


def _ru_marker_hits(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w in _RU_WORDS}


# ── report narrative ─────────────────────────────────────────────────────────

async def _kk_senior_report(db: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x",
                is_active=True, is_verified=True, locale="kk")
    db.add(user)
    await db.flush()
    profile = Profile(user_id=user.id, name="Тест", age=16, grade=9, city="Алматы",
                      country="Қазақстан", language="қазақша", age_group=AgeGroup.senior)
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()

    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)

    return await report_service.build_report(assessment.id, db)


async def test_kk_report_narrative_has_no_russian_leak(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    resp = await _kk_senior_report(db_session, monkeypatch)

    texts = [
        resp.summary, resp.final_analysis, resp.interest_map_note,
        resp.personality_note,
        *(c.description for c in resp.strength_cards),
        *(n.description for n in resp.thinking_style_notes),
        *(getattr(c, "why", "") for c in getattr(resp, "careers", []) or []),
    ]
    texts = [t for t in texts if t]

    # same heuristic the runtime validator enforces — zero issues = fully kk
    assert _check_language_kk(texts) == [], "Russian leak in kk report narrative"


# ── catalog ──────────────────────────────────────────────────────────────────

async def _kk_program_detail(db: AsyncSession):
    # ru base columns carry Russian; the kk overlay is what a kk request must
    # get back. After KZ-505 there is no temp allowlist, so every free-text
    # field the response exposes has to resolve to Kazakh.
    uni = University(name="Тест Университеті", country="Қазақстан", city="Алматы",
                     description="Русское описание вуза",
                     description_i18n={"kk": "Университеттің қазақ тіліндегі сипаттамасы."})
    db.add(uni)
    direction = Direction(name="Бағыт", slug="guard-kz602", holland_code="RIA")
    db.add(direction)
    await db.flush()
    program = Program(university_id=uni.id, name="Информатика (бакалавр)", language="қазақша",
                      description="Русское описание программы",
                      description_i18n={"kk": "Бағдарламаның қазақ тіліндегі сипаттамасы."},
                      who_its_for="Русский «для кого»",
                      who_its_for_i18n={"kk": "Бұл бағдарлама нақты ғылымдарды ұнататындарға арналған."},
                      requirements={"exams": ["ҰБТ", "Математика"], "needs_essay": True},
                      deadlines={}, grants=[])
    program.directions = [direction]
    db.add(program)
    await db.flush()
    return await university_service.get_program_detail(db, program.id, locale="kk")


def _walk_strings(node, key=None):
    if isinstance(node, str):
        yield key, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, k)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _walk_strings(v, key)


async def test_kk_program_detail_has_no_russian_leak_outside_allowlist(
    db_session: AsyncSession
) -> None:
    detail = await _kk_program_detail(db_session)
    payload = detail.model_dump()

    offenders: list[tuple[str | None, str, set[str]]] = []
    for key, text in _walk_strings(payload):
        if key in _RAW_KEYS or key in _TEMP_KEYS:
            continue
        hits = _ru_marker_hits(text)
        if hits:
            offenders.append((key, text, hits))

    assert not offenders, f"Russian leak in kk catalog response: {offenders}"


# ── ЕНТ / ҰБТ do not cross locales ──────────────────────────────────────────

def test_ent_and_ubt_do_not_mix_within_a_locale() -> None:
    ru = tr("subjects", locale="ru")["admission_terms"]
    kk = tr("subjects", locale="kk")["admission_terms"]
    assert all(_ENT_KK not in v for v in ru.values()), "ҰБТ leaked into ru admission terms"
    assert all(_ENT_RU not in v for v in kk.values()), "ЕНТ leaked into kk admission terms"

    for area in ("university_requirements", "gap_analysis"):
        kk_tree = json.dumps(tr(area, locale="kk"), ensure_ascii=False)
        ru_tree = json.dumps(tr(area, locale="ru"), ensure_ascii=False)
        assert _ENT_RU not in kk_tree, f"ЕНТ in kk catalog area {area}"
        assert _ENT_KK not in ru_tree, f"ҰБТ in ru catalog area {area}"

    # the kk AI-prompt glossary rule reads "«ЕНТ» орнына «ҰБТ»": ЕНТ appears
    # once as the *source* term being replaced — that's expected. What must
    # not happen is the ru prompt carrying kk terms.
    assert glossary_block("ru") == ""
    assert _ENT_KK in glossary_block("kk")


# ── the allowlist itself ────────────────────────────────────────────────────

def test_guard_config_temp_allowlist_is_only_kz504_pending_fields() -> None:
    # KZ-504/505 are done — every university/program description has a
    # native-reviewed kk translation — so the temp allowlist is now EMPTY and
    # must stay that way. A re-added key means a Russian leak is being hidden
    # instead of fixed.
    assert _TEMP_KEYS == set()
