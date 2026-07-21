"""
Calibration tool — drives many synthetic Akinator sessions through the real
engine (start_session/submit_answer, no HTTP, no LLM) and prints aggregate
stats: average questions to reveal, single/cluster/ceiling split, per-axis-
family coverage, which questions actually get asked, and (for --strategy
target) whether the engine converges on the persona it was aimed at.

Everything runs inside one outer transaction that's ALWAYS rolled back at the
end (same SAVEPOINT trick as tests/conftest.py's db_session fixture) — no
throwaway users/profiles/sessions are ever left in the dev database, however
many runs you ask for.

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

from sqlalchemy import select
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


def _pick_option(strategy: str, question: AkinatorQuestion, rng: random.Random, target_profile: dict | None) -> int:
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
        # A tie at the top (frequently 0-0-0 when the question is simply
        # irrelevant to this persona's axes) used to default to option 0
        # regardless of what it actually says — silently dragging belief
        # toward whichever *other* profession that option happens to favor.
        # Prefer a genuinely neutral option ("и то и другое поровну", empty
        # axis_weights) when one's available and ties the best real score.
        if scores[best] <= 0:
            neutral = next((i for i, opt in enumerate(options) if not opt.get("axis_weights")), None)
            if neutral is not None and scores[neutral] == scores[best]:
                return neutral
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
) -> None:
    """One "textbook" persona per real profession (skips the old placeholder
    "explore-*" directions, which carry no profile), run `trials_per_profession`
    times each. Reports, per profession, how often it lands in the top `top_n`
    by final belief — the bar for "would a real user plausibly see this
    suggested" — and what beats it when it doesn't."""
    real_slugs = [p["slug"] for p in SPECIALTIES if p["slug"] in leaf_profiles_by_slug]
    rows: list[tuple[str, int, int, Counter]] = []

    for slug in real_slugs:
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


async def main(
    runs: int, ages: list[str], strategies: list[str], seed: int,
    census: bool, census_top_n: int,
) -> None:
    async with engine.connect() as conn:
        outer_trans = await conn.begin()
        db = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
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
                        db, AGE_GROUPS[age_key], runs, rng, leaf_profiles_by_slug, census_top_n
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
            await db.close()
            await outer_trans.rollback()

    print("\nDone. Rolled back — nothing was persisted to the database.")


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
    args = parser.parse_args()

    resolved_ages = list(AGE_GROUPS) if args.age == "all" else [args.age]
    resolved_strategies = STRATEGIES if args.strategy == "all" else [args.strategy]

    asyncio.run(main(
        args.runs, resolved_ages, resolved_strategies, args.seed,
        args.census, args.census_top_n,
    ))
