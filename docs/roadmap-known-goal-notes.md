# `known`-goal roadmap notes (research only — no decisions, no plan)

Date: 2026-08-04
Author: Backend Architect session, `pro-156`.

Scope: this is grounded analysis of what exists in the codebase today, for a
human to read before anyone decides whether/how `AssessmentGoal.known`
("Уже знаю, кем хочу стать") should get its own roadmap logic. It does not
propose a design. `docs/riasec-roadmap-tasks.md` (#9/#10/#11) and
`docs/roadmap-goal-contract.md` cover the 3 goals (`explore`/`profession`/
`university`) that the recent roadmap rework actually targeted; `known` was
explicitly out of scope for that work.

---

## 1. What `known` does end-to-end today

1. **Direction picker.** `GET /api/v1/directions/tree` returns the full
   sphere → leaf-profession catalog for a "known-profession picker"
   (`app/routers/directions.py:17-23`, docstring says exactly this). The
   student picks a leaf `Direction` directly — this is not a recommendation,
   it's a catalog browse.

2. **Validation quiz.** `GET /api/v1/directions/{slug}/known-profession-quiz`
   (`app/routers/directions.py:34-41`) returns a small, hand-authored
   per-leaf question bank (`KnownProfessionQuiz`, `app/models/
   known_profession_quiz.py:11-19`): each question has `kind` ∈
   `situational`/`subject`/`commitment` and 2+ options, each option carrying
   a `fit_score` of 0/1/2 (`app/schemas/known_profession.py:7-16`). This is a
   small, purpose-built bank outside the belief-walk engine — explicitly not
   one-row-per-question like `AkinatorQuestion` (model docstring, same file).

3. **Finalize.** `POST /api/v1/assessment/known-profession/finalize`
   (`app/routers/assessment.py:48-63`) calls `known_profession_service.
   finalize` (`app/services/known_profession_service.py:47-104`), which:
   - looks up the `Direction` and 404s if it doesn't exist or isn't a leaf
     (`known_profession_service.py:53-55`);
   - loads the quiz for that leaf, 404s if none exists yet
     (`known_profession_service.py:57-62`);
   - scores the answers via `score_answers` — sum of `fit_score` across
     answered questions vs. `2 * len(questions)` as max, giving a `percent`,
     then bucketed into a `verdict` of `strong`(≥70)/`partial`(≥40)/`weak`
     (`known_profession_service.py:23-44`);
   - abandons any `in_progress` `Assessment` the profile currently has,
     same "only one current assessment" invariant `assessment_service.
     create_assessment` enforces elsewhere (`known_profession_service.py:
     66-77`);
   - **creates a new `Assessment` directly in `completed` status**, with
     `goal=AssessmentGoal.known` and, critically,
     `selected_direction_slug=direction_slug` **set immediately at
     creation** — not left `None` pending a later "confirm" step
     (`known_profession_service.py:83-90`);
   - **does not create an `AssessmentSession` row at all.** The comment
     directly above the `Assessment(...)` construction says so explicitly:
     "No AssessmentSession is created here — this flow never runs the
     belief-walk engine, so there is no session/belief to persist... See
     known-profession-redesign notes: result_service.get_result and
     roadmap_builder already tolerate a sessionless Assessment."
     (`known_profession_service.py:79-82`);
   - writes a `KnownProfessionQuizLog` row (`leaf_slug`, raw `answers`,
     `percent`, `verdict`) tied to the new assessment
     (`known_profession_service.py:93-100`).

   Response is just `{assessment_id, percent, verdict}`
   (`app/schemas/known_profession.py:30-33`) — the router docstring says the
   point of creating a completed assessment immediately is so "`/result` and
   `/roadmap` work immediately" (`app/routers/assessment.py:54-56`).

**Verified claim: "known is sessionless."** `known_profession_service.
finalize` never touches `AssessmentSession` (grep for `AssessmentSession`
in that file returns nothing). `Assessment.session` is a `lazy="joined"`
relationship (`app/models/assessment.py:59`) that will simply resolve to
`None` for these rows, and `Assessment.is_akinator` (`app/models/
assessment.py:61-63`) — `return self.session is not None` — is `False` for
every `known` assessment. `KnownProfessionQuizLog`'s own docstring confirms
the same thing from the other side: "assessment_id points at the sessionless
Assessment created for this flow... no AssessmentSession exists for it"
(`app/models/known_profession_quiz_log.py:14-16`).

**`AssessmentGoal.known` special-casing, exhaustively.** `grep -rn
"AssessmentGoal.known" app/` turns up exactly one hit in the entire `app/`
tree: the assignment at `known_profession_service.py:85` where the
`Assessment` row is created. Nothing in `roadmap_builder.py`,
`student_context.py`, or the roadmap prompt (`app/prompts/
direction_roadmap.py`) mentions `known` by name or branches on it. The one
place in the codebase that *does* explicitly branch on "is this a
sessionless/known assessment" is `result_service.py` (§2 below) — a
different endpoint (`/result`), not the roadmap one.

---

## 2. What happens today when a `known` assessment hits the roadmap endpoints

Traced through the actual gate and generation code, not assumed:

**The access gate passes, silently, with no `known`-specific branch.**
`_require_direction_roadmap_access` (`app/services/roadmap_builder.py:
104-166`) checks `confirmed = assessment.selected_direction_slug`
(line 131). For `known`, this is never `None` — it was set at `Assessment`
creation time by `known_profession_service.finalize`
(`known_profession_service.py:87`), before the roadmap endpoint is ever
called. So the `confirmed is None` branch (lines 132-151), which is where
`explore`/`unsure` get their relaxed gate and where `profession`/
`university`/`known` would otherwise 400 with "Сначала выберите это
направление в тесте" — never fires for `known`. Execution falls straight
through to the `confirmed == slug` / direction lookup path (lines 153-166)
exactly like an already-confirmed `profession` or `university` assessment
would. There is no `if assessment.goal == AssessmentGoal.known` anywhere in
this function — it works by construction (the flow pre-populates the field
the gate checks), not by an explicit case for `known`.

This is directly exercised by `tests/integration/
test_known_profession_router.py::test_roadmap_access_allowed_after_known_
profession_finalize` (lines 229-257), whose own docstring says: "Confirms
the sessionless Assessment this flow creates plugs straight into the
existing roadmap pipeline — no roadmap_builder changes needed." **This test
only calls `_require_direction_roadmap_access` directly** — it does not go
through `generate_direction_roadmap` / `POST /api/v1/roadmap/directions`,
so it does not exercise LLM-backed content generation. I found no test
anywhere in `tests/` that drives the full roadmap-generation pipeline
(mocked-LLM or otherwise) for a `known`-goal assessment. `tests/
integration/test_roadmap_builder.py:166-172`'s parametrized regression test
explicitly covers only `profession`/`university` and says in its own
docstring: "profession/university (and known, untested here since it's set
via a dedicated flow) must keep requiring a confirmed direction" — i.e. the
test suite itself flags that `known`'s gate behavior is asserted by
construction/comment, not by a dedicated test of the goal-branch logic
(because there isn't one).

**Generation itself: no exception, but the input signal is the thinnest of
any goal.** Assuming the gate is passed and `generate_direction_roadmap`
runs (`roadmap_builder.py:224-265`), it calls `build_student_context`
unconditionally (`app/services/student_context.py:23-143`), same as every
other goal. That function is already written to tolerate `session is None`
(it has to, for the same `known` flow) — see `belief: dict[str, float] =
session.belief if session else {}` (line 52) and `rejected_slugs = list(
session.rejected_leaves) if session else []` (line 53) — so nothing throws.
But walking through what that means concretely for `known`:

- `leaning_directions` → always `{}` (built from `belief`, which is `{}`)
  (`student_context.py:69-73`).
- `rejected_directions` → always `[]` (built from `rejected_slugs`, which is
  `[]`) (`student_context.py:74-76`).
- `axis_matches` / `axis_growth_areas` → always `{}`. These are gated by an
  explicit `if session is not None:` block (`student_context.py:92-108`)
  that is skipped entirely for `known`. This is the **measured**, most-
  trusted student signal per the roadmap prompt's own stated priority order
  (see below) — it is unconditionally unavailable for `known`.
- `strengths` → **does** populate, because it's read off `target_direction.
  profile` (`student_context.py:82-90`), i.e. what the *direction* values,
  not a measured fact about the student — and `target_direction` is looked
  up via the `direction_slug` argument explicitly passed in
  (`student_context.py:59-60, 81`), independent of `belief`/session.
- `subject_readiness` → **may** populate. It's read from
  `SubjectReadinessSession` keyed only by `assessment_id`
  (`student_context.py:110-121`), a model whose own docstring says it's
  "Entirely separate from the Akinator engine (AssessmentSession,
  assessment_id..." (`app/models/subject_readiness_session.py:20-22`), and
  the router that drives it (`app/routers/subject_readiness.py:21-35`) only
  checks that the calling user owns the `Assessment` — no goal check
  anywhere. So this signal is available for `known` **iff** the frontend
  separately routes the student through that mini-quiz after finalize; nothing
  about the `known` flow itself populates it.
- `subjects_liked`/`subjects_disliked`/`subjects_easy`/`subjects_hard`,
  `artifacts` → populate normally, since both come straight off `Profile`
  columns (`student_context.py:131-135`), collected at onboarding,
  independent of goal or session entirely.
- **The quiz result itself (`percent`/`verdict` from `KnownProfessionQuizLog`)
  is not read anywhere in this path.** `student_context.py` never queries
  `KnownProfessionQuizLog`, and neither does `roadmap_builder.py` or the
  prompt module `app/prompts/direction_roadmap.py` (confirmed by grep — zero
  hits for `KnownProfessionQuizLog`/`verdict`/`quiz_log` in any of those three
  files). The one piece of `known`-specific measured signal this flow just
  produced is invisible to roadmap generation.

**Does the LLM call itself degrade gracefully or produce nonsense?** Based
on reading the prompt's own instructions (`app/prompts/direction_roadmap.py`),
it's designed to degrade, not to only work when full signal exists — it was
written with a priority-ordered fallback chain per field, not a hard
dependency on axis/session data:

- `subjects_now` note: priority is `subject_readiness` → self-reported
  subjects → "neutral note, no invented level" if nothing at all
  (`direction_roadmap.py:106-118`). For `known` without a completed
  subject-readiness pass, this collapses to tier 2 or 3 — self-report or
  neutral, same as it would for any goal lacking that signal.
- `growth_focus`: 5-source priority chain — `subject_readiness` →
  `axis_growth_areas` → `subjects_hard`/`disliked` → `rejected_directions` →
  direction's own `axis_profile` (not a measured student fact at all, just
  an axis the direction cares about that didn't make the `strengths` cut)
  (`direction_roadmap.py:159-178`). Sources 1-2 (the *measured* ones) are
  structurally empty for `known` per above; source 4 (`rejected_directions`)
  is also always empty for `known`. So `known` roadmaps fall to source 3
  (self-report, if relevant subjects exist) or source 5, which is always
  available since it's pure `Direction` data (`direction_roadmap.py:186-192`
  explicitly instructs the model to use source 5 framed as "next-level
  polish," not a fabricated weakness, when nothing else qualifies).
- `profession_options`: driven by `axis_matches`/`subject_readiness`
  distinguishing signal when present, else return 2-3 options with
  `why=null` (`direction_roadmap.py:94-103`) — this logic doesn't
  fundamentally break for `known`, but the schema/prompt in general assumes
  the model is helping the student *narrow down* from several plausible
  professions in a direction. For `known`, the student already told the
  system exactly which single profession they want (via the leaf `Direction`
  they picked) — the response is a `profession_options` list which may
  reintroduce ambiguity ("2-3 professions with why=null") the flow was
  supposed to have already resolved.

**Net answer to "works, degrades, or breaks": it runs without throwing and
produces a structurally valid `DirectionRoadmapResponse` — same schema as
`profession`/`university` — but on the weakest tier of personalization the
prompt supports (self-report + direction-level data only, no measured
axis/belief signal, and the one measured `known`-specific signal — the quiz
verdict — silently unused).** This is a plausible/graceful degradation, not
a crash or obviously nonsensical output, but it is untested (§1) and nobody
has verified the actual text output reads sensibly for a "I already know
what I want" student versus a "help me figure out subjects_now/growth_focus"
student for whom the prompt was written.

---

## 3. What's conceptually different about `known` vs. the 3 designed goals

The 3 in-scope goals (per `docs/riasec-roadmap-tasks.md` and
`docs/roadmap-goal-contract.md §6`) share one thing `known` doesn't have:
some kind of *discover/match/narrow* step before a direction is settled on.

- **`explore`**: "try several things on" — explicitly no commitment, the
  gate relaxation (§1.2 of the goal contract, `roadmap_builder.py:131-151`)
  exists specifically because there's no confirmed direction yet, and
  generating a plan must not silently confirm one
  (`roadmap_builder.py:252-260`). The whole point is trying multiple
  `direction_slugs` via the 0..N endpoint (`roadmap_builder.py:463-477`).
- **`profession`**: the student has a goal of landing on *a* profession, but
  (per the goal contract §6 and task #10) the plan is meant to expand into
  3-5 candidate professions with practice per profession — i.e. still a
  narrowing/comparison step, just narrower than `explore`.
- **`university`**: admission-focused; richness lives in
  `university_requirements` (§4 of the goal contract) — deadlines, grants,
  language, portfolio, documents. Still assumes a direction was arrived at
  through the assessment, same access-gate shape as `profession`
  (`roadmap_builder.py:138`, `known` unchanged alongside them).

`known` starts from the opposite premise: **the student already picked one
specific leaf profession from the full catalog before any test ran** — the
`Direction` comes from `GET /directions/tree` (a browse), not from
`leaning_directions`/belief or an LLM match. The quiz that follows
(`known_profession_service.score_answers`) isn't a discovery instrument —
its own scoring produces a `strong`/`partial`/`weak` **validation verdict**
against a choice already made, not a recommendation. There is no "which
direction" question left to answer by the time roadmap generation would run
for `known` — only "given this specific, self-selected, quiz-validated
target, what does a plan toward it look like."

Whether that's closer in *shape* to `profession` (skills/subjects/starter
actions toward one path) or `university` (admission mechanics once the path
is fixed), or genuinely needs both, or neither because the quiz `verdict`
changes what the plan should even say (e.g. a `weak` verdict arguably means
something different from a `strong` one for what "development plan" should
recommend) is an open question — see §5. The current code treats it as
identical in shape to `profession`/`university` (same gate behavior, same
response schema, same prompt) purely because nothing distinguishes it, not
because that equivalence was evaluated and chosen.

---

## 4. Signal availability summary for `known`, vs. what #9/#10/#11 assume

| Signal | Available for `known`? | Where established |
|---|---|---|
| `Assessment.selected_direction_slug` | Yes — set at finalize, not via a later confirm step | `known_profession_service.py:87` |
| `AssessmentSession` (belief, rejected_leaves, step) | **No** — never created | `known_profession_service.py:79-82`, `app/models/assessment.py:59-63` |
| `axis_matches` / `axis_growth_areas` (measured, per-axis) | **No** — gated on `session is not None` | `student_context.py:92-108` |
| `leaning_directions` / `rejected_directions` | **No** — both derived from `belief`/`rejected_slugs`, which are `{}`/`[]` without a session | `student_context.py:52-53, 69-76` |
| `strengths` (direction's own axis profile) | Yes — direction-shaped, not student-measured | `student_context.py:81-90` |
| `subject_readiness` (measured, per-subject) | Conditional — only if the frontend separately drives that flow post-finalize; nothing in `known`'s own flow populates it | `student_context.py:110-121`, `app/models/subject_readiness_session.py:20-22` |
| `subjects_liked/disliked/easy/hard`, `artifacts` | Yes — plain `Profile` columns, goal-independent | `student_context.py:131-135` |
| `KnownProfessionQuizLog.percent` / `.verdict` | Exists in the DB, tied to the assessment, but **not read** by `student_context.py`, `roadmap_builder.py`, or the prompt | `known_profession_service.py:93-100`; grep confirms zero references elsewhere |

The goal-specific generators referenced by #9/#10/#11 in `docs/
riasec-roadmap-tasks.md` (explore's "try different things," profession's
3-5 candidates, university's admission block) are described there as
working "on the existing belief-walk signal" (`riasec-roadmap-tasks.md`
lines 26-28: tasks #9/#10 are tagged 🟡, "can start on current signal").
That current signal is exactly the two rows (`axis_matches`/
`axis_growth_areas` and `leaning_directions`/`rejected_directions`) that are
structurally empty for `known`. Any of that future generator logic that
leans on belief/axis signal — which per the prompt's own priority chains
(§2 above) is *most* of the highest-trust tiers — would need a fallback
story for `known` specifically, or would silently run on the same
degraded/self-report-only tier as a `known` roadmap does today.

---

## 5. Open questions for a human (not answered here)

- Should `known` reuse the existing `DirectionRoadmapResponse` shape and
  `roadmap_builder` pipeline at all, or does "already knows the profession"
  warrant a distinct response/content shape the way `university_
  requirements` is distinct content within the shared shape (goal contract
  §6)?
- Should the quiz `verdict` (`strong`/`partial`/`weak`) factor into the plan
  at all — e.g. should a `weak` verdict change `growth_focus`, add a
  "reconsider or dig deeper" framing, or otherwise surface the mismatch the
  quiz already measured but the roadmap currently ignores? Or is the quiz
  intentionally a separate, closed loop (validate the choice, show
  percent/verdict once) that was never meant to feed into a longer-lived
  plan?
- Is `profession_options` (a list of 1-3 professions, sometimes with
  `why=null` when the model can't distinguish) the right shape at all for a
  student who already picked exactly one profession by name? Should `known`
  roadmaps special-case this field (e.g. always exactly 1, always with
  `why`) or is reusing the ambiguity-tolerant version fine?
- Should `known` get its own `_require_direction_roadmap_access` branch, or
  is "falls through the same path as `profession`/`university` because
  `selected_direction_slug` happens to already be set" acceptable to keep
  relying on implicitly, long-term?
- Given `axis_matches`/`axis_growth_areas`/`leaning_directions`/
  `rejected_directions` are structurally unavailable without an
  `AssessmentSession`, is there any appetite for optionally routing `known`
  students through a lightweight signal-gathering step (e.g. making
  `subject_readiness` a required/prompted step rather than an optional one
  for this goal specifically) before roadmap generation, or is staying on
  self-report/direction-only signal an accepted tradeoff for this flow?
- Does `known` warrant explicit test coverage of the full (mocked-LLM)
  generation pipeline — today only the access gate is tested
  (`test_known_profession_router.py:229-257`), not actual content — before
  any of the above is decided, just to establish a truthful baseline of
  what today's output currently reads like?
- Is the current behavior (silent success on the weakest personalization
  tier, no error, no `known`-specific messaging anywhere in the response)
  actually desired as a stopgap, or should `known` be explicitly blocked
  from the roadmap endpoints (like the current `_EMPTY_SLUGS_NOT_IMPLEMENTED`
  400 pattern used elsewhere in this file for another not-yet-designed case,
  `roadmap_builder.py:454-460`) until it's deliberately designed, rather
  than silently degrading?
