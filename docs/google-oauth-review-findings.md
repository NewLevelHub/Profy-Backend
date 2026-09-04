# Google OAuth — code review findings (2026-08-28)

## Context

Multi-angle code review of the Google OAuth feature (`app/services/oauth_service.py`
and the auth changes around it) done right after PR #66 (`pro-229-to-dev` → `dev`)
merged. 10 findings survived verification against the actual current code.
Not all are equally urgent — this doc ranks them and gives a straight answer on
what needs fixing before wider rollout vs. what can wait.

## Priority verdict

**Fix before promoting Google login to real users** (findings #1–#4): #1 is a
security hole in the exact feature being launched — every day it's live with
real traffic is exposure, not a hypothetical. #2–#4 are a correctness
regression that can lock out or duplicate **existing** users the moment this
ships to prod, not something that only bites in some future scenario.

**Fine to defer a week or more** (findings #5–#10): edge cases, rare races, a
migration path that's essentially never exercised in this repo, and pure
efficiency/cleanup with no user-facing impact.

## Findings

### 1. Account takeover via Google auto-link — `app/services/oauth_service.py:42`

Auto-linking a Google login to an existing account (matched by email) leaves
the account's pre-existing password hash untouched.

**Attack**: attacker registers via `POST /register` with the victim's real
email and a password of their choosing. The row stays `is_verified=False`
(attacker never sees the verification code sent to the victim's real inbox).
Later the victim signs in with "Sign in with Google" using that same email —
`login_or_register_google` (lines 40–44) finds the attacker's row by email,
sets `google_id` and `is_verified=True`, but never touches
`hashed_password`. From that point, `auth_service.login()` succeeds for the
**attacker's original password**, since `hashed_password` is set and
`is_verified` is now `True` — the attacker has standing access to an account
the victim believes is exclusively theirs via Google.

**Fix direction**: on link, either clear `hashed_password` (force the
account to Google-only) or require the victim to already own a verified
account before linking — don't silently adopt an unverified row.

### 2–4. Legacy mixed-case emails: lockout + duplicate accounts

Root cause: this session's fix for the Google-linking case-mismatch bug
normalizes email to lowercase for all *new* requests (`NormalizedEmail` in
`app/schemas/auth.py`), but there's no migration backfilling **existing**
rows that were stored in whatever case the user originally typed (pre-fix,
nothing normalized case at all).

- **`app/services/auth_service.py:27`** — `login()`'s case-sensitive lookup
  can't find a pre-existing user like `'Jane.Doe@Gmail.com'` when they log
  in with the same address (now lowercased to `'jane.doe@gmail.com'` before
  the query) → `401 Invalid credentials` despite the correct password.
  `password_reset_service.initiate_reset()` has the identical defect, and
  is compounded by the anti-enumeration fix from PR #65
  (`app/routers/auth.py:136`, `except ValueError: pass`) — the user's
  forgot-password request silently "succeeds" with no code ever sent. **No
  recovery path exists for an affected user.**
- **`app/services/auth_service.py:61`** — `register()`'s case-sensitive
  uniqueness check misses the same pre-existing mixed-case rows, so
  registering with the already-used email (just normalized) creates a
  **second, separate account** instead of returning "Email already exists".
- **`app/services/oauth_service.py:40`** — same defect for Google
  sign-in: the email-linking lookup can't find a pre-existing mixed-case
  account, so Google login also creates a duplicate instead of linking —
  splitting the user's existing profile/assessment data across two rows.

**Fix direction**: a one-time backfill migration lowercasing all existing
`users.email` values resolves all three symptoms at once (the normalization
going forward already ensures no new mixed-case rows get created). Worth
checking prod data first to gauge how many rows are actually affected.

### 5. Google network errors surface as unhandled 500 — `oauth_service.py:23`

`verify_google_id_token` only catches `ValueError`. If Google's public JWKS
endpoint is briefly unreachable/times out during cert fetch, the resulting
`requests`/`urllib3` exception isn't a `ValueError`, isn't caught anywhere,
and produces an unhandled 500 for what should be a transient, retryable
condition.

### 6. Missing `email` claim raises uncaught `KeyError` — `oauth_service.py:34`

`claims["email"]` uses direct dict indexing. A token obtained without the
email/profile scope has no `"email"` key, so this raises `KeyError` —
uncaught, unhandled 500 instead of a clean 400. Edge case (standard Google
Identity Services flow always includes email), low real-world likelihood.

### 7. Concurrent new-Google-user race — `oauth_service.py:46`

Lookup-then-insert with no protection against a duplicate concurrent
request. Two simultaneous first-time Google logins for the same brand-new
account can both pass the lookups and both attempt `db.add()`+`commit()`;
the second raises `IntegrityError` (not `ValueError`) → unhandled 500
instead of a graceful response. Rare (double-tab/double-click), not urgent.

### 8. Migration `downgrade()` breaks once Google-only accounts exist

`alembic/versions/bf4109ec3b43_...py:32` sets `hashed_password` back to
`NOT NULL` with no backfill. Will fail the moment any Google-only account
exists. Essentially never exercised in this repo's normal workflow (no
evidence of routine `alembic downgrade` usage) — cosmetic until it matters.

### 9. Redundant unique constraint + index on `google_id` — same migration, line 24

`create_unique_constraint` + a separate `create_index` on the identical
single column — Postgres already builds an implicit unique index backing
the constraint, so the second index is pure waste (double write-path
maintenance, zero query benefit). Mirrors the same existing redundancy on
`users.email`. Pure cleanup, no functional impact.

### 10. Shared `requests.Session` across `asyncio.to_thread` workers — `oauth_service.py:12`

The module-level `Request()` wraps a `requests.Session()` reused across
every concurrent request via the thread pool `asyncio.to_thread` uses.
`requests.Session` isn't documented as safe for concurrent multi-thread use.
Plausible under real concurrent load, hasn't been observed failing, low
priority to chase down without evidence it's actually happening.

## Status

**#1–#4 fixed** (branch `fix/google-oauth-review-findings`):
- #1: `login_or_register_google` now clears `hashed_password` when linking to
  an unverified existing row (`app/services/oauth_service.py`). Covered by
  `tests/unit/test_oauth_service.py::test_login_or_register_google_clears_password_for_unverified_account`;
  the pre-existing "password preserved" test was updated to use an
  already-verified row, which is the only case that should preserve it
  (`test_login_or_register_google_links_verified_password_account`).
- #2–#4: new migration `caf6ae824d45_backfill_lowercase_user_emails.py`
  lowercases every existing mixed-case `users.email`, skipping (and
  printing) any row that would collide with an existing lowercase variant
  rather than guessing which one to keep. Verified manually against a local
  DB with both a clean case and a colliding pair — see PR for the exact
  output.

**#5–#9 fixed** (same branch):
- #5: `verify_google_id_token` now also catches `google.auth.exceptions.GoogleAuthError`
  (the base class `TransportError` and issuer-validation failures actually
  raise), so a transient JWKS-fetch failure surfaces as a clean `ValueError`
  (-> 400) instead of an unhandled 500. Covered by
  `test_verify_google_id_token_wraps_transient_google_auth_error`.
- #6: `verify_google_id_token` now checks for the `email` claim explicitly
  and raises `ValueError` instead of letting `claims["email"]` raise
  `KeyError`. Covered by `test_verify_google_id_token_rejects_missing_email_claim`.
- #7: the new-user insert in `login_or_register_google` now catches
  `IntegrityError` on commit, rolls back, and re-fetches the row the
  concurrent request won instead of surfacing a 500 — the loser of the race
  gets a normal successful login. Covered by
  `test_login_or_register_google_recovers_from_concurrent_insert_race`.
- #8: `bf4109ec3b43`'s `downgrade()` now backfills any `NULL hashed_password`
  row with an unusable placeholder before re-adding the `NOT NULL`
  constraint, so it no longer fails once a Google-only account exists.
  Verified manually: inserted a Google-only user, ran
  `alembic downgrade a06b39fb621e`, confirmed it completed instead of
  raising a not-null violation.
- #9: new migration `d896a3811d5b_drop_redundant_google_id_index.py` drops
  `ix_users_google_id` — `uq_users_google_id`'s implicit unique index already
  covers that column. Verified via `\d users` that only the unique
  constraint's index remains after upgrading.

- #10: the module-level `requests.Session` singleton is replaced with a
  `threading.local()`-scoped `google_requests.Request()` — each
  `asyncio.to_thread` worker thread now gets its own private session
  (created once, reused across calls on that thread) instead of sharing one
  across every concurrent request.

All 10 findings are now resolved.
