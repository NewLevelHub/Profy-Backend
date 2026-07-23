# Akinator calibration — backlog and methodology (2026-07)

Working notes from an extended calibration/playtest session on the senior-age
akinator engine. Goal: find where the test can't reliably reach the right
specialty for a real student, not just chase a single pass/fail number.

## How to reproduce / continue this work

- Local stack: `docker-compose -f docker-compose.yml -f docker-compose.local.yml up -d` (see profi-backend README / memory for DB creds).
- Statistical check (aggregate accuracy across all 38 senior leaf directions):
  `docker-compose ... exec api python scripts/calibration_simulate.py --census --runs 100 --age senior --census-top-n 3 --seed 7`
  Reports, per profession, how often a "textbook" persona (answers each
  question by maximizing `match_score` against its own profile) lands in the
  top-3 final belief. `--runs 30` is fast but noisy (see below); use `--runs
  100` before trusting a small change.
- Root-cause tracing (why one specific profession fails): write a one-off
  script that walks `akinator_session_service.start_session` /
  `submit_answer` for a single persona, printing each question's text,
  chosen option, and `match_score` per option, plus top-3 belief before/after
  each answer. This found every real bug in this session; the aggregate
  census only tells you *that* something's wrong, never *why*.

### Critical methodology finding: question selection is not seeded

`select_next_question`'s temperature-softmax sampling (`_sample_by_entropy`)
creates its own unseeded `random.Random()` — the census script's `--seed`
only fixes which profession is being simulated, not the actual question
order within a session. Two runs of *identical* code can differ by 5-15
percentage points per profession at `--runs 50`. **Revised (round 16): even
at `--runs 100` this can be 10-20pp for a profession that sits in a crowded
cluster** — e.g. speech-therapist swung 56%→62%→46% and psychologist
43%→52%→58% across three same-code n=100 runs. The earlier "~5pp at n=100"
estimate was too optimistic; it held for isolated professions but not for
ones with several habitual rivals. Any conclusion drawn from a single run at
n<=50 is unreliable, and even at n=100 a single borderline profession
crossing 50% in one run isn't proof of anything — always compare against at
least one same-seed rerun, and trust the *cluster-wide* pattern (does the
same small set of rivals keep winning?) more than any single profession's
exact percentage. This falsified at least three premature "regression"
calls this session — e.g. round 16's apparent "across the board drop" after
the data-science/finance-accounting fix turned out to be the *pre-existing*
baseline (a clean same-seed run with no code changes showed the identical
drop), not something the fix caused.

**Revised again (round 18): for some professions the band is wider still.**
translator, with ZERO code changes across seven separate n=100 runs this
session, landed at 34/46/49/51/52/55/63% — a ~30pp spread. A round-18
experiment (re-adding translator's `Motor:-1`, see "tried and reverted"
below) initially looked like a confirmed regression after 2 runs (32%, 38%
vs a then-assumed 46-55% band) — but two *more* no-change runs afterward
landed at 34% and 63%, which fully overlaps the "with the edit" numbers and
invalidates that conclusion. Lesson reinforced harder this time: for a
profession sitting in the crowded creative cluster, 2 runs on either side of
a change is not enough to call it either way — the practical floor for a
trustworthy verdict on a borderline-cluster profession is more like 4-5
same-seed n=100 runs per side, not 2. Cheaper alternative when that budget
isn't available: judge by the *cluster-wide failing count* and whether the
same *named rivals* keep appearing, not by one profession's raw percentage.

## Current state (as of this doc)

- Baseline before this session: 12/38 professions failing top-3 (n=30).
- After the fixes below, including round 16 (data-science/finance-accounting)
  and round 17 (psychologist): consistently ~1/38 failing at n=100 —
  whichever creative-cluster member (translator/school-teacher/
  speech-therapist/marketing/psychologist) is currently unluckiest in that
  run's RNG, see the noise note above (now known to be wide, up to ~30pp for
  some of these). No profession has failed *reproducibly in the same
  direction* across multiple same-seed n=100 runs since data-science was
  fixed in round 16 and psychologist in round 17.
- Branch history: this work moved `pro-108` → `pro-116` → `pro-120` →
  `pro-111` as the user merged/rebased across the session (`pro-120` was
  merged into `pro-111` via PR #34). Fixes through round 16, including
  data-science/finance-accounting, are committed on `pro-111` as of this
  doc. **Round 17 (psychologist `Ideas:-1`) is verified and kept but not yet
  committed as of this doc** — still in the working tree, along with round
  18's revert (net effect of round 18 on the file: a comment only, no data
  change — see "tried and reverted"). Check `git status` /
  `git diff -- scripts/seed_akinator_content.py` before assuming a clean
  tree. Check `git log --oneline -- scripts/seed_akinator_content.py
  app/services/akinator_engine.py` if picking this back up later — branch
  names in this doc are historical, not necessarily where the work lives now.
- Content lives in `scripts/seed_akinator_content.py` (`SPECIALTIES` for leaf
  profiles, `QUESTIONS` for the question bank); engine logic in
  `app/services/akinator_engine.py`. Every fix below has a matching inline
  comment at its exact location (search for "calibration playtest pass").
- Unrelated but blocking: local dev DB can get stuck on migration `0033` if
  it predates the fix — see `alembic/versions/0033_add_subject_readiness.py`.
  The original had `postgresql.ENUM(...).create(bind, checkfirst=True)`
  followed by using that same ENUM in `op.create_table(...)`, which triggers
  a *second*, unguarded implicit creation via SQLAlchemy's `create_type=True`
  default — fails with `DuplicateObjectError` under asyncpg specifically
  (`checkfirst` doesn't reliably prevent it in this async path). Fixed by
  dropping the manual `.create()` call entirely and letting `create_table`'s
  single implicit creation handle it. If you hit `DuplicateObjectError:
  type "..." already exists` on a fresh `alembic upgrade head`, this is
  almost certainly why — check for the same double-creation pattern.

## Fixed and verified (see inline code comments for exact numbers)

1. **order=0** (very first question) had no option representing the Data
   axis — merged into "техника" alongside Phys. Seeded every IT/data-leaning
   session into the same bucket as mechanical/civil/pilot from question 1.
   Added a 5th option. **Biggest single win of the session** — a structural
   content fix, not a rival-nerf.
2. **order=37** was an undeclared de-facto finance-accounting resolver
   (`resolves_pair=None`, so invisible to resolver audits) — halved its
   weights.
3. Imbalanced resolver weights (the "wrong side" of a pair scored higher for
   its own profession than the "right" option): order=28
   (mechanical-engineer/civil-engineering), order=21 and order=45
   (marketing), order=26 (agronomist).
4. Missing neutral "не знаю" options on non-resolver forced-choice questions:
   orders 24, 29, 36, and the new order=51 (see #6).
5. Missing resolver questions between genuinely close professions: none
   existed between the whole IT/data/finance cluster (added order=51,
   4-way), none between school-teacher/speech-therapist (added order=52),
   none between speech-therapist/social-worker (added order=50).
6. "Zero negative axis" profiles — can gain belief from any answer, never
   lose it, so they win by attrition over a long session regardless of fit.
   Fixed: pilot, hospitality-manager, management-entrepreneurship,
   film-director, design, food-production-tech, lawyer, architect,
   fire-safety-engineer (most recent — see below, not yet committed).
7. marketing was the only profile in the whole catalog with zero axes at
   magnitude 2 — could never win a contested question against any
   resolver (which always carry at least one ±2 weight). Sharpened its two
   defining axes (Ideas, Vis) to 2.
8. **data-science's chronic loss to finance-accounting (round 16, the item
   formerly tracked as "open backlog #2").** Root cause found by tracing
   fresh sessions: the two profiles share *no opposing axis at all* — every
   axis both carry (Data/Obj/Exp/Focus/Struct/Predict/Acad/Math/People/Auto)
   points the same direction, so any question touching that space could only
   ever separate them by relative profile-norm strength, and finance's
   smaller, more concentrated profile almost always won (confirmed on
   order=48: finance scored 2.694 vs data-science's 1.947 on the same shared
   option, even after finance's Focus was already trimmed in round 8).
   Weight-rebalancing on order=37/48 had already been tried and couldn't fix
   this because there was no axis to rebalance *toward* — every rebalance
   just traded which of the two profiles' norm advantage won by less.
   Fixed by adding a genuine new opposing axis: `Inv:1` on data-science
   (finds patterns in messy/raw data — real investigative/constructive work)
   and `Inv:-1` on finance-accounting (applies fixed external rules to the
   letter — same reasoning as lawyer's and fire-safety-engineer's existing
   `Inv:-1`), plus a new order=53 direct resolver question feeding that axis.
   **Verified across three independent same-seed n=100 runs** (two on
   `pro-120`, one after re-merging onto `pro-111`): data-science 42%
   (baseline, no Inv fix) → 61% → 65% → 68%. finance-accounting itself was
   unaffected (93%→96%→96%→98%, no collateral loss). No other profession
   was reproducibly harmed — the professions that flip in/out of "failing"
   across these runs (psychologist, translator, school-teacher,
   speech-therapist) were *already* borderline in the pre-round-16 baseline
   too (see the revised noise note above); they're pre-existing "creative
   cluster" bleed (item 2 below), not a new side effect of this fix.
9. **psychologist's chronic losses to cinematographer/pr-specialist/
   makeup-artist-film (round 17).** Same disease as #8: checked all axes
   shared between psychologist and its three chronic n=100 rivals and found
   zero opposing ones (Exp/Focus/Acad, plus People/Emp for two of the
   three) — every one of them also carries `Ideas:2` (round 6 had already
   zeroed psychologist's own `Ideas` out as incidental overlap, but left it
   with no way to actively lose ground against the cluster). Added
   `Ideas:-1` to psychologist: genuinely not central to psychology (talking
   through an existing person's situation, not inventing abstract/visual
   concepts) and shared at magnitude 2 by all three rivals plus
   film-director. Traced a real session first (order=45's marketing-resolver
   option flipped from +0.196 to -0.192 for psychologist, as intended).
   **Verified across three n=100 runs**: psychologist 48% (pre-round-16/17
   baseline) → 53% → 50% → 51%, with pr-specialist and makeup-artist-film
   dropping out of its top-3 "loses to" list entirely in all three
   post-fix runs (previously its #1/#2 rivals). Kept; not yet committed.

## Tried and reverted (documented in code so nobody repeats the experiment blind)

- **Hard filter on resolver questions** (`select_next_question`): exclude a
  resolves_pair question unless one of its named leaves is in the current
  top-N belief. Measured *worse* (12→10 failing vs 12→7 with no filter) —
  excluding a resolver outright can permanently lock a leaf out of its own
  best rescue chance.
- **Soft priority nudge** (same idea, but discount instead of exclude): DID
  produce a real, reproducible net improvement (n=100: 4→3 failing;
  data-science/marketing/speech-therapist each gained 6-11pp) — but at a
  traced, systematic cost to leaves *adjacent to* a rivalry without being
  part of it (actor lost 18pp because its habitual neighbors' mutual
  resolvers kept getting boosted at its expense). Reverted because the
  failure mode was only found by tracing one profession; true prevalence
  across the other 37 unknown, and this touches every session's question
  order, unlike a content edit. **Follow-up idea, untried**: only grant the
  bonus if the querying leaf itself scores decently on at least one option
  of the resolver, not just because a rival is in its own top-N.
- Removing a shared/overlapping axis outright (data-science's Struct,
  translator's would-be Motor addition) — `match_score` divides by the
  profile's own norm, so removing an axis *shrinks* the norm and makes every
  *other* axis score relatively stronger, often making things worse, not
  better. Lesson: don't remove axes to reduce overlap; only add
  well-justified negatives, and verify the direction empirically.
- Trimming software-engineer's Focus (same recipe that helped
  finance-accounting) — broke software-engineer itself (90%→48%) without
  truly helping data-science. Confirms the "crowded cluster" is not fixable
  by trimming rivals one at a time — the win rotates to whoever's next
  closest (civil-engineering/pilot/architect took over).
- **translator's `Motor:-1` vs cinematographer, retried a second time
  (round 18)** — round 7 had tried and reverted this on a single n=30 run
  that looked bad; round 18 retried it "properly" with n=100 x2, got 32%/38%
  (vs an assumed 46-55% band) and initially declared it a confirmed
  regression. That declaration was itself wrong: two more no-change control
  runs after reverting landed at 34% and 63%, showing translator's true
  noise band is far wider than assumed (see the revised noise note above) —
  32-38% is not distinguishable from that band on 2 runs per side. Left
  reverted as the conservative default, but the record is "inconclusive,"
  not "confirmed harmful." Do not re-cite the earlier "confirmed regression"
  framing (it was corrected same-day in the inline code comment too). A fair
  re-test needs ~4-5 n=100 runs per side, not 2 — not attempted here given
  the time cost of Docker rebuilds this session.
- **Third attempt at a `select_next_question` relevance nudge (round 19)** —
  anchored the bonus to the CURRENT top-1 belief leaf's own score on a
  resolver's options, instead of round-2-attempt's "either named leaf in
  top-5" (which had caused actor's 18pp loss). Directly motivated by a real
  user complaint (a clearly STEM-leaning session getting cinema/medicine
  questions) — traced two sessions before running any census, and both were
  bad enough to revert on trace evidence alone: (1) a software-engineer
  session still got asked film-crew, medicine-cluster, and animals/nature
  resolvers — the original complaint was NOT fixed; (2) a genuinely new
  failure mode appeared that neither prior attempt had: because whichever
  leaf is currently *leading* gets its own resolvers preferentially boosted
  next, a broad/generic profile that edges narrowly ahead (pilot, in the
  traced run) can bootstrap a feedback loop and end up dominating a session
  that should have gone elsewhere — pilot reached 0.636 belief in a session
  simulating a software-engineer persona. An actor-persona trace also still
  hit an unrelated resolver and lost its lead late in the session. Reverted
  same day, before spending a census run on it (Docker was also killing the
  census process on every attempt that day — see below). This is the third
  distinct way `select_next_question`-level nudging has broken something;
  see item 3 below for the still-recommended content-level alternative.

### Aside: Docker Desktop instability this session
Multiple background census runs died with exit 137 (SIGKILL) mid-session,
unrelated to any code change — confirmed by immediately retrying the exact
same command after the api container auto-restarted, which then succeeded.
If a census run comes back completely empty with exit 137, that's Docker,
not a regression — just retry (`docker ps` to confirm the api container is
stable/not mid-restart first).

## Open backlog — not yet fixed

### 1. Same "zero negative axes" bug, not yet audited for real impact
Found in the round-9 systematic scan but not fixed because they weren't
failing census *at the time*: **general-medicine, dentist,
veterinary-zootechnics, sports-coach, rehabilitation-therapist**. All
currently pass at 80-95%+, so low urgency — but fire-safety-engineer looked
fine in aggregate too until a real user's own playthrough surfaced it. Worth
tracing at least once each before assuming they're truly safe.

### 2. The "creative cluster" likely has the same disease data-science had
actor, design, cinematographer, film-director, musician, makeup-artist-film,
pr-specialist all lean heavily on shared Ideas/Vis/Motor/Focus axes and
constantly appear in each other's "often loses to" lists across nearly every
round of this session, independent of whatever else was being changed. This
cluster is the entire remaining source of borderline failures — translator,
school-teacher, speech-therapist, marketing, and (before round 17)
psychologist all lose almost exclusively to cinematographer/pr-specialist/
makeup-artist-film/film-director/design in every recent census run.

**Progress (round 17):** confirmed the "no opposing axis" theory is the
right lens here — psychologist shared zero opposing axes with its three
chronic rivals (all carrying `Ideas:2`), and adding `Ideas:-1` fixed it
cleanly and reproducibly (item 9 above). **Round 18 tried the same theory on
translator vs cinematographer** (also zero opposing axes, via `Motor`) but
came back inconclusive — see "tried and reverted." Two data points either
way isn't enough for a profession this deep in the cluster; translator's own
noise band turned out to span 34-63% at n=100 with *no* code change at all,
wider than any other profession characterized this session. Whoever
continues this: budget 4-5 n=100 runs per side before concluding anything on
translator specifically, and check whether school-teacher/speech-therapist/
marketing/actor have the same axis-overlap shape as psychologist did (a
cleaner target than translator, potentially) before spending more runs on
translator's noisier case.

### 3. Off-topic questions mid-session (real user complaint, 2026-07-21)
A user going clearly down a physics/math-leaning path reported getting asked
about cinema and medicine mid-session — jarring, and a plausible trust/
completion-rate risk even where the final math still lands correctly.
**Confirmed still present as of round 19** via a fresh trace: a
software-engineer-target session got 4 of 15 questions from entirely
unrelated resolvers (film-crew, medicine-cluster, fire-safety/police,
animals/nature).

Root cause: `select_next_question`'s entropy calculation scores a question's
informativeness across *all 38 leaves*, not relative to the current user's
apparent direction — a question that's still highly uncertain for two
unrelated leaves (e.g. actor vs film-director) can out-score a
directly-relevant one.

**Three separate attempts at an algorithm-level fix have now failed** (see
"tried and reverted" above for full detail on each):
1. Hard filter on irrelevant resolvers — measured worse overall.
2. Soft nudge keyed to "either resolver leaf in top-5 belief" — real
   aggregate improvement, but boosted resolvers between a leaf's *neighbors*
   at that leaf's own expense (actor -18pp).
3. Soft nudge keyed to the current #1 leaf's own score — didn't fix the
   original complaint (still asked unrelated resolvers in a fresh trace)
   *and* introduced a leader-lock-in feedback loop (a generic profile that
   edges narrowly ahead gets its own resolvers preferentially boosted next,
   entrenching it further — reached 0.636 belief for the wrong profession
   in one traced session).

**Recommendation: stop trying to fix this at the algorithm level.** Three
different framings of "make relevant resolvers more likely" have each found
a new way to misfire, and the failure modes keep appearing only via manual
tracing, not census aggregates — meaning there's likely a fourth one hiding
too. The still-untried, lower-risk alternative: add more *deep* (depth 2-3)
differentiating questions **within** already-strong clusters (e.g. further
splitting mechanical-engineer/civil-engineering/data-science/
software-engineer/it-infrastructure-security/pilot/architect beyond what
order=28/51 already do) so that, for a genuinely STEM-leaning session,
in-domain questions out-compete off-topic ones on raw
expected-entropy-reduction *on their own merits* — a pure content addition,
no change to `select_next_question` itself, so it can't introduce a new
selection-logic bug the way all three algorithm attempts did.

### 4. Long sessions dilute "quiet" professions
A profession with few genuinely-relevant questions loses relative belief
share over a long session purely from softmax renormalization, even without
being directly contradicted by anything (traced clearly for psychologist
mid-session in an earlier round). Partially mitigated by cleaning up
psychologist's profile (removed incidental Auto/Ideas that were dragging it
into unrelated creative/entrepreneurial resolvers) but the general mechanism
is unaddressed. No content-level fix attempted yet; likely needs either
shorter ceilings or a way to weight later answers more than earlier noise.

## Note on parallel edits to this file

`scripts/seed_akinator_content.py` is shared with unrelated feature work —
during round 16 the user independently added a `subjects_required` field to
every `SPECIALTIES` entry (for a separate subject-readiness quiz feature,
`alembic/versions/0033_add_subject_readiness.py` and friends) while this
calibration work was in progress on a stashed diff. Reapplying the stash
after that work landed produced two real merge conflicts (data-science and
finance-accounting profile lines) — resolved by hand, keeping both the new
`subjects_required` key and the round-16 axis/comment changes. If continuing
this work with the seed file open elsewhere, check `git status` before
assuming a clean baseline — this file accumulates edits from more than one
concurrent effort.

Round 16 is committed. **Round 17 (psychologist `Ideas:-1`) is verified and
kept, but sits uncommitted in the working tree as of this doc** — round 18
touched the same file (added then reverted translator's `Motor:-1`,
replacing the surrounding comment) so the tree isn't clean even though the
net data change from round 18 is zero. Run `git diff -- scripts/seed_akinator_content.py`
before committing to see exactly what round 17 changed.
