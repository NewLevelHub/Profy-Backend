import logging
import uuid
from datetime import datetime, timezone
from enum import Enum

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import AppError
from app.i18n import DEFAULT_LOCALE, KNOWN_LOCALES, use_locale
from app.models.analysis_result import AnalysisResult
from app.models.artifact import Artifact
from app.models.assessment import Assessment, AssessmentStatus
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.schemas.report_narrative import ReportNarrativeOutput
from app.schemas.result_v2 import (
    MiResultResponse,
    ResultResponseV2,
    ResultV2Adapter,
    RiasecResultResponse,
    StudentStrengthCard,
    StudentThinkingStyleNote,
)
from app.services import (
    assessment_shared,
    bigfive_content,
    bigfive_service,
    mi_service,
    motivation_pair_service,
    motivation_service,
    report_narrative_context,
    report_v2_assembler,
    riasec_service,
    thinking_style_service,
)
from app.services.bigfive_content import strength_phrases
from app.services.motivation_content import highlight_phrases as motivation_highlight_phrases
from app.services.report_narrative_service import (
    generate_report_narrative,
    translate_report_narrative,
)

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24  # 24 hours

# The owner-locale pointer (`_resolve_owner_locale`) is a cheap 2-join query to
# recompute, and its invalidation on retake / PATCH /auth/me is best-effort
# (`safe_redis_delete` swallows RedisError). A short TTL bounds how long a
# silently-missed delete can keep `/result` pointed at the previous language —
# instead of the full 24h report TTL — while still being long enough that the
# ~2s GET /result poll during generation is served entirely from cache.
OWNER_LOCALE_CACHE_TTL = 60 * 5  # 5 minutes

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


# Cache key itself lives in assessment_shared (report_cache_key) so the one
# place that invalidates it on retake (invalidate_retake) can never drift
# from the key this module reads/writes.
_cache_key = assessment_shared.report_cache_key


async def _cache_get(redis: aioredis.Redis, key: str) -> str | None:
    """Redis is an accelerator for the DB-backed report, never its source of
    truth — an outage here must fall through to the DB path, not surface as
    a 500 for a report that's actually available."""
    try:
        return await redis.get(key)
    except aioredis.RedisError:
        logger.warning("redis get failed for key=%s — falling back to DB", key, exc_info=True)
        return None


async def _cache_set(
    redis: aioredis.Redis, key: str, value: str, *, ttl: int = CACHE_TTL
) -> None:
    try:
        await redis.setex(key, ttl, value)
    except aioredis.RedisError:
        logger.warning("redis set failed for key=%s — response served without caching", key, exc_info=True)


async def _cache_get_response(redis: aioredis.Redis, key: str) -> ResultResponseV2 | None:
    """Wraps _cache_get with shape validation: a cache entry written before
    a schema change (a new required field, e.g. personality_notes) can't
    deserialize into the current ResultV2Schema. Redis is an accelerator,
    never the source of truth, so this must degrade the exact same way a
    connection failure does — fall through to the DB path (which rebuilds a
    fully current response and overwrites the stale entry) rather than
    surface a 500 for a report that's actually available."""
    cached = await _cache_get(redis, key)
    if not cached:
        return None
    try:
        return ResultV2Adapter.validate_json(cached)
    except ValidationError:
        logger.warning("cached payload for key=%s no longer matches the schema — falling back to DB", key)
        return None


def _career_dict(direction: Direction, match_score: int) -> dict:
    return {
        "slug": direction.slug,
        "name": direction.name,
        "holland_code": direction.holland_code,
        "match_score": match_score,
        "description": direction.description or "",
        "professions": list(direction.professions or []),
        "skills_needed": list(direction.skills_needed or []),
        "subjects_to_develop": list(direction.subjects_to_develop or []),
        "first_steps": list(direction.first_steps or []),
    }


async def _find_primary_analysis(
    assessment_id: uuid.UUID, db: AsyncSession, *, exclude_locale: str
) -> AnalysisResult | None:
    """An already-generated report for this assessment in a *different*
    locale, to translate from instead of generating a second one from
    scratch. Prefers the `ru` row (source of truth), then the earliest
    generated."""
    rows = (
        await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
        )
    ).scalars().all()
    others = [r for r in rows if r.locale != exclude_locale and r.summary]
    if not others:
        return None
    others.sort(key=lambda r: (r.locale != DEFAULT_LOCALE, r.created_at))
    return others[0]


async def _build_narrative(
    *,
    assessment_id: uuid.UUID,
    db: AsyncSession,
    age_group: AgeGroup,
    strengths: list[str],
    personality_profile: dict[str, float],
    personality_notes: dict[str, str],
    thinking_style: dict[str, float],
    motivation_top: list[str],
    motivation_highlights: list[str],
    profile: Profile | None,
    artifacts: list[Artifact],
    locale: str = DEFAULT_LOCALE,
) -> tuple[report_narrative_context.ReportNarrativeContext, ReportNarrativeOutput]:
    """Produces everything text-shaped (summary, strength_cards,
    thinking_style_notes, final_analysis) for this locale.

    If a report already exists in another locale, that one's narrative is
    *translated* into this locale with a single LLM call — so a `ru` and a
    `kk` report say the same thing, not two independently generated takes.
    Only the first-ever locale is generated from scratch. Either path ends
    in a deterministic fallback (never raises, never leaves a field empty)."""
    # Caller runs this whole block under i18n.use_locale(locale) so the
    # KZ-307 accessors inside the context builder and the deterministic
    # fallback resolve to the artifact owner's language. The AI prompt still
    # gets `language=locale` explicitly.
    context = report_narrative_context.build_report_narrative_context(
        age_group=age_group,
        strengths=strengths,
        personality_profile=personality_profile,
        personality_notes=personality_notes,
        thinking_style=thinking_style,
        motivation_top=motivation_top,
        motivation_highlights=motivation_highlights,
        subjects_liked=list(profile.subjects_liked or []) if profile else [],
        subjects_easy=list(profile.subjects_easy or []) if profile else [],
        artifacts=artifacts,
    )

    primary = await _find_primary_analysis(assessment_id, db, exclude_locale=locale)
    if primary is not None:
        narrative, is_ai = await translate_report_narrative(
            context,
            source={
                "summary": primary.summary,
                "final_analysis": primary.final_analysis,
                "strength_cards": [dict(c) for c in (primary.strength_cards or [])],
                "thinking_style_notes": [dict(n) for n in (primary.thinking_style_notes or [])],
            },
            source_locale=primary.locale,
            target_locale=locale,
        )
        logger.info(
            "report_narrative translated from=%s to=%s is_ai=%s age_group=%s",
            primary.locale, locale, is_ai, age_group.value,
        )
        return context, narrative

    narrative, is_ai = await generate_report_narrative(context, language=locale)
    logger.info(
        "report_narrative generated is_ai=%s age_group=%s locale=%s",
        is_ai, age_group.value, locale,
    )
    return context, narrative


async def _acquire_generation_lock(assessment_id: uuid.UUID, db: AsyncSession) -> None:
    """Transaction-scoped Postgres advisory lock keyed on assessment_id —
    serializes the "check DB, then generate" section of build_report()
    across concurrent requests for the *same* assessment, so a second
    concurrent POST /result/generate never runs its own LLM call/scoring
    pass in parallel with the first, only to have it discarded on
    IntegrityError. `pg_advisory_xact_lock` auto-releases when the
    transaction ends (commit or rollback) — no manual unlock, so it can
    never leak even if generation raises or the connection drops.
    `hashtext()` collapses the UUID to the bigint the lock function wants;
    a hash collision with an unrelated assessment_id would only ever cause
    extra (harmless) serialization, never a correctness bug — the re-check
    after acquiring the lock is what actually prevents a duplicate insert."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(assessment_id)})


def _stored_interest_instrument(profile: dict) -> str:
    """riasec_service.HOLLAND_ORDER keys are single uppercase letters, MI
    keys are lowercase words — unambiguous either way, so a stored row's
    own `profile` dict is enough to tell the two apart without also having
    to persist age_group on AnalysisResult."""
    return "riasec" if any(key in riasec_service.HOLLAND_ORDER for key in profile) else "mi"


async def _resolve_owner_locale(
    assessment_id: uuid.UUID, db: AsyncSession, redis: aioredis.Redis
) -> str:
    """The report renders in the *artifact owner's* language (`users.locale`),
    never the locale of whoever opened `/results` — an admin on `ru` must
    still see a `kk` student's report in `kk`. `kk` isn't a SUPPORTED_LOCALES
    value pre-KZ-603, so it's read straight off the row (KNOWN_LOCALES-gated)
    and applied through `i18n.use_locale`, not the request-locale machinery.

    Cached in Redis (`owner_locale_cache_key`, short `OWNER_LOCALE_CACHE_TTL`):
    the value changes only on retake or `PATCH /auth/me`, both of which delete
    this key, so the hot `GET /result` poll path avoids a 2-join query before
    every cache hit. The TTL is short (not the report's 24h) because that
    delete is best-effort — a silently-missed one must not pin the wrong
    language for a day.
    """
    loc_key = assessment_shared.owner_locale_cache_key(assessment_id)
    cached = await _cache_get(redis, loc_key)
    if cached in KNOWN_LOCALES:
        return cached

    owner_locale = (
        await db.execute(
            select(User.locale)
            .select_from(Assessment)
            .join(Profile, Profile.id == Assessment.profile_id)
            .join(User, User.id == Profile.user_id)
            .where(Assessment.id == assessment_id)
        )
    ).scalar_one_or_none()
    resolved = owner_locale if owner_locale in KNOWN_LOCALES else DEFAULT_LOCALE
    await _cache_set(redis, loc_key, resolved, ttl=OWNER_LOCALE_CACHE_TTL)
    return resolved


def _shape_response(analysis: AnalysisResult, *, locale: str = DEFAULT_LOCALE) -> ResultResponseV2:
    """Rebuilds the v2 shape from an already-generated, already-stored row —
    no LLM call, no re-generation. `strength_cards`/`thinking_style_notes`
    are read back verbatim (already the final {title, description} shape,
    migration 0041); `careers`/`interest_map`/`is_flat_profile`/
    `exploration_activities` are recomputed from the other stored raw
    fields via report_v2_assembler — the same functions generation uses,
    just fed from storage instead of a fresh context. Those recompute
    label/synthesis text, so the whole rebuild runs under the owner's
    locale (KZ-403)."""
    with use_locale(locale):
        return _shape_response_inner(analysis)


def _shape_response_inner(analysis: AnalysisResult) -> ResultResponseV2:
    instrument = _stored_interest_instrument(analysis.profile)
    effective_age_group = AgeGroup.junior if instrument == "mi" else AgeGroup.senior
    minimal_context = report_narrative_context.build_report_narrative_context(
        age_group=effective_age_group,
        strengths=list(analysis.strengths),
        personality_profile={}, personality_notes={}, thinking_style={},
        motivation_top=[], motivation_highlights=[],
        subjects_liked=[], subjects_easy=[], artifacts=[],
    )
    differentiation = float((analysis.meta or {}).get("differentiation", 0.0))
    flat = report_v2_assembler.is_flat_profile(differentiation)
    interest_map = report_v2_assembler.build_interest_map(effective_age_group, dict(analysis.profile))

    common = dict(
        assessment_id=analysis.assessment_id,
        summary=analysis.summary,
        # Server-authored framing lines resolved for the owner's locale — the
        # schema default is ru-only (KZ-403). Runs inside use_locale() above.
        **report_v2_assembler.build_fixed_framings(),
        strength_cards=[StudentStrengthCard.model_validate(c) for c in analysis.strength_cards],
        interest_map=interest_map,
        interest_map_note=report_v2_assembler.build_interest_map_note(interest_map),
        thinking_style_notes=[StudentThinkingStyleNote.model_validate(n) for n in analysis.thinking_style_notes],
        # personality_profile is stored on every row regardless of
        # interest_instrument (Big Five doesn't branch by age) — read back
        # directly, no need to recompute or route through minimal_context.
        personality_notes=report_v2_assembler.build_personality_notes(
            instrument == "mi", dict(analysis.personality_profile)
        ),
        personality_note=report_v2_assembler.build_personality_note(dict(analysis.personality_profile)),
        motivation_highlights=list(analysis.motivation_highlights),
        final_analysis=analysis.final_analysis,
        is_flat_profile=flat,
        created_at=analysis.created_at,
    )

    if instrument == "mi":
        return MiResultResponse(
            **common,
            exploration_activities=report_v2_assembler.build_exploration_activities(minimal_context),
        )

    return RiasecResultResponse(
        **common,
        careers=report_v2_assembler.build_riasec_careers(minimal_context, list(analysis.careers)),
    )


async def _assert_assessment_complete(
    assessment_id: uuid.UUID, age_group: AgeGroup, db: AsyncSession
) -> None:
    """Server-side re-check, independent of whatever `completed` flag a
    client last saw from /assessment/answers or /assessment/motivation —
    each of those only ever confirms its own phase, not the whole test.
    Required counts are age-specific since the MI/Harter merge: junior's
    Likert total is MI + Big Five with the retired RIASEC rows excluded
    (assessment_shared.likert_total_questions already does this), middle
    and senior are RIASEC + Big Five (question pairs land in the same
    Question/UserResponse tables, so no separate count is needed for them).
    Motivation is Harter pairs for junior/middle, MOST/LEAST triplets for
    senior — different tables, so the right counter has to be picked here."""
    likert_answered = await assessment_shared.likert_answered_count(assessment_id, db)
    likert_total = await assessment_shared.likert_total_questions(db, age_group)
    likert_done = likert_total > 0 and likert_answered >= likert_total

    if age_group == AgeGroup.senior:
        mot_answered = await motivation_service.answered_count(assessment_id, db)
        mot_total = await motivation_service.total_triplets(db)
    else:
        mot_answered = await motivation_pair_service.answered_count(assessment_id, db)
        mot_total = await motivation_pair_service.total_pairs(db)
    mot_done = mot_total > 0 and mot_answered >= mot_total

    if not (likert_done and mot_done):
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            error_code="assessment_not_completed",
            detail="Тест ещё не завершён — сначала ответь на все обязательные вопросы",
        )


async def build_report(
    assessment_id: uuid.UUID, db: AsyncSession
) -> ResultResponseV2:
    redis = _get_redis()
    locale = await _resolve_owner_locale(assessment_id, db, redis)
    cache_key = _cache_key(assessment_id, locale)

    cached_response = await _cache_get_response(redis, cache_key)
    if cached_response is not None:
        return cached_response

    existing_result = await db.execute(
        select(AnalysisResult).where(
            AnalysisResult.assessment_id == assessment_id,
            AnalysisResult.locale == locale,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        response = _shape_response(existing, locale=locale)
        await _cache_set(redis, cache_key, response.model_dump_json())
        return response

    # No result yet — but a concurrent request for this same assessment_id
    # might already be generating one. Block here (real DB-level wait, not
    # busy-polling) until any such request's transaction finishes, then
    # re-check: if it landed a row while we waited, read that instead of
    # independently repeating the scoring pass + LLM call below. This is
    # what actually stops duplicate generation work — the IntegrityError
    # handler further down is only a defense-in-depth backstop now, not the
    # primary mechanism.
    await _acquire_generation_lock(assessment_id, db)
    existing_result = await db.execute(
        select(AnalysisResult).where(
            AnalysisResult.assessment_id == assessment_id,
            AnalysisResult.locale == locale,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        response = _shape_response(existing, locale=locale)
        await _cache_set(redis, cache_key, response.model_dump_json())
        return response

    assessment_result = await db.execute(
        select(Assessment).where(Assessment.id == assessment_id)
    )
    assessment = assessment_result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found"
        )

    profile_result = await db.execute(
        select(Profile).where(Profile.id == assessment.profile_id)
    )
    profile = profile_result.scalar_one_or_none()
    age_group = profile.age_group if profile is not None else AgeGroup.senior

    # Gate before any write: an incomplete assessment must not flip to
    # `completed` and must not get a partial AnalysisResult.
    await _assert_assessment_complete(assessment_id, age_group, db)

    artifacts_result = await db.execute(
        select(Artifact).where(Artifact.profile_id == assessment.profile_id)
    )
    artifacts = list(artifacts_result.scalars().all())

    # The whole scoring -> deterministic-text -> assemble pass renders in the
    # artifact owner's language: development_plan, matched_careers,
    # strength_phrases, the narrative (LLM or fallback) and assemble_result_v2
    # all read get_locale() through the KZ-307 accessors. `kk` isn't a
    # SUPPORTED_LOCALES value pre-KZ-603 so use_locale (KNOWN_LOCALES-gated)
    # is what carries it, not set_locale. (KZ-401/KZ-403.)
    with use_locale(locale):
        if age_group == AgeGroup.junior:
            # Junior (6-9) is not career-oriented (TZ_Profi.md §4.1) — RIASEC and
            # its career matching are replaced with an MI-style "what to try"
            # instrument. Big Five stays unchanged below for personality/thinking_style.
            raw = await mi_service.raw_scores(assessment_id, db, age_group)
            counts = await mi_service.question_counts(db, age_group)
            profile_scores = mi_service.normalize(raw, counts)
            aversion_counts = await mi_service.aversion(assessment_id, db, age_group)

            code = mi_service.top_code(profile_scores)
            meta = {
                "differentiation": mi_service.differentiation(profile_scores),
                "consistency": mi_service.consistency(profile_scores),
                "aversion": aversion_counts,
            }
            strengths, weaknesses = mi_service.strengths_weaknesses(profile_scores, aversion_counts, counts)
            plan = mi_service.development_plan(code, weaknesses, aversion_counts, counts)
            careers: list[dict] = []
        else:
            raw = await riasec_service.raw_scores(assessment_id, db, age_group)
            counts = await riasec_service.question_counts(db, age_group)
            profile_scores = riasec_service.normalize(raw, counts)
            aversion_counts = await riasec_service.aversion(assessment_id, db, age_group)

            code = riasec_service.top_code(profile_scores)
            meta = {
                "differentiation": riasec_service.differentiation(profile_scores),
                "consistency": riasec_service.consistency(code[:2]),
                "aversion": aversion_counts,
            }
            strengths, weaknesses = riasec_service.strengths_weaknesses(profile_scores, aversion_counts, counts)
            plan = riasec_service.development_plan(code, weaknesses, aversion_counts, counts)

            matched = await riasec_service.matched_careers(code, db)
            careers = [_career_dict(d, score) for d, score in matched]

        # grand_mean is the same query for both raw_scores() and facet_raw() below
        # (same assessment_id/age_group) — fetch it once here instead of each
        # function independently re-running it.
        bf_mean_answer = await bigfive_service.grand_mean(assessment_id, db, age_group)

        bf_raw = await bigfive_service.raw_scores(assessment_id, db, age_group, mean_answer=bf_mean_answer)
        bf_counts = await bigfive_service.question_counts(db, age_group)
        bigfive_scores = bigfive_service.normalize(bf_raw, bf_counts)

        bf_facet_raw = await bigfive_service.facet_raw(assessment_id, db, age_group, mean_answer=bf_mean_answer)
        bf_facet_counts = await bigfive_service.facet_counts(db, age_group)
        bf_facet_norm = bigfive_service.facet_normalize(bf_facet_raw, bf_facet_counts)
        thinking_style = thinking_style_service.compute(bf_facet_norm)

        personality_profile, personality_notes = bigfive_content.build_personality_profile(bigfive_scores)
        personality_highlights = strength_phrases(personality_profile)

        # Junior/middle answer the Harter-format pairs instead of the 3-way
        # MOST/LEAST triplets (senior) — different tables/scoring, same shape.
        if age_group in (AgeGroup.junior, AgeGroup.middle):
            mot_scores = await motivation_pair_service.raw_scores(assessment_id, db)
        else:
            mot_scores = await motivation_service.raw_scores(assessment_id, db)
        mot_top = motivation_service.top_categories(mot_scores)
        mot_highlights = motivation_highlight_phrases(mot_top)

        # One narrative call feeds summary + strength_cards + thinking_style_notes
        # together (LLM when enabled and valid, deterministic fallback otherwise
        # — report_narrative_service never raises and never leaves any of the
        # three empty/inconsistent with each other).
        context, narrative = await _build_narrative(
            assessment_id=assessment_id,
            db=db,
            age_group=age_group,
            strengths=strengths,
            personality_profile=personality_profile,
            personality_notes=personality_notes,
            thinking_style=thinking_style,
            motivation_top=mot_top,
            motivation_highlights=mot_highlights,
            profile=profile,
            artifacts=artifacts,
            locale=locale,
        )
        strength_cards_stored = [card.model_dump(exclude={"evidence_ids"}) for card in narrative.strength_cards]
        thinking_style_notes_stored = [
            note.model_dump(exclude={"evidence_ids"}) for note in narrative.thinking_style_notes
        ]

        analysis = AnalysisResult(
            assessment_id=assessment_id,
            locale=locale,
            summary=narrative.summary,
            profile=profile_scores,
            code=code,
            meta=meta,
            careers=careers,
            strengths=strengths,
            weaknesses=weaknesses,
            development_plan=plan,
            big_five=bigfive_scores,
            thinking_style=thinking_style,
            personality_highlights=personality_highlights,
            personality_profile=personality_profile,
            personality_notes=personality_notes,
            motivation=mot_scores,
            motivation_top=mot_top,
            motivation_highlights=mot_highlights,
            strength_cards=strength_cards_stored,
            thinking_style_notes=thinking_style_notes_stored,
            final_analysis=narrative.final_analysis,
            report_version=2,
        )
        db.add(analysis)
        if assessment.status != AssessmentStatus.completed:
            # Same transaction as the AnalysisResult insert below — either both
            # land or neither does, so a completed-without-a-report assessment
            # can no longer exist.
            assessment.status = AssessmentStatus.completed
            assessment.completed_at = datetime.now(timezone.utc)
        try:
            await db.commit()
            await db.refresh(analysis)
        except IntegrityError:
            await db.rollback()
            existing_result = await db.execute(
                select(AnalysisResult).where(
                    AnalysisResult.assessment_id == assessment_id,
                    AnalysisResult.locale == locale,
                )
            )
            analysis = existing_result.scalar_one()
            response = _shape_response(analysis, locale=locale)
            await _cache_set(redis, cache_key, response.model_dump_json())
            return response

        response = report_v2_assembler.assemble_result_v2(
            assessment_id=assessment_id,
            age_group=age_group,
            context=context,
            narrative=narrative,
            profile_scores=profile_scores,
            personality_profile=personality_profile,
            differentiation=meta["differentiation"],
            careers=careers,
            created_at=analysis.created_at,
        )
    await _cache_set(redis, cache_key, response.model_dump_json())
    return response


class ReportLookup(str, Enum):
    """Outcome of a `/result` read (KZ-406), resolved from a single query."""

    OK = "ok"
    # A report exists, but only in a locale other than the owner's current one
    # — the "switched language, needs lazy regeneration" case.
    LOCALE_NOT_GENERATED = "locale_not_generated"
    NOT_FOUND = "not_found"


async def resolve_report(
    assessment_id: uuid.UUID, db: AsyncSession
) -> tuple[ResultResponseV2 | None, ReportLookup]:
    """`/result` read with a 3-state outcome: the owner-locale report, or a
    signal distinguishing "a report exists only in another locale" (KZ-406
    lazy regen) from "no report at all". Both cases are derived from one
    query, so the ~2s GET /result poll during generation never runs a second
    near-duplicate SELECT on top of it."""
    redis = _get_redis()
    locale = await _resolve_owner_locale(assessment_id, db, redis)
    cache_key = _cache_key(assessment_id, locale)

    cached_response = await _cache_get_response(redis, cache_key)
    if cached_response is not None:
        return cached_response, ReportLookup.OK

    # No locale filter: an assessment has at most len(KNOWN_LOCALES) rows, so
    # this costs the same as the old locale-filtered SELECT but also reveals
    # whether a *different* locale's report exists — without a second query.
    rows = (
        await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
        )
    ).scalars().all()
    if not rows:
        return None, ReportLookup.NOT_FOUND

    analysis = next((row for row in rows if row.locale == locale), None)
    if analysis is None:
        # A report exists, just not for the owner's current locale — KZ-406
        # will lazily (re)generate it. Do NOT fall back to another locale's row.
        return None, ReportLookup.LOCALE_NOT_GENERATED

    response = _shape_response(analysis, locale=locale)
    await _cache_set(redis, cache_key, response.model_dump_json())
    return response, ReportLookup.OK


async def get_report(
    assessment_id: uuid.UUID, db: AsyncSession
) -> ResultResponseV2 | None:
    """The owner-locale report, or None when there is none for that locale
    (whether or not one exists in another locale). Callers that must tell
    those two apart use `resolve_report`."""
    response, _ = await resolve_report(assessment_id, db)
    return response


async def invalidate_owner_locale_cache(user_id: uuid.UUID, db: AsyncSession) -> None:
    """Drop the cached owner-locale pointer (and the per-locale report cache
    entries) for every assessment this user owns. Called from `PATCH /auth/me`
    when `users.locale` changes: the report itself is keyed per-locale so a
    switch never *serves* the wrong language, but `_resolve_owner_locale`'s
    Redis cache would otherwise keep pointing `/result` at the old locale's
    key until it expired."""
    rows = await db.execute(
        select(Assessment.id)
        .join(Profile, Profile.id == Assessment.profile_id)
        .where(Profile.user_id == user_id)
    )
    redis = _get_redis()
    keys = [k for aid in rows.scalars().all() for k in assessment_shared.report_cache_keys(aid)]
    if keys:
        await assessment_shared.safe_redis_delete(redis, *keys)
