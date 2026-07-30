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
- After the fixes below, through round 21 (data-science/finance-accounting,
  psychologist, pilot, hospitality-manager, actor): typically 0-1/38 failing
  at n=100 (one run this session reached 0/38, the best result all
  session) — whichever creative-cluster member (translator/school-teacher/
  speech-therapist/marketing/psychologist/actor) is currently unluckiest in
  that run's RNG, see the noise note above (now known to be wide, up to
  ~30pp for some of these). No profession has failed *reproducibly in the
  same direction* across multiple same-seed n=100 runs since data-science
  was fixed in round 16.
- Branch history: this work moved `pro-108` → `pro-116` → `pro-120` →
  `pro-111` → `pro-114` as the user merged/rebased across the session
  (`pro-120` merged into `pro-111` via PR #34; `pro-111` merged into `dev`
  via PR #35/#36/#37 alongside other unrelated feature work; `pro-114` is
  where rounds 19-21 happened). Fixes through round 16, including
  data-science/finance-accounting, are committed. **Rounds 17 and 20-21
  (psychologist, pilot resolver, hospitality-manager, actor) are verified
  and kept but not yet committed as of this doc** — still in the working
  tree, along with round 18's revert (net effect on the file: a comment
  only, no data change — see "tried and reverted"). `app/services/
  akinator_engine.py` similarly carries round 19's revert (a leader-based
  relevance nudge, tried and reverted same-day — net effect: docstring
  changes only, no behavior change from HEAD). Check `git status` /
  `git diff -- scripts/seed_akinator_content.py app/services/
  akinator_engine.py` before assuming a clean tree. Check `git log
  --oneline -- scripts/seed_akinator_content.py
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
10. **pilot had zero `resolves_pair` questions anywhere in the bank (round
    20)** — the content-level fix for the "off-topic questions" complaint
    (item 3 below), after three algorithm-level attempts all failed (see
    above). Traced sessions found pilot as the single most common wrong
    rival across nearly the entire STEM cluster (mechanical-engineer,
    civil-engineering, architect, software-engineer, data-science,
    it-infrastructure-security, finance-accounting) — most visibly in the
    round-19 trace where it bootstrapped a feedback loop to 0.636 belief in
    a software-engineer-target session. It already had a real opposing axis
    against every one of them (`Inv:-1`, round 3, vs their `Inv:1-2`), but
    always weak (1-2 magnitude) and buried under 6-9 shared same-direction
    axes, with no dedicated resolver to sharpen it or let
    `cluster_resolver_service` disambiguate a final cluster containing
    pilot (that service requires >=2 `resolves_pair` members to overlap the
    cluster — impossible for pilot with zero resolvers). Added order=54: a
    sharp ±2 `Inv` fork ("следовать проверенной процедуре" vs "придумать и
    спроектировать что-то новое"), `resolves_pair` naming pilot plus its
    five main STEM rivals — same playbook as order=53 for data-science.
    Traced first: a software-engineer session that previously lost its lead
    to pilot (0.636 by step 15, see round-19 notes) now never let pilot into
    its top-3 at all, and reached a much more decisive lead (0.532 by step
    12-13) either selecting order=54 directly or resolving cleanly without
    it. **Verified across two n=100 runs**: 2/38 and 1/38 failing overall
    (both were the same pre-existing psychologist/translator borderline
    cases, no new failures). Whole STEM cluster stayed healthy both runs
    (data-science 58-69%, software-engineer 95-98%, mechanical-engineer
    69-74%, civil-engineering 97-99%, architect 96-98%,
    it-infrastructure-security 74-75%, pilot 99%), and pilot's presence in
    *other* professions' "loses to" lists dropped noticeably versus the
    pre-fix pattern. Doesn't fully eliminate off-topic questions in a single
    session (still one content addition, not the whole cluster) but is a
    real, low-risk, measured step in the right direction — see item 3 for
    what's still open. Kept; not yet committed.
11. **hospitality-manager had zero opposing axis vs kindergarten-teacher
    (round 20b)** — same audit method applied to the "business/service"
    cluster (hospitality-manager, management-entrepreneurship,
    social-worker, police-officer, kindergarten-teacher, sports-coach),
    which showed the same "one profile dominates many others' loss lists"
    shape as pilot did for STEM. hospitality-manager and kindergarten-
    teacher share 6 axes (People/Emp/Focus/Struct/Pace/PhysSt), all same
    direction, zero opposing — hospitality-manager didn't carry `Care` at
    all despite being a guest/operations-facing role, not personal
    caregiving (same reasoning as architect's existing `Care:-1`, round 9).
    Added `Care:-1` to hospitality-manager — also a real (if weaker) wedge
    against social-worker (`Care:2`) and sports-coach (`Care:1`), two more
    chronic rivals. **Verified across two n=100 runs**: kindergarten-teacher
    61% → 78% (up from a pre-fix baseline in the high-60s/low-70s), overall
    census reached **0/38 failing** on the first run (best result all
    session) and 1/38 (psychologist, the known chronic case) on the repeat.
    hospitality-manager's presence in other professions' loss lists dropped
    across the board. Noted but not chased further: kindergarten-teacher's
    *new* #2 rival is now police-officer, which also shares zero opposing
    axes with it (People/Focus/Struct/Pace/PhysSt) — kindergarten-teacher
    still comfortably passes (61-78%) so this is low-priority, flagged for
    whoever continues this. Kept; not yet committed.
12. **actor's weak opposition against the creative cluster (round 21)** —
    actor was this session's most persistently borderline profession
    (repeatedly ~50%, and separately the traced casualty of the round-17
    soft-nudge side effect). Unlike items 8/9/11, this wasn't a clean
    zero-opposition case: actor already has real opposition vs design
    (Vis/Auto/People/PhysSt) and food-production-tech (Struct/People). But
    vs its single biggest rival, pr-specialist, it shared 7 same-direction
    axes against only one weak (1-magnitude) opposing one (Auto). Actor
    didn't carry `Inv` either way, despite the job being about interpreting
    material someone else wrote rather than inventing it — added `Inv:-1`
    (same "applies, doesn't invent" reasoning as lawyer/pilot/
    fire-safety-engineer). This opposes pr-specialist/design/
    makeup-artist-film/cinematographer/film-director all at once (everyone
    in the cluster except musician, which carries no Inv either way).
    **Verified across two n=100 runs**: actor 50% → 52%, up from a pre-fix
    ~51% but now with pr-specialist gone from its top-3 losses entirely
    (replaced by cinematographer/musician/makeup-artist-film) — a real
    shift in *which* rival wins, not just a percentage nudge. Partial win,
    not a clean one like items 8/9/11: musician has no Inv axis to oppose,
    so it's now actor's most persistent uncontested rival (and grew
    relatively). psychologist dipped to 39% on the first run (its worst
    showing this session) but recovered to 47% on the repeat — within its
    already-known 39-58% noise band (see item 9), not attributed to this
    change since psychologist's own profile wasn't touched. 1/38 failing
    both runs (psychologist, the known chronic case). Kept; not yet
    committed. **Natural next step, not yet attempted**: find actor's real
    differentiator from musician specifically (they share Ideas/Vis/Motor/
    Risk/Struct, similar "performs live" signature) before touching
    anything else in this cluster.

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

## 2026-07-27 update: catalog grew from 38 to 57 specialties

Between sessions, the user's own parallel work (a different branch/chat)
added **19 new leaves** on top of the original 38 — see
`docs/akinator-new-directions-proposal.md` (a doc from this same effort,
proposing exactly these gaps from the Almaty university dataset; the user
independently implemented 5 of its "явные пробелы" as `petroleum-mining-
geology`, `energy-engineering`, `international-relations`, `logistics`,
`aviation-engineering`, plus 14 more from an earlier pass). `SPECIALTIES` is
now 57, `QUESTIONS` is 53. Branch history since the last update moved
through `pro-114` → `pro-126` → `pro-131` as the user kept merging/rebasing;
branch names in this doc are historical, check `git log` for current state.

**New tooling this round:**
- **Isolated calibration Docker stack** — the user regularly runs parallel
  dev work in other chats against the shared `profi-backend-*` containers,
  which repeatedly caused stuck transactions and SIGKILLs when a census run
  and their dev work hit the same `db`/`api` containers at once. Fixed by
  bringing up a **second, fully separate Compose project**:
  `docker-compose -p profi-calib -f docker-compose.yml -f
  docker-compose.local.yml up -d --build db redis api` (omit `nginx`, the
  only service that binds a host port). Full detail + rationale saved to
  memory (`profi-backend-docker-compose-local` memory file) so future
  sessions start here directly instead of rediscovering it.
- **`--census-only <slug1,slug2,...>` flag added to
  `scripts/calibration_simulate.py`** — a full `--census --runs 100` now
  means 57×100=5700 full simulated sessions through the real engine/DB
  (was 38×100=3800), taking 35-40 minutes even on an idle, uncontended
  stack (confirmed via `time`, not a bug — inherent ~0.4-0.6s/session cost).
  The new flag restricts which leaves get their own persona simulated
  (every leaf is still fully scored/competed against on every question —
  this only cuts how many *outer* personas run) for fast iteration:
  `--census-only project-management,international-relations,... --runs
  30-50` finishes in 1-8 minutes depending on cluster size. **Always
  confirm a fix with at least one full unfiltered `--runs 100` pass before
  calling it done** — the filtered mode is for fast iteration, not final
  verification (a change can help everything you're watching and quietly
  hurt something outside the filtered set, as round 25 demonstrated with
  `architect`).

**Fresh n=100 baseline on the grown catalog: 10/57 failing** —
`international-relations` **1%** (essentially broken), `media-journalism`
27%, `artificial-intelligence` 34%, `marketing-advertising` 36%,
`data-science` 40%, `psychologist` 41%, `journalist` 41%, `marketing` 42%,
`medicine-biology` 45%, `finance-economics` 47%.

### Root-caused international-relations' catastrophic failure — it wasn't international-relations
`international-relations` had already been through **5 documented rounds**
of the standard playbook in the user's own parallel work (search
"Redesigned TWICE" in `scripts/seed_akinator_content.py` for the full
blow-by-blow: zero-opposition fixes, a dedicated resolver, axis-magnitude
trims, a "give it a real positive identity" pass) and was *still* failing
at ~0-1%, each round surfacing a *different* set of rivals. Traced a real
session instead of patching the profile a 6th time: `project-management`
(one of the 19 new leaves) had **9 axes and only ONE negative** — the
exact "zero negative axis" disease fixed repeatedly elsewhere in this file
(pilot round 3, hospitality-manager round 3, marketing round 6) — and won
almost every generic leadership/organize/people question regardless of
fit, reaching 0.53 belief by step 11 of a 22-step session and locking out
the real answer for the rest of it. This wasn't narrowly about
international-relations — the same shape showed up in project-management's
loss lists for speech-therapist, lawyer, fire-safety-engineer,
school-teacher, police-officer, kindergarten-teacher, social-worker.
**Fix (round 23): added `Exp:-1, Care:-1` to `project-management`**
(breadth-across-domains per its own description; operations/coordination
function, not personal caregiving — same reasoning already used for
hospitality-manager's `Exp:-1`/`Care:-1`). **Verified**: overall census
10/57 → 7/57 failing; `international-relations` 1%→8-16% across three runs
(still failing, but no longer catastrophic — see below for what's still
open); `finance-economics`, `medicine-biology` crossed reliably into
passing; `marketing-advertising`/`media-journalism`/`marketing` improved
inconsistently but net-positive. **Traced side effect**: `data-science` and
`artificial-intelligence` got reproducibly *worse* (not noise — repeated in
the same direction on 2 independent runs) — the entropy-based question
selector is global across all 57 leaves, so changing one leaf's profile
measurably shifts which questions get picked in *every* session, including
ones that never touch that leaf's own axes. Expected and compensated for by
the fixes below.

### Parallel diagnostic agents + convergent independent fixing
Launched 4 read-only diagnostic agents in parallel (no Docker/DB access, to
avoid contention) covering the other 9 baseline failures, each tasked with
the same "zero/weak opposing axis" method used throughout this file.
Findings: `psychologist` needed `Dev:-1` (vs `psychology-pedagogy`/
`speech-therapist`); `medicine-biology` needed an axis vs
`rehabilitation-therapist`/`veterinary-zootechnics`/`dentist`;
`journalist`/`media-journalism` both needed `Inv:-1` (vs `pr-specialist`/
`design-digital-art`/`film-director`/`marketing-advertising`);
`marketing`/`marketing-advertising` both needed `Risk:-1` (vs
`business-entrepreneurship`/`film-director`); `artificial-intelligence`
needed an axis vs `architect`; `data-science` needed `Ideas:-1`;
`science-research` needed `Math:-1` (it had no domain anchor axis at all);
the engineering cluster needed `engineering-architecture`/
`mechanical-engineer`/`it-infrastructure-security` axis work.

**Before implementing any of it, discovered the user's parallel session had
already independently applied 7 of these 12 fixes** — same diagnosis,
sometimes the exact same axis (`data-science Ideas:-1`, `journalist
Inv:-1`, `media-journalism Inv:-1`, `marketing-advertising Risk:-1`,
`psychologist Dev:-1`), sometimes a different-but-equally-valid one
(`medicine-biology Obj:-2` instead of `Motor:-1`; `artificial-intelligence
Phys:-1` instead of `Obj:-1`) — all marked "round 23/24, new-specialties
expansion" in the inline comments, converging on the exact same
methodology documented in this file without prompting. **Found one bug
while auditing**: `marketing`'s comment claimed "Risk:-1 added round 23"
but the actual `profile` dict was missing the key — fixed.

**Round 25 — applied the 5 genuinely still-missing fixes** (plus the
marketing bug fix): `artificial-intelligence` got an *additional* `Obj:-1`
(the existing `Phys:-1` alone wasn't enough — still 17-18% failing);
`science-research` got `Math:-1`; `engineering-architecture` got
`Predict:-1` (mirrors civil-engineering, opposes it-infrastructure-
security's `Predict:1`); `mechanical-engineer` got `Predict:1` (opposes
both civil-engineering's and the new engineering-architecture's
`Predict:-1` at once); `it-infrastructure-security` got `Ideas:-1` (opposes
engineering-architecture, its new #1 rival since the section grew to 9
leaves). **Mixed result on fast filtered re-check (2×, n=50)**:
`marketing`/`marketing-advertising` jumped decisively (42→84-88%,
36→54-78%) — clean wins. But `data-science` (18-20%), `artificial-
intelligence` (22-38%), `mechanical-engineer` (26-34%), `it-infrastructure-
security` (36-40%) got *worse*, not better, with **`architect` appearing as
the dominant rival across nearly all of them** — reproducible across both
runs, not noise.

### The engineering/analytical supercluster has hit diminishing returns from axis tweaks
`architect` was already flagged in its own round-9 comment as "the loudest
profile in the catalog" (6 axes at magnitude 2, only 1 negative) — the
disease resurfaced because the surrounding sections grew from 2-3 leaves to
9-10 (engineering-tech: mechanical-engineer/civil-engineering/
engineering-architecture/aviation-engineering/energy-engineering/
petroleum-mining-geology/pilot/architect; plus data-science/artificial-
intelligence/science-research sharing much of the same Ideas/Inv/Exp/Focus/
Struct/Acad territory). **Round 26**: added `Predict:1` to `architect`
(additive — architecture is an iterative, client-driven creative process,
genuinely less predictable-up-front than either rigorous structural
engineering or statistical/scientific method; opposes civil-engineering,
engineering-architecture, data-science, artificial-intelligence, and
science-research's `Predict:-1` all at once). Kept — it's benign and
description-grounded — but the aggregate result was only modest/
inconsistent: `mechanical-engineer` improved slightly (26-34%→34%) but its
rivals *rotated* to entirely different leaves (cinematographer,
civil-engineering, food-production-tech) rather than resolving;
`data-science`/`international-relations` didn't move at all. **This is the
same rotation pattern documented in round 11** (trimming one loud rival
just hands the win to the next-closest one) — except this time the fix was
purely *additive*, not a trim, and it still rotated rather than resolved,
because the underlying problem isn't any single leaf anymore: it's that
10+ leaves now genuinely share most of their axis space with no single
missing-axis fix able to cover all of them. **Conclusion: stop
axis-tweaking this cluster.** See `docs/akinator-deep-differentiation-plan.md`
(written this session) for the next approach — dedicated depth 2-3 resolver
questions naming specific rivals within this cluster, the same structural
content-fix pattern that worked for pilot (round 20) and data-science
(round 16), rather than more profile edits.

### Still open as of this doc
- `international-relations`: 8-16% across 3 filtered runs — hugely
  improved from 1% but still failing. Its 3 dedicated resolvers (order=
  59/60/61) exist but its current rivals (`law-public-administration`,
  `lawyer`, `pilot`) aren't the ones those resolvers were built against.
  Needs a fresh trace against its *current* rival set, not another
  profile-only patch (5 rounds of that already failed once).
- `data-science`, `artificial-intelligence`, `mechanical-engineer`,
  `it-infrastructure-security`: still failing (18-40% range), rivals rotate
  between `architect`/`software-engineer`/`finance-economics`/
  `civil-engineering`/`cinematographer` depending on the run — this is the
  supercluster problem above, needs deep-differentiation questions, not
  more axes.
- `psychologist` (42-45%), `journalist` (48-58%): borderline, existing
  fixes (Dev/Predict/Ideas/Inv) already applied, not chased further this
  round.
- **Near-duplicate taxonomy flags from the diagnostic agents** (not
  axis-fixable, a product decision): `marketing`/`marketing-advertising`/
  `pr-specialist` share professions in their lists (Бренд-менеджер,
  PR-менеджер); `journalist`/`media-journalism` share "Журналист"/
  "Блогер-журналист"; `engineering-architecture` sits profile-wise almost
  exactly between `civil-engineering` and `architect`. Worth a deliberate
  decision on whether all of these should coexist as separate leaves before
  spending more calibration effort on any of them.
- A full unfiltered `--census --runs 100` (no `--census-only`) was kicked
  off after round 26 to get a clean overall picture including leaves not
  in the filtered set this round — check for its output/results if picking
  this up fresh; it was still running when this doc was last edited.

## Note on parallel edits to this file (original, pre-2026-07-27)

Round 16 is committed. **Round 17 (psychologist `Ideas:-1`) is verified and
kept, but sits uncommitted in the working tree as of this doc** — round 18
touched the same file (added then reverted translator's `Motor:-1`,
replacing the surrounding comment) so the tree isn't clean even though the
net data change from round 18 is zero. Run `git diff -- scripts/seed_akinator_content.py`
before committing to see exactly what round 17 changed.

## Status snapshot, 2026-07-28 (context-clear checkpoint)

Everything below is uncommitted as of this checkpoint (`git status` in both
`profi-backend` and `Profy-Frontend` shows the full list). Picking this up
fresh: read this whole doc plus `docs/akinator-deep-differentiation-plan.md`
before doing anything else — a lot happened in one sitting.

**Solid, working, ready to commit whenever:**
- Round 24 content fixes (data-science/journalist/psychologist/medicine-biology/
  finance-economics/marketing/marketing-advertising/media-journalism/
  artificial-intelligence axis additions) — all verified via full n=100 census.
- Deep-differentiation priority 1 (STEM/engineering cluster, orders 63-65 in
  `QUESTIONS`) — verified, AI 44%→64%, mechanical-engineer 32%→41%.
- "Не интересует" feature (backend `apply_disinterest` + frontend button) —
  traced and confirmed working in isolation (named leaves drop ~5-6x, all
  other leaves' relative order exactly preserved). Touches
  `app/services/akinator_engine.py`, `app/services/akinator_session_service.py`,
  `app/schemas/akinator_session.py`, `app/routers/akinator.py` on the backend,
  and `AkinatorAssessmentView.tsx`/`useAkinatorAssessment.ts`/`shared/types/index.ts`
  on the frontend (Profy-Frontend repo, separate `git status`).
- `entrypoint.sh` CRLF fix (real infra bug, unrelated to calibration — see
  [[profi-backend-docker-compose-local]] memory).

**REVERTED, 2026-07-28 (same day as found broken):** `_has_topic_relevance` /
the topic-irrelevance penalty in `select_next_question` (attempt 4 at the
off-topic-question algorithm fix). Cleanly removed — `_has_topic_relevance`,
`_TOPIC_RELEVANCE_TOP_N`, `_TOPIC_IRRELEVANCE_PENALTY`,
`_TOPIC_IRRELEVANCE_ONSET_STEP`, and the penalty-wiring block inside
`select_next_question` are all gone; `select_next_question`'s docstring now
documents attempt 4 (false-positive via shared-but-unrelated axis VALUE
between `data-science`/`international-relations`'s `Care:-2`, same as
before) inline alongside attempts 1-3, with an explicit "don't try a 5th"
conclusion. **Decision: stop trying to fix this at the `select_next_question`
algorithm level entirely** (4/4 attempts have each failed in a genuinely
different way, found only via manual tracing). Going forward, the two
sanctioned mitigations are (a) the "Не интересует" button — the user's own
explicit preference, since it hands the judgment call to the user rather
than guessing algorithmically — and (b) the deep-differentiation content
plan's remaining priorities (below), not further `select_next_question`
edits.

**Deep-differentiation priority 2 (business/service cluster) — DONE and
VERIFIED, 2026-07-28.** Targeted census on the 8 originally-planned leaves
(marketing/marketing-advertising/business-entrepreneurship/management-
entrepreneurship/project-management/finance-economics/finance-accounting/
pr-specialist) found all 8 already passing (75-98%), so the plan's own
assumption (a failure *within* that labeled cluster) didn't hold — the real,
empirically-confirmed rivalry was cross-cluster: marketing/marketing-
advertising/business-entrepreneurship's top-2 rivals were consistently
pr-specialist and design-digital-art (10-20/100 losses each), with
film-director/makeup-artist-film also appearing — all from the creative-
design/stage-media sections, sharing Ideas/Inv/Vis/People with zero
opposition. Root cause: none of those 4 creative leaves carried `Motiv`
("результат, финиш vs процесс") despite the business trio's own `Motiv:1-2`
already being central to their identity. Fixed the standard way: added
`Motiv:-1` to pr-specialist/design-digital-art/film-director/
makeup-artist-film (each has its own inline justification — crafting a
story/image/visual/film is process work, not a measured business outcome)
plus a new order=66 direct resolver naming all 7 leaves at once (mirrors
order=54/63's multi-leaf fork pattern). Traced first (pure `match_score`
check, no DB needed): clean fork for all 7 named leaves, negligible
collateral on their other existing resolvers (orders 39/45/46/59/64 don't
touch Motiv, so the added axis only grows the profile norm slightly — same
safe pattern as every prior "add a real axis" fix). **Verified across two
independent n=100 runs (seed=7, seed=13):** marketing-advertising 75%→86%→
87%, business-entrepreneurship 86%→96%→95%, marketing 89%→98%→97% — all
three consistent across both seeds, not noise. Rivals themselves
(pr-specialist, design-digital-art, film-director, makeup-artist-film)
stayed strong both runs (91-98%), no collateral damage. `QUESTIONS` is now
57 (was 56), `assert` updated. Kept; not yet committed.

**Not done, next up:** deep-differentiation plan priority 3 (words/
communication cluster) and international-relations round 7 (last measured
19-21%, still colliding with law-public-administration/pilot/lawyer after
round 6's full profile rewrite).

## 2026-07-29: attempt 5 (cluster-lock window) — off-topic mid-session questions

A real playtest (user manually clicking through the frontend) sharpened the
"off-topic questions" complaint that priorities 1-2 didn't actually fix:
final accuracy was correct (landed on software-engineer) but the QUESTION
SEQUENCE itself was incoherent — 3 clear physmat/IT wide-start answers, then
neutral, then a café resolver, then animals/helping-people. Content
additions (deep-diff) only help the engine resolve correctly ONCE it's
already circling the right cluster — they don't stop it wandering into
unrelated clusters mid-session, which is a `select_next_question`-level
problem, not a content one.

**First tried WIDE_START_STEPS 3->4** (using the bank's 4th and last
depth<=1 direct question, order=3) — verified real via 2 seeds: target-
persona accuracy 65%->74-78%, but random/consistent/alternating strategies
got meaningfully longer (+1-2.4 avg steps) and hit the ceiling far more
often (+9-18pp). Only delayed the complaint by exactly one step, didn't fix
continuity. **Reverted same day**, superseded by the item below.

**Attempt 5 (kept):** a temporary CANDIDATE-SET restriction (not a score
nudge, unlike attempts 1-4) for `_CLUSTER_LOCK_STEPS=3` steps right after
wide-start. `_is_cluster_relevant`: generic (non-resolver) questions always
pass; a `resolves_pair` question passes only if it names a leaf in the
CURRENT top-`_CLUSTER_LOCK_TOP_N=5` belief. Falls back to the unfiltered
pool if the filter would leave nothing (avoids attempt 1's lockout
failure). Self-limiting by construction: a clear answerer gets a
concentrated top-5 so the lock steers meaningfully; a scattered answerer
gets a spread-out top-5 so it barely restricts anything — matches the
user's own stated expectation ("scattered answers -> scattered questions is
fine, that's not the complaint").

Traced against the exact physmat scenario (6 runs): within the lock window,
every resolver shown was either generic or thematically adjacent
(finance-accounting's Data/Math overlap with physmat is real, not a bug —
see below); zero medicine/animals/cinema-style jumps, versus 5/6 runs
hitting one before this fix. The 2 off-topic hits that did occur happened
strictly AFTER the window (step 8), as designed.

Same tradeoff shape as the WIDE_START_STEPS experiment showed up again in
the health-check (random/consistent/alternating avg steps +1-1.5, ceiling
rate +10-19pp; target accuracy 65%->77%) — expected, and accepted per the
user's own logic: this cost only lands on already-ambiguous answer
patterns, not on users who actually answer clearly.

**Full census (57 leaves, n=50, seed=7) after attempt 5: 2/57 failing**
(international-relations 40%, translator 48% — both pre-existing chronic
cases, not new). Critically, **no regression on attempt 2's or attempt 3's
casualties**: actor 88%, software-engineer 100%, pilot 84% (not
dominating). This is the first algorithm-level attempt in this whole effort
to pass a full census clean on its first try.

**Second-seed confirmation (n=50, seed=13): also clean.** actor 86%,
software-engineer 96%, pilot 62% (reasonable losses, not dominating) — no
attempt-2/3-style regression on either seed. 2/57 failing again:
international-relations 34% (consistent chronic case, both seeds).
translator/mechanical-engineer each failed on exactly one of the two seeds
(48%/62% and 56%/48% respectively, not both at once) — within the
already-documented noise band for these borderline STEM/creative-cluster
professions, not attributed to attempt 5. **Attempt 5 is now considered
verified**, not just promising.

## 2026-07-29: census performance fix — real periodic commits

The single-giant-rolled-back-transaction design (flagged as open tech debt
repeatedly in this doc) finally got fixed after a user-reported 3-hour
full-census run. Root cause was exactly as suspected: `scripts/
calibration_simulate.py`'s `main()` bound its `AsyncSession` with
`join_transaction_mode="create_savepoint"` inside one outer `conn.begin()`
that was always rolled back — every `db.commit()` already called
throughout the script AND inside `akinator_session_service` was only ever
releasing a SAVEPOINT, never a real commit, so Postgres MVCC visibility
checks kept accumulating cost across the entire run (thousands of sessions
in one transaction).

**Fix:** removed the savepoint wrapper entirely — `main()` now uses a plain
`AsyncSession(engine, ...)`, so every existing `db.commit()` call is a real
commit. Throwaway data is cleaned up for real at the end via
`_cleanup_calibration_data` (DELETE, not rollback) — matched by the fixed
`@calibration.local` email domain. **Caught one real bug while implementing
this**: `profiles.user_id -> users.id` has no `ON DELETE CASCADE` (unlike
`assessments.profile_id` and `assessment_sessions.assessment_id`, which
do), so deleting `User` rows first raised `ForeignKeyViolationError` —
fixed by deleting `Profile` rows first.

**Verified:** full 57x50 census (2850 sessions) now takes **~23 minutes**
flat, with per-profession timing STABLE throughout (15-35s each, first
profession to last) — no more growth from ~70s to ~300s+ over a run. Since
this now leaves real (if temporary) rows in `profi-calib`'s DB during a
run, it's more important than ever to only ever point this script at the
isolated `profi-calib` stack, never a real dev/prod database — already the
standing rule, now with a slightly higher cost if violated.

## 2026-07-29: content QA pass — duplicate questions and "не знаю" doubling

A manual playtest surfaced two real, confirmed content bugs (not
perception issues):

1. **The frontend ALWAYS renders its own "🤷‍♂️ Затрудняюсь ответить / Не
   знаю" button** for every question (`AkinatorAssessmentView.tsx`,
   unconditional, not gated on the question having its own neutral
   option) — this has been true since early in this effort (see
   `calibration_simulate.py`'s own `_pick_option` docstring, which already
   documented this fact). But **27 of 57 questions ALSO listed their own
   explicit `{"text": "не знаю", ...}` entry** in `options` — a leftover
   from before `option_index=None` became the uniform not-know mechanism.
   Result: those 27 questions showed "не знаю" TWICE (once as a normal
   option card, once as the fixed dashed-border button below); the other
   30 showed it once. **Fixed:** stripped all 27 redundant explicit
   entries (they were byte-identical, one `replace_all` edit) — verified
   every question still has >=2 real options, module still imports/
   validates cleanly, and a smoke-test census run still completes normally.
   The frontend button is untouched and remains the sole "не знаю"
   affordance everywhere, now consistently.

2. **Duplicate/near-duplicate question TEXTS**, found by exact and
   near-string matching across all 57: order=54 and order=66 (both my own
   2026-07-28/29 additions) were WORD-FOR-WORD identical ("В работе тебе
   важнее…") despite testing different axes (Inv vs Motiv). order=55/63
   ("В инженерной работе тебе ближе/интереснее…") and order=4/60/61
   ("Помогать людям…"/"Забота о ком-то…") were near-duplicates. **Fixed:**
   reworded the newer of each pair (66, 63, 60, 61 — all added 2026-07-24
   or later) to a distinct opening phrase, keeping every axis_weights/
   resolves_pair/option exactly as-is (order=61's near-duplicate option
   text was also lightly reworded, same axis meaning). Older/foundational
   questions (54, 55, 4) left untouched. Verified no exact duplicates
   remain via the same detection script.

**Update, same day:** the four "числа/данные" questions (orders 37/48/51/53)
were reworded too, once flagged. They're functionally distinct (37: a
generic Data-vs-People gate, resolves_pair=None; 48: management-
entrepreneurship vs finance-accounting, logistics vs accounting; 51: the
4-way data-science/software-engineer/finance-accounting/it-infrastructure-
security resolver; 53: data-science vs finance-accounting specifically, the
Inv-axis fork from round 16) but 3 of the 4 opened with "числа"/"цифры"/
"числа и данные" — a physmat/IT-leaning user can plausibly see 2-3 of them
in one session and feel like they're repeating themselves, even though each
tests something different. Reworded all 4 to distinct opening phrases
(order=37 "Точные расчёты и порядок — это про тебя?", order=48 "В
бизнес-процессах тебе ближе…", order=51 "В IT и данных тебе конкретно
нравится…", order=53 "Разбираясь в фактах, тебе важнее…") — options,
axis_weights, and resolves_pair untouched on all 4. Verified: module loads,
57 questions, no exact duplicates anywhere in the bank.

## 2026-07-29: international-relations round 7 — partial progress, honestly reported

Baseline going in: 34-40% across two n=50 full-catalog census seeds, losing
consistently to law-public-administration, lawyer, and pilot.

**Root cause, found by tracing (not just re-reading the profile):** this
profile's own dedicated resolver, order=57 ("Работать на стыке разных
сторон — что тебе ближе?"), was written when this profile's `Struct` was
different — round 6 (2026-07-24, documented in the profile's own long
comment history) flipped `Struct` to +2 to align with law-public-
administration, and nobody re-verified order=57 afterward. Computed
`match_score` by hand and confirmed: international-relations, law-public-
administration, lawyer, AND pilot ALL score highest on the SAME option of
order=57 now — it resolves nothing between them (still correctly opposes
journalist, its other named leaf, untouched). Every other axis this profile
carries (Emp/Care/Motiv/Dev) is extra relative to the trio, not opposing —
they just don't touch those axes.

**Fix that worked:** found one real, fully unused, fully shared axis —
`Data`. All three rivals carry `Data:1` (precise records/precedent/
instrument data); this profile carried none. Diplomacy/negotiation is a
relationship field, not a data-analysis one. Added `Data:-1` + new order=67
resolver (clean single-axis fork, verified via `match_score`: international-
relations -0.38/0.58, all three rivals ~0.42-0.45/~-0.42 to -0.45).
**Targeted census (n=100): 34-40%->45%.** Real, measured improvement — but
still short of 50%, still losing to the same three at nearly the same rate.

**Two follow-up attempts, BOTH tried and reverted after full-census
verification came back worse** (documented in detail inline in the
profile's own comment, so nobody repeats them blind):
- Second axis, `Lead:-1` + order=68 (all three rivals also share `Lead:1`,
  untouched by this profile) — isolated `match_score` looked clean, full
  census came back WORSE (45%->25%).
- Removing `Inv:-1` after tracing WHY: this profile's existing `Inv:-1`
  (added round 2, correctly opposes the design/creative cluster) also
  happens to match lawyer's/pilot's own `Inv:-1` — on the STEM Inv+Motor
  double-fork (order=63), the target-persona "correctly" picks the `Inv:-1`
  side, but that option's `Motor:2` benefits pilot/mechanical-engineer
  enormously while contributing nothing to this profile (no Motor axis).
  Removing `Inv:-1` turns that into an exact 0/0 tie ("не знаю") instead of
  a forced wrong-genre pick — looked like a clean improvement in isolation,
  and didn't break order=59 (still separates via `Struct` alone). Full
  census came back WORSE anyway (45%->38%): a "не знаю" answer wastes that
  question's slot entirely in a ceiling-bound session instead of extracting
  even `Inv`'s partial signal — see open backlog #4 ("long sessions dilute
  quiet professions"). A lesson worth generalizing: **a change that looks
  correct on an isolated `match_score` check for one question can still be
  a net negative once you account for the full session** (wasted slots,
  not just wrong-direction pulls) — always verify via census even when the
  isolated trace looks unambiguous.

**Standing result, end of round 7: 45% (order=67/`Data` only), up from
34-40%, still failing top-3.** Honestly not fully solved. Whoever continues
this: the lesson above points toward a full-session-aware fix (e.g. more of
this profile's OWN high-signal resolvers so it wastes fewer question slots)
rather than another isolated axis edit — not attempted today.

**Deep-differentiation priority 3 (words/communication cluster) — not
otherwise started.** journalist/media-journalism/translator/lawyer/
law-public-administration/pr-specialist were all re-checked as collateral
during this round's census runs and are healthy (55-99%, no regressions
from any of the international-relations changes above, including the two
reverted ones — profile edits to one leaf don't touch any other leaf's own
profile).

**Priority 3 follow-up, same day: journalist/media-journalism.** Clean
14-leaf baseline census for the whole cluster found journalist at 58%
(losing most to media-journalism, x30/100) and translator at 64% (losing
most to cinematographer, food-production-tech — the same crowded creative
cluster this session already spent two rounds on, with the documented
conclusion "needs 4-5+ n=100 runs per side to say anything, not attempted
here given Docker rebuild cost" — left alone this round rather than repeat
that mistake).

journalist/media-journalism turned out to share the exact "structural hole"
pattern already fixed for pilot in round 20: they're each other's #1 mutual
rival but had ZERO `resolves_pair` questions naming both together, despite
a real, already-existing opposing axis sitting unused — `Predict`
(journalist:2, comfortable with breaking-news unpredictability; media-
journalism:-1, planned/produced content). Added order=69, a clean
single-axis resolver. Verified via `match_score` first (journalist
0.873/-0.873, media-journalism -0.516/0.516), then via two independent
n=100 census runs: **journalist 58%→69% (seed=7) / 62% (seed=21)** — real
improvement both seeds, media-journalism unaffected (90-96%, within noise).
`QUESTIONS` now 59.

**Still open, not attempted:** translator (64%, deliberately left alone
per the noise-band lesson above); the two remaining priority-3 clusters
named in the plan doc's "taxonomy, not calibration" note (marketing/
marketing-advertising/pr-specialist professions-list overlap; engineering-
architecture sitting between civil-engineering/architect) — product
decisions, not calibration work.

## 2026-07-29: two real bugs found via manual playtest (not calibration)

A user manually clicking through the app (main stack, not profi-calib) found
two real product bugs while testing as a reference "programmer" persona,
unrelated to axis/question calibration:

**1. Zombie question row.** A manual reference-persona trace surfaced a
question (order=68) that no longer exists in `scripts/seed_akinator_
content.py` — it was this session's own Lead-axis experiment for
international-relations, tried and reverted earlier the same day. Root
cause: `seed_questions` only ever upserts by `order`, never deletes a row
whose `order` disappeared from `QUESTIONS` unless it's explicitly listed in
`RETIRED_QUESTION_ORDERS` — a same-day add-then-revert during iteration
was never registered there, so the row silently kept being served by the
live engine. **Fixed properly, not just patched once**: `seed_questions`
now also deletes any `AkinatorQuestion` row whose `order` isn't in the
live `QUESTIONS` list, on every run — this makes the DB self-healing on
every deploy (entrypoint.sh already runs this script unconditionally on
every container start), regardless of whether anyone remembers to register
a retirement. Verified live: manufactured a fake order=999 row, ran the
seed script, confirmed it reported "1 orphan(s) deleted" and the row was
gone — on both `profi-calib` and the main stack.

**2. `explore-*` nodes (junior/middle-only reveal buckets) leaking into the
"I already know my profession" picker, 404ing when picked.** `GET /
directions/tree` (the picker's only data source) returned every `is_leaf`
Direction with zero age filtering, including the 6 `EXPLORE_NODES` —
these are the Akinator engine's own internal fallback reveal buckets for
junior sessions that don't differentiate within the real 57-specialty
catalog, `age_groups=["junior","middle"]` only (no "senior"), and have no
row in `known_profession_quizzes` (seeded only for the 57 real
specialties, confirmed 1:1 — no gaps). Junior isn't a wired-up branch of
the app currently, so these nodes should never be user-selectable at all
right now. **Fixed:** `direction_service.get_direction_tree` now filters
to leaves with `"senior" in age_groups`, which cleanly excludes all 6
`explore-*` nodes without hardcoding slugs. Verified live via `GET /api/v1/
directions/tree` on the main stack: response shrank from 42052 to 39262
bytes, zero `explore-*` slugs remain in it. Applied to the main stack
directly (`docker cp` + `docker restart profi-backend-api-1`) since this
is an app bug, not calibration content — no profi-calib involvement needed.

Both fixes are uncommitted, same as everything else today.

## 2026-07-29: IT cluster — 3 structural holes found via reference-persona playtest

Ran 5 manual "textbook" reference-persona sessions through the real engine
(software-engineer, data-science, it-development, it-infrastructure-
security, artificial-intelligence — the whole `akinator-it-data` section
minus the junior-only explore node), including the full post-reveal
cluster-resolver phase (`cluster_resolver_service`), not just the main
akinator phase. 3/5 personas landed on the wrong result in at least one run
(RNG-noise dependent, per the usual caveat). Traced each with `match_score`
by hand rather than guessing.

**it-development lost a real session to [it-development, finance-economics,
software-engineer] with ZERO eligible cluster-resolver questions to
disambiguate further** (none existed linking any two of the three). Root
cause: zero axis opposition among all three — classic disease. Real,
description-grounded fix: `Exp` flipped 1→-1 on it-development's profile —
its own description says "без жёсткой специализации на конкретном стеке"
(no strict specialization) but it carried `Exp:1` ("глубокая узкая
экспертиза" per axes.py — literally the opposite trait). This alone
creates real opposition against software-engineer (Exp:2) and finance-
economics (Exp:1). Added order=70, a dedicated Exp resolver naming all
three. **Verified: it-development 100%→99% across two n=100 seeds** (no
prior census number existed for it — this was its first-ever calibration
check), 0 collateral damage on software-engineer/finance-economics.

**it-infrastructure-security lost a real session to [energy-engineering,
engineering-architecture, pilot].** It already carried a real, unused
opposing axis — `Focus:-1` ("реагировать на нештатные ситуации" — incident
response is constant context-switching, the literal opposite of energy-
engineering's `Focus:1` and pilot's `Focus:2` sustained deep work) — just
no dedicated resolver ever forced it. Added order=71. **Verified: it-
infrastructure-security 83%/82% across two seeds** (first-ever calibration
check for this leaf too).

**data-science lost a real session to [software-engineer, finance-
economics, architect]**, with the only cluster-resolver question touching
two of the three (order=54, a diluted 9-way STEM fork) rather than a
dedicated one. It already carried real opposition on `Obj` (-2, "разбирать/
докапываться") against software-engineer (Obj:1) and architect (Obj:1) —
same "applies/builds vs investigates" wedge used elsewhere in this file —
just no resolver naming this specific trio. Added order=72. **Verified:
data-science 61%/58% across two seeds** — within its already-documented
noise band (not a regression; no prior number existed specifically
post-order=67 either, so this is a fresh baseline, not a comparison point).

`QUESTIONS` now 62 (was 59).

**Also fixed: `cluster_resolver_service.get_eligible_questions` picked the
lowest-`order` eligible resolver with no regard for how much of the
cluster it actually covered.** Re-examining the it-infrastructure-security
trace found this WASN'T actually the cause of that specific miss (it-
infrastructure-security had already lost in the MAIN phase before cluster
resolution even started — the resolve phase was legitimately disambiguating
only the 3 leaves that made the cluster). But the underlying logic gap is
real and general: with only a `>=2 overlap` bar and no preference for
covering leaves not yet addressed, the scarce 3-question resolve budget
could still get spent on a resolver that leaves a genuinely-undecided
cluster member completely unaddressed when a better alternative exists.
Fixed: `get_eligible_questions` now sorts by (fresh cluster-leaf coverage
descending, total overlap descending, curation order ascending) instead of
order alone. Verified: `tests/integration/test_cluster_resolver.py` still
passes.

## 2026-07-29: it-development retired — confirmed accidental near-duplicate

User's own follow-up question after the round above ("чем IT и разработка
отличается по факту от SE?") led to retiring it-development entirely —
their read was that a teammate probably added it by accident, and the
axis/content analysis backed that up completely: zero real opposition
against software-engineer even after today's Exp fix (that fix was
*constructed* to make the engine technically distinguish them, not a
restored real distinction), both `professions` lists literally shared
"Fullstack-разработчик", and both descriptions said the same thing in
different words. Confirmed via the university data itself: **151 of 155**
`Program` rows tagged with `it-development` already ALSO carried
`software-engineer` — only 4 ("Информатика"/"Компьютерные науки"/
"Компьютерная инженерия" at Melbourne/KTH/NTU/Bilkent) had it as their sole
tag.

**Removal, done properly, not just deleted from the list:**
- Added `it-development` to `RETIRED_DIRECTION_SLUGS` (comment explains why,
  matches the file's own established retirement convention).
- Removed order=70 (this session's own Exp resolver, built specifically for
  it-development — no longer meaningful without it).
- New one-off `scripts/retag_it_development.py`: strips `it-development`
  from every `Program.direction_slugs`; the 4 sole-tag programs get
  `software-engineer` added instead so none end up with an empty array.
  Not part of the regular entrypoint pipeline (one-time cleanup).
- Ran the (now self-healing, see the zombie-question fix above)
  `seed_akinator_content.py`: hard-deleted the `it-development` Direction
  row, cleared 2 real `Assessment.selected_direction_slug` references that
  had already resolved to it (prevents a 500 on those users' roadmap page),
  and auto-deleted the now-orphaned order=70 question row.

`SPECIALTIES` now 56 (was 57), `QUESTIONS` now 61 (was 62). Verified zero
remaining references anywhere (`programs.direction_slugs`,
`directions.slug`, `akinator_questions.resolves_pair`) on both stacks.
Applied to the main stack directly (retag + seed + restart), same as the
other app-level fixes today.

## 2026-07-29: new metric — off-topic question rate, and a full n=50 census

Added a genuine measurement for "how often do completely irrelevant
questions appear", operationalized precisely (not by feel): a question
counts as off-topic for a session if it's a dedicated resolver naming
specific OTHER professions (never this session's own target) on which the
target persona has no honest positive answer — the case a real user would
plausibly hit "Не интересует" on, distinct from generic "не знаю" (see
`_run_one`'s new tracking in `scripts/calibration_simulate.py`,
`RunResult.off_topic_count`/`not_know_count`, reported per-profession and
catalog-wide by `run_census`).

**Full n=50 census across all 56 leaves (post it-development retirement):
0/56 failing — the best result of the whole 2026-07 effort.** Worst:
international-relations 54%, mechanical-engineer 60%, journalist 64%,
translator 66% — nobody below 50%. **Off-topic rate: 6.5% catalog-wide
average** (2467/37842 questions). Worst 10: school-teacher (12.3%),
psychology-pedagogy (11.4%), international-relations (10.6%), psychologist
(10.6%), law-public-administration (10.5%), police-officer (10.4%), actor
(10.3%), science-research (8.6%), lawyer (8.3%), media-journalism (8.3%) —
clustering around two groups: the "helper" cluster (school-teacher/
psychology-pedagogy/psychologist/police-officer) and the "law" cluster
(international-relations/law-public-administration/lawyer).

**Helper cluster — same structural-hole audit as everything else today,
and the gaps were dramatic:** of 21 possible pairs among the 7 leaves
(school-teacher/psychology-pedagogy/psychologist/kindergarten-teacher/
speech-therapist/social-worker/police-officer), **15 had ZERO shared
`resolves_pair` question.** kindergarten-teacher and police-officer each
had zero resolvers against ALL 6 of the others. Three fixes:
- kindergarten-teacher: added `Acad:-1` (the only one of the 6 with no
  Acad at all, despite every real rival carrying positive Acad) + new
  order=73 resolver naming 5 rivals at once.
- police-officer: added `Emp:-1` (procedure/authority-driven, not
  emotional-attunement work, despite 4 rivals carrying `Emp:2`) + new
  order=74 resolver.
- psychology-pedagogy vs psychologist: near-identical profiles, zero
  resolver, but real existing opposition on `Motiv`/`Dev` (pedagogy is
  result/teaching-oriented, psychologist is process/non-directive) — new
  order=75 resolver, no profile changes needed.

**Verified via two n=100 census seeds, all 7 leaves: 0/7 failing (79-96%
range), accuracy healthy.** Off-topic rate: mixed but net positive —
school-teacher/psychology-pedagogy improved, kindergarten-teacher (5.8-7.4%)
and social-worker (3.9-4.2%) now clearly low, psychologist roughly flat,
**police-officer got WORSE (10.4%→12.3-12.7%, consistent both seeds, not
noise)**. Root cause: adding `Emp:-1` grows police-officer's profile norm,
which dilutes its OTHER axis scores slightly on every unrelated question in
the bank — the same "add an axis, pay a small universal dilution cost"
tradeoff documented all day, just newly visible because this is the first
metric sensitive enough to detect it directly (top-3 accuracy wasn't).
Accepted as a reasonable trade: closing a confirmed zero-resolver
structural hole for a real, measured +2pp cost elsewhere. `QUESTIONS` now
64 (was 61).

**Law cluster (international-relations/law-public-administration/lawyer) —
investigated, NOT further fixed, and this was a deliberate decision, not
an oversight.** Unlike the helper cluster, internal coverage is already
complete (order=67 links all pairs). Traced 20 sessions per leaf and found
off-topic hits scattered across **15+ different, unrelated orders** (STEM
resolvers, business resolvers, psychology resolvers, medicine resolvers —
no concentration on 1-2 fixable gaps). Root cause: these three share a
generic "serious, structured professional" signature (People:1, Data:1,
Exp:2, Focus:2, Struct:2, Acad:2) that weakly touches almost every resolver
in the catalog without a strong specific stake either way. This is the same
diffuse "generic broad profile vs sharply-worded specific resolvers"
pattern already diagnosed and abandoned for the STEM supercluster earlier
this session ("stop axis-tweaking this cluster... the win rotates to
whoever's next closest") — chasing individual off-topic orders here would
be whack-a-mole with no stable fix. The two mitigations already built today
(cluster-lock window, "Не интересует" button) are the right tools for this
specific shape of problem, not more resolvers.

## 2026-07-29: it-development retirement was incomplete — found the hard way

Restarting the main stack after the helper-cluster fixes above crashed it:
`entrypoint.sh`'s pipeline runs `seed_astana_universities.py` unconditionally
on every container start, and that script has its own hardcoded per-program
`direction_slugs` literals (NOT sourced from the live `programs` table) —
it still listed `it-development` for 18 Astana programs, and its own
`assert _slug in _KNOWN_DIRECTION_SLUGS` check (validated against the
current live SPECIALTIES/EXPLORE_NODES, which correctly no longer include
it-development) crashed the whole boot on that mismatch.

The earlier retirement only fixed the **live database** (via
`retag_it_development.py` + the self-healing seed) — it missed that
`it-development` was ALSO hardcoded directly in seed-script source, which
re-asserts/re-inserts on every fresh deploy regardless of what's already in
the database. Found and fixed the same pattern in three more files:
- `scripts/seed_astana_universities.py` — 18 occurrences in
  `"direction_slugs": [...]` literals, all alongside other real tags (0
  sole-tag cases, same pattern as the database had).
- `scripts/seed_almaty_universities.py` — 133 occurrences, same pattern, 0
  sole-tag cases (these two files' counts, 18+133=151, exactly match the
  151 "had other tags" count `retag_it_development.py` reported against
  the live database — confirms this was the same underlying data, just
  duplicated across the DB and these two source files).
- `scripts/seed_known_profession_quizzes.py` — a whole 5-question quiz
  block for `leaf_slug: "it-development"`. Not in `entrypoint.sh`'s
  pipeline (didn't cause the crash) but still stale/orphaned content —
  removed the block entirely.

Fixed via a small script-driven removal (strip `it-development` from every
`direction_slugs` array, verified 0 remaining afterward) rather than by
hand across 151 occurrences. Verified: main stack now boots clean through
the full `entrypoint.sh` pipeline end to end, `curl /docs` returns 200,
zero remaining `it-development` references anywhere in the codebase or
either stack's database. All four touched files now byte-identical
(`md5sum`) between `profi-calib` and the main stack.

**Lesson for any future retirement**: `RETIRED_DIRECTION_SLUGS` in
`seed_akinator_content.py` only guarantees the *akinator content* self-heals
— it says nothing about the university-seeding scripts, which turned out to
carry their own independent copies of the same slug. Check `grep -rl
"<slug>" scripts/` across the WHOLE scripts directory before considering a
retirement complete, not just the akinator content file.

## 2026-07-29: made this class of bug catchable automatically — `validate_content_integrity.py`

Follow-up to the it-development retirement above, which took three separate
discoveries (live `programs` table, then `seed_astana_universities.py`/
`seed_almaty_universities.py`'s own hardcoded copies, then a stale
`known_profession_quizzes` row) before it was actually complete. Rather
than rely on remembering to `grep` everywhere next time, added a single
consolidated check: new `scripts/validate_content_integrity.py`, wired in
as the LAST step of `entrypoint.sh` (after every seed script, before
`Starting API`). One pass over the live database, checks every place a
Direction slug gets referenced:
- `programs.direction_slugs` — reported as a WARNING (a stale tag there
  degrades gracefully, the program just doesn't show up under that
  direction).
- `akinator_questions.resolves_pair` — FATAL (a dangling slug here silently
  breaks a resolver's whole point, and the akinator engine reads this at
  runtime).
- `known_profession_quizzes.leaf_slug` — FATAL. This is the ONLY validation
  that has ever covered this table — `seed_known_profession_quizzes.py` has
  no assert of its own, and isn't even in the entrypoint pipeline (open
  question below).

Verified: ran standalone (`Content integrity OK: 75 directions, 1513
programs, 64 questions, 56 known-profession quizzes`), then verified the
FULL `entrypoint.sh` end-to-end via a real container restart (not just the
individual script) — boots clean through to `Starting API`. Applied to both
stacks, `entrypoint.sh` and the new script byte-identical (`md5sum`)
between them.

**Open question, not decided today:** `seed_known_profession_quizzes.py`
itself is still NOT in `entrypoint.sh`'s pipeline — a genuinely fresh
deploy (empty DB) would boot with ZERO `known_profession_quizzes` rows,
silently breaking the "I already know my profession" quiz feature entirely
for that environment, until someone runs the script by hand. Not added to
the pipeline today because memory notes an existing plan to redesign this
specific feature ("profi-known-profession-redesign" — dead-end quiz,
decided plan: server-side banks, sessionless Assessment) — didn't want to
bake a behavior change into the boot sequence for a feature already flagged
for rework without the user's explicit call.

**Resolved same day**: user confirmed `seed_known_profession_quizzes.py`
should be added — it's the per-leaf validation quiz for the "Уже знаю, кем
хочу стать" flow (`AssessmentGoal.known`): a user picks a specific leaf
directly from `/directions/tree` (skipping the belief-walk engine
entirely), answers 5 profession-specific questions, and gets a fit
percentage/verdict (strong/partial/weak) via `known_profession_service.
score_answers` — a sanity-check on an already-made choice, not a discovery
mechanism, so it was safe to add regardless of the separate known-
profession-*redesign* plan (which is about the picker/entry-point UX, not
this validation step). Confirmed idempotent (upserts by `leaf_slug`, no
assert of its own) and all 56 `leaf_slug`s valid against current
SPECIALTIES before wiring in. Added to `entrypoint.sh` after the Almaty
universities step, before the broken-session cleanup. Verified via a real
container restart on both stacks (not just the standalone script) — full
pipeline boots clean, `validate_content_integrity.py` now reports 56
known-profession quizzes (was 0 on `profi-calib`, which had never run this
script before), and `GET /api/v1/directions/software-engineer/known-
profession-quiz` returns real data instead of 404.
