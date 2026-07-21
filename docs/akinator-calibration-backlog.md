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
percentage points per profession at `--runs 50`, ~5pp at `--runs 100`. Any
conclusion drawn from a single run at n<=50 is unreliable — always compare
against a same-seed rerun (or use n=100) before deciding a change helped or
hurt. This falsified at least two premature "regression" calls this session.

## Current state (as of this doc)

- Baseline before this session: 12/38 professions failing top-3 (n=30).
- After the fixes below: consistently ~1-3/38 failing at n=100 (data-science
  is the one still-reliable failure; a couple of others sit right at the 50%
  edge and flip between passing/failing depending on run).
- All fixes except the most recent one (fire-safety-engineer, see below) are
  committed to `pro-108`. Check `git log --oneline -- scripts/seed_akinator_content.py app/services/akinator_engine.py`
  and `git diff` for exact uncommitted state.
- Content lives in `scripts/seed_akinator_content.py` (`SPECIALTIES` for leaf
  profiles, `QUESTIONS` for the question bank); engine logic in
  `app/services/akinator_engine.py`. Every fix below has a matching inline
  comment at its exact location (search for "calibration playtest pass").

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

## Open backlog — not yet fixed

### 1. Same "zero negative axes" bug, not yet audited for real impact
Found in the round-9 systematic scan but not fixed because they weren't
failing census *at the time*: **general-medicine, dentist,
veterinary-zootechnics, sports-coach, rehabilitation-therapist**. All
currently pass at 80-95%+, so low urgency — but fire-safety-engineer looked
fine in aggregate too until a real user's own playthrough surfaced it. Worth
tracing at least once each before assuming they're truly safe.

### 2. data-science — the one confirmed chronic case
Sits at a genuine "crowded intersection": its core temperament axes
(Focus/Struct/Math/Exp — "precise, deep-focus, analytical") are shared
almost identically with finance-accounting, software-engineer,
civil-engineering, pilot, lawyer, mechanical-engineer. Weakening whichever
rival is currently #1 just hands the win to the next-closest rival in the
same cluster (confirmed twice: finance-accounting→software-engineer→
civil-engineering/pilot/architect). The *only* fix that produced a durable,
non-rotating improvement was structural (order=0's missing Data option, item
#1 above). Recommendation: look for a similar structural/content gap
specific to data-science's true differentiator (Obj axis — investigative
analysis vs building/inventing) rather than more rival-nerfing.

### 3. The "creative cluster" likely has the same disease as data-science
actor, design, cinematographer, film-director, musician, makeup-artist-film,
pr-specialist all lean heavily on shared Ideas/Vis/Motor/Focus axes and
constantly appear in each other's "often loses to" lists across nearly every
round of this session, independent of whatever else was being changed. Never
directly investigated with the same rigor as data-science. Worth the same
treatment: trace 2-3 personas from this cluster, look for a missing
structural distinction (a merged/absent option somewhere early), rather than
more axis-tweaking.

### 4. Off-topic questions mid-session (real user complaint, 2026-07-21)
A user going clearly down a physics/math-leaning path reported getting asked
about cinema and medicine mid-session — jarring, and a plausible trust/
completion-rate risk even where the final math still lands correctly.
Root cause: `select_next_question`'s entropy calculation scores a question's
informativeness across *all 38 leaves*, not relative to the current user's
apparent direction — a question that's still highly uncertain for two
unrelated leaves (e.g. actor vs film-director) can out-score a
directly-relevant one. The reverted "soft nudge" experiment (see above) was
one attempt at this; it worked but had its own side effect. Untried
alternative worth exploring: add more *deep* (depth 2-3) differentiating
questions **within** already-strong clusters (e.g. further splitting
mechanical-engineer/civil-engineering/data-science/software-engineer/
it-infrastructure-security/pilot/architect beyond what order=28/51 already
do) so that, for a genuinely STEM-leaning session, in-domain questions
out-compete off-topic ones on raw expected-entropy-reduction — without
touching the global selection algorithm at all.

### 5. Long sessions dilute "quiet" professions
A profession with few genuinely-relevant questions loses relative belief
share over a long session purely from softmax renormalization, even without
being directly contradicted by anything (traced clearly for psychologist
mid-session in an earlier round). Partially mitigated by cleaning up
psychologist's profile (removed incidental Auto/Ideas that were dragging it
into unrelated creative/entrepreneurial resolvers) but the general mechanism
is unaddressed. No content-level fix attempted yet; likely needs either
shorter ceilings or a way to weight later answers more than earlier noise.

## Most recent uncommitted work

`fire-safety-engineer`: added `Auto:-1, Inv:-1` (round 15) — it shared 8 of
11 axes with it-infrastructure-security and had zero negatives, so any
generic "precise/structured" question fed both, explaining the real user's
"IT the whole time, still got fire-safety" experience. Confirmed
it-infrastructure-security 75%→77%, fire-safety-engineer correctly cooled
82%→65%. A same-seed n=100 repeat was in flight to rule out noise when this
doc was written — check `/tmp/round15_repeat.txt` if it still exists, or
just rerun the census command above.
