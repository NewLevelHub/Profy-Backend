"""
Calibration tool — drives many synthetic Akinator sessions through the real
engine (start_session/submit_answer, no HTTP, no LLM) and prints aggregate
stats: average questions to reveal, single/cluster/ceiling split, per-axis-
family coverage, which questions actually get asked, and (for --strategy
target) whether the engine converges on the persona it was aimed at.

Commits for real, periodically (2026-07-29 — was one giant outer transaction
rolled back at the end, same SAVEPOINT trick as tests/conftest.py's
db_session fixture; changed because a full 57x100 census took 3+ hours,
traced to Postgres MVCC visibility-check cost growing with the size of a
single transaction — thousands of sessions inside ONE transaction, not a
DB-side bug). Every `db.commit()` already called throughout this script and
inside akinator_session_service (once per session start, once per answer)
is now a REAL commit instead of a savepoint release, so each simulated
session only pays visibility-check cost against its own small transaction.
Throwaway users/profiles are cleaned up (real DELETE, cascades to their
assessments/sessions) at the end of every run via `_cleanup_calibration_data`
— safe to interrupt mid-run too, since this is only ever pointed at the
isolated `profi-calib` stack, not a real dev/prod database.

Replaces the one-off `docker-compose exec api python -c "..."` snippets used
during the first calibration pass — same idea, just reusable and versioned.

Usage (inside Docker):
    docker-compose exec api python scripts/calibration_simulate.py
    docker-compose exec api python scripts/calibration_simulate.py --runs 300 --age senior
    docker-compose exec api python scripts/calibration_simulate.py --strategy target --runs 200
    # Full "confusion census": one textbook persona per real profession, N
    # trials each, reporting which ones don't reliably rank in the top-3:
    docker-compose exec api python scripts/calibration_simulate.py --census --runs 6 --age senior
"""
import argparse
import asyncio
import os
import random
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine
from app.models.akinator_question import AkinatorQuestion
from app.models.assessment import Assessment, AssessmentGoal
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import akinator_engine, akinator_session_service
from scripts.seed_akinator_content import SPECIALTIES, seed_questions, seed_sections, seed_specialties

STRATEGIES = ["random", "consistent", "alternating", "target"]
AGE_GROUPS = {"junior": AgeGroup.junior, "middle": AgeGroup.middle, "senior": AgeGroup.senior}


@dataclass
class RunResult:
    steps: int
    status: str
    reason: str | None
    families_touched: set[str]
    question_orders: list[int]
    revealed_slugs: list[str]
    final_belief: dict[str, float]
    target_slug: str | None = None


@dataclass
class Aggregate:
    step_counter: Counter = field(default_factory=Counter)
    status_counter: Counter = field(default_factory=Counter)
    reason_counter: Counter = field(default_factory=Counter)
    question_freq: Counter = field(default_factory=Counter)  # post-wide-start only
    full_family_coverage: int = 0
    target_hits: int = 0
    target_attempts: int = 0
    n: int = 0

    def add(self, result: RunResult) -> None:
        self.n += 1
        self.step_counter[result.steps] += 1
        self.status_counter[result.status] += 1
        self.reason_counter[result.reason] += 1
        for order in result.question_orders[3:]:  # skip the fixed wide-start
            self.question_freq[order] += 1
        if result.families_touched == {"A", "B", "C", "D", "E"}:
            self.full_family_coverage += 1
        if result.target_slug is not None:
            self.target_attempts += 1
            if result.target_slug in result.revealed_slugs:
                self.target_hits += 1

    def avg_steps(self) -> float:
        if self.n == 0:
            return 0.0
        return sum(k * v for k, v in self.step_counter.items()) / self.n

    def print_report(self, label: str, total_question_count: int) -> None:
        print(f"\n=== {label} (n={self.n}) ===")
        print(f"avg steps: {self.avg_steps():.2f}")
        print(f"steps distribution: {dict(sorted(self.step_counter.items()))}")
        print(f"status: {dict(self.status_counter)}")
        print(f"reason: {dict(self.reason_counter)}")
        print(f"axis-family coverage (all 5 touched before reveal): {self.full_family_coverage}/{self.n}")
        never_picked = total_question_count - len(self.question_freq)
        print(f"post-wide-start questions never picked: {never_picked}/{total_question_count}")
        if self.question_freq:
            least = self.question_freq.most_common()[-3:]
            most = self.question_freq.most_common(3)
            print(f"  least picked: {least}")
            print(f"  most picked:  {most}")
        if self.target_attempts:
            hit_rate = 100 * self.target_hits / self.target_attempts
            print(f"target-persona accuracy: {self.target_hits}/{self.target_attempts} ({hit_rate:.0f}%)")


def _pick_option(
    strategy: str, question: AkinatorQuestion, rng: random.Random, target_profile: dict | None
) -> int | None:
    """Returns an index into question.options, or None for "не знаю".

    None mirrors a real fact about the production system, not a simulation
    shortcut: the frontend always renders a "Затрудняюсь ответить / Не
    знаю" button for every single question (not conditional on the question
    having its own explicit neutral option), and submit_answer's docstring
    is explicit that option_index=None is "a real, recorded answer with
    zero axis contribution (identity update), not a skip" — for ANY
    question, not just ones the content happened to give a spare option to.
    A real user with no genuine stake in a question clicks that button.
    Earlier versions of this function tried to approximate this by hunting
    for an in-list option with empty axis_weights that ties the best score
    — but that only worked for the subset of questions that happened to
    have one, and produced a systematically different (worse) simulation
    of the off-topic-question experience than what real users actually do.
    Returning None directly whenever no option is a genuine positive match
    covers every question uniformly, exactly like the real frontend."""
    options = question.options
    if strategy == "random":
        return rng.randrange(len(options))
    if strategy == "consistent":
        return 0
    if strategy == "alternating":
        return 0 if question.depth % 2 == 0 else len(options) - 1
    if strategy == "target":
        scores = [
            akinator_engine.match_score(opt.get("axis_weights", {}), target_profile or {})
            for opt in options
        ]
        best = max(range(len(options)), key=lambda i: scores[i])
        if scores[best] <= 0:
            return None
        return best
    raise ValueError(f"unknown strategy: {strategy!r}")


async def _run_one(
    db: AsyncSession,
    age_group: AgeGroup,
    strategy: str,
    rng: random.Random,
    leaf_profiles_by_slug: dict[str, dict],
    forced_target_slug: str | None = None,
) -> RunResult:
    user = User(email=f"{uuid.uuid4()}@calibration.local", hashed_password="x")
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name="Calibration", age=15, grade=9, city="C", country="C",
        language="ru", age_group=age_group,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    await db.commit()

    if strategy == "target":
        target_slug = forced_target_slug or rng.choice(list(leaf_profiles_by_slug))
    else:
        target_slug = None
    target_profile = leaf_profiles_by_slug.get(target_slug) if target_slug else None

    turn = await akinator_session_service.start_session(assessment.id, age_group, db)
    question = turn.next_question
    orders: list[int] = []
    families: set[str] = set()
    steps = 0
    while question is not None:
        orders.append(question.order)
        families |= {f.value for f in akinator_engine.question_axis_families(question)}
        option_index = _pick_option(strategy, question, rng, target_profile)
        turn = await akinator_session_service.submit_answer(
            assessment.id, question.id, option_index, age_group, db
        )
        steps += 1
        question = turn.next_question

    return RunResult(
        steps=steps,
        status=turn.decision.status,
        reason=turn.decision.reason,
        families_touched=families,
        question_orders=orders,
        revealed_slugs=list(turn.decision.leaves),
        final_belief=turn.session.belief,
        target_slug=target_slug,
    )


def _rank(slug: str, belief: dict[str, float]) -> int:
    """1-based rank by belief, descending — 1 means it would have won outright."""
    ranked = sorted(belief.items(), key=lambda kv: -kv[1])
    return next(i for i, (s, _) in enumerate(ranked) if s == slug) + 1


async def run_census(
    db: AsyncSession,
    age_group: AgeGroup,
    trials_per_profession: int,
    rng: random.Random,
    leaf_profiles_by_slug: dict[str, dict],
    top_n: int,
    only_slugs: set[str] | None = None,
) -> None:
    """One "textbook" persona per real profession (skips the old placeholder
    "explore-*" directions, which carry no profile), run `trials_per_profession`
    times each. Reports, per profession, how often it lands in the top `top_n`
    by final belief — the bar for "would a real user plausibly see this
    suggested" — and what beats it when it doesn't.

    `only_slugs`, if given, restricts which professions get their OWN persona
    simulated (each is still scored against the full leaf catalog — this only
    cuts down how many of the 57 outer loops run, not what they compete
    against). Added 2026-07 once the catalog grew past 50 leaves and a full
    `--runs 100` census started taking 30-40 minutes even on an otherwise-idle
    stack (57 leaves x 100 trials = 5700 full simulated sessions through the
    real engine/DB, not a fast mock) — most iteration during a single fix
    only needs to recheck the profession just changed plus its named rivals,
    not all 57."""
    real_slugs = [p["slug"] for p in SPECIALTIES if p["slug"] in leaf_profiles_by_slug]
    if only_slugs:
        real_slugs = [s for s in real_slugs if s in only_slugs]
    rows: list[tuple[str, int, int, Counter]] = []

    # TEMPORARY progress logging (2026-07-28, remove once the "why is this so
    # slow" question is settled) — one line per profession with elapsed/ETA,
    # so a long full run shows visible progress instead of looking hung.
    import time as _time
    _t_start = _time.monotonic()
    for _slug_i, slug in enumerate(real_slugs):
        _t_slug_start = _time.monotonic()
        hits = 0
        beaten_by: Counter = Counter()
        for _ in range(trials_per_profession):
            result = await _run_one(
                db, age_group, "target", rng, leaf_profiles_by_slug, forced_target_slug=slug
            )
            belief = result.final_belief
            rank = _rank(slug, belief)
            if rank <= top_n:
                hits += 1
            else:
                top = [s for s, _ in sorted(belief.items(), key=lambda kv: -kv[1])[:top_n]]
                beaten_by.update(top)
        rows.append((slug, hits, trials_per_profession, beaten_by))
        _elapsed = _time.monotonic() - _t_start
        _per_slug = _elapsed / (_slug_i + 1)
        _eta = _per_slug * (len(real_slugs) - _slug_i - 1)
        print(
            f"[progress] {_slug_i + 1}/{len(real_slugs)} {slug}: "
            f"{_time.monotonic() - _t_slug_start:.1f}s this profession, "
            f"{_elapsed:.0f}s elapsed, ~{_eta:.0f}s remaining",
            file=sys.stderr,
        )

    rows.sort(key=lambda r: r[1] / r[2])  # worst hit-rate first
    print(f"\n=== profession census (top-{top_n}, {trials_per_profession} trials each, age={age_group.value}) ===")
    failing = 0
    for slug, hits, trials, beaten_by in rows:
        rate = hits / trials
        needs_a_look = rate < 0.5  # fails the majority of the time
        flag = "  <-- needs a look" if needs_a_look else ""
        if needs_a_look:
            failing += 1
        beaters = ", ".join(f"{s}x{c}" for s, c in beaten_by.most_common(3))
        print(f"  {slug:26s} {hits}/{trials} ({100*rate:3.0f}%){flag}" + (f"   often loses to: {beaters}" if beaters else ""))
    print(f"\n{failing}/{len(rows)} professions fail top-{top_n} more often than not ({trials_per_profession} trials each).")


async def _leaf_profiles_by_slug(db: AsyncSession) -> dict[str, dict]:
    result = await db.execute(select(Direction).where(Direction.is_leaf.is_(True)))
    return {d.slug: (d.profile or {}) for d in result.scalars().all() if d.profile}


async def _cleanup_calibration_data(db: AsyncSession) -> int:
    """Deletes every throwaway user this run created (matched by the fixed
    @calibration.local email domain _run_one always uses) and their
    profiles. Profile must go first — profiles.user_id -> users.id has NO
    ON DELETE CASCADE (only assessments.profile_id and
    assessment_sessions.assessment_id do), so deleting User first raises a
    ForeignKeyViolationError. Real DELETE + commit, since we're no longer
    relying on an outer rollback to erase this data. Returns how many
    users were deleted."""
    calibration_user_ids = (
        select(User.id).where(User.email.like("%@calibration.local"))
    )
    await db.execute(delete(Profile).where(Profile.user_id.in_(calibration_user_ids)))
    result = await db.execute(
        delete(User).where(User.email.like("%@calibration.local"))
    )
    await db.commit()
    return result.rowcount


async def main(
    runs: int, ages: list[str], strategies: list[str], seed: int,
    census: bool, census_top_n: int, census_only: set[str] | None = None,
) -> None:
    db = AsyncSession(engine, expire_on_commit=False)
    deleted = 0
    try:
        section_ids, *_ = await seed_sections(db)
        await seed_specialties(db, section_ids)
        await seed_questions(db)
        await db.commit()

        total_questions = (await db.execute(select(AkinatorQuestion))).scalars().all()
        total_question_count = len(total_questions)
        leaf_profiles_by_slug = await _leaf_profiles_by_slug(db)

        rng = random.Random(seed)

        if census:
            for age_key in ages:
                await run_census(
                    db, AGE_GROUPS[age_key], runs, rng, leaf_profiles_by_slug, census_top_n,
                    only_slugs=census_only,
                )
        else:
            for age_key in ages:
                age_group = AGE_GROUPS[age_key]
                for strategy in strategies:
                    agg = Aggregate()
                    for _ in range(runs):
                        result = await _run_one(db, age_group, strategy, rng, leaf_profiles_by_slug)
                        agg.add(result)
                    agg.print_report(f"age={age_key} strategy={strategy}", total_question_count)
    finally:
        deleted = await _cleanup_calibration_data(db)
        await db.close()

    print(f"\nDone. Committed as real (periodic) transactions — cleaned up {deleted} "
          f"calibration user(s)/profile(s)/session(s) at the end.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Calibration simulator — runs many synthetic Akinator sessions through "
            "the real engine and reports average length, question-selection spread, "
            "and (for --strategy target) whether it converges on the intended "
            "profession. Nothing is written to the database (rolled back at the end)."
        )
    )
    parser.add_argument("--runs", type=int, default=100, help="sessions per (age, strategy) combo")
    parser.add_argument(
        "--age", choices=[*AGE_GROUPS, "all"], default="all", help="age group(s) to simulate"
    )
    parser.add_argument(
        "--strategy", choices=[*STRATEGIES, "all"], default="all",
        help="random=uniform picks, consistent=always first option, "
             "alternating=flip-flops, target=greedily answers toward a random real profession",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed, for reproducible runs")
    parser.add_argument(
        "--census", action="store_true",
        help="instead of --strategy, run a 'textbook' persona for EVERY real profession "
             "(--runs becomes trials per profession) and report which ones don't reliably "
             "land in the top --census-top-n by final belief, and what beats them",
    )
    parser.add_argument(
        "--census-top-n", type=int, default=3,
        help="with --census: how many top-belief slots count as 'a real user would plausibly see this'",
    )
    parser.add_argument(
        "--census-only", type=str, default=None,
        help="with --census: comma-separated leaf slugs to simulate a persona for, instead of all "
             "57 (e.g. --census-only project-management,international-relations,lawyer). Every "
             "candidate leaf is still fully scored/competed against on every question — this only "
             "cuts how many OUTER personas run, for fast iteration on a specific fix. Full runs "
             "without this flag are still needed before calling a fix verified.",
    )
    args = parser.parse_args()

    resolved_ages = list(AGE_GROUPS) if args.age == "all" else [args.age]
    resolved_strategies = STRATEGIES if args.strategy == "all" else [args.strategy]
    resolved_census_only = (
        {s.strip() for s in args.census_only.split(",") if s.strip()} if args.census_only else None
    )

    asyncio.run(main(
        args.runs, resolved_ages, resolved_strategies, args.seed,
        args.census, args.census_top_n, resolved_census_only,
    ))
