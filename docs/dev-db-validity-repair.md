# One-off repair: dev DB drift blocking `b8911a00feb0` (remove_validity)

## Symptom

CD deploy to dev fails at the `alembic upgrade head` step with:

```
sqlalchemy.exc.DBAPIError: ... InvalidTextRepresentationError:
invalid input value for enum question_instrument_enum: "validity"
[SQL: DELETE FROM questions WHERE instrument = 'validity']
```

## Cause

Dev's real database schema drifted from what `alembic_version` claims: the
validity data model (`d4a7e21b9f30_validity_module_data_model.py` /
`c9f21d7e4a3b_psych_block_foundation.py`) never fully landed there, even
though history says it's an ancestor of dev's recorded revision. `question_instrument_enum`
has no `'validity'` label, and `assessment_validity` / `validity_calibration_log`
tables, `analysis_results.validity`, `questions.validity_meta` /
`questions.validity_role` don't exist — but `b8911a00feb0` (already merged
into `dev`) unconditionally tries to delete/drop all of that.

`migrations_fix.py` (PRO-429) forbids editing an already-merged migration
file, and rightly so — but a crash *inside* an already-merged migration can't
be fixed forward with a later one (the deploy never reaches it). The fix is
to repair the one drifted database directly, once, so the original migration
finds what it expects.

## Fix (run once against the real dev DB, before the next deploy)

```bash
docker exec -i profi_db_dev sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < repair_validity.sql
```

`repair_validity.sql`:

```sql
BEGIN;

CREATE TYPE validity_role_enum AS ENUM ('sd_key', 'infrequency');
CREATE TYPE sd_level_enum AS ENUM ('ok', 'social_desirability', 'high');
CREATE TYPE traffic_light_enum AS ENUM ('green', 'yellow', 'red');

ALTER TYPE question_instrument_enum ADD VALUE IF NOT EXISTS 'validity';

COMMIT;

-- ALTER TYPE ... ADD VALUE cannot run inside the same transaction as its
-- first use, so the table/column DDL that references these types is a
-- separate transaction.
BEGIN;

ALTER TABLE questions ADD COLUMN validity_role validity_role_enum;
ALTER TABLE questions ADD COLUMN validity_meta JSONB;
ALTER TABLE analysis_results ADD COLUMN validity JSONB;

CREATE TABLE validity_calibration_log (
    id UUID NOT NULL,
    assessment_id UUID NOT NULL,
    sd_raw INTEGER NOT NULL,
    sd_level sd_level_enum NOT NULL,
    longstring_max INTEGER NOT NULL,
    irv DOUBLE PRECISION NOT NULL,
    infrequency_failed INTEGER NOT NULL,
    careless_flag BOOLEAN NOT NULL,
    traffic_light traffic_light_enum NOT NULL,
    age_group age_group_enum NOT NULL,
    thresholds_version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT validity_calibration_log_pkey PRIMARY KEY (id),
    CONSTRAINT validity_calibration_log_assessment_id_fkey FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE
);
CREATE INDEX ix_validity_calibration_log_assessment_id ON validity_calibration_log (assessment_id);

CREATE TABLE assessment_validity (
    id UUID NOT NULL,
    assessment_id UUID NOT NULL,
    sd_raw INTEGER NOT NULL,
    sd_level sd_level_enum NOT NULL,
    longstring_max INTEGER NOT NULL,
    irv DOUBLE PRECISION NOT NULL,
    infrequency_failed INTEGER NOT NULL,
    careless_flag BOOLEAN DEFAULT false NOT NULL,
    traffic_light traffic_light_enum NOT NULL,
    details JSONB DEFAULT '{}'::jsonb NOT NULL,
    rt_ms JSONB,
    thresholds_version INTEGER NOT NULL,
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT assessment_validity_pkey PRIMARY KEY (id),
    CONSTRAINT ck_assessment_validity_sd_raw_range CHECK (sd_raw >= 0 AND sd_raw <= 20),
    CONSTRAINT assessment_validity_assessment_id_fkey FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE,
    CONSTRAINT uq_assessment_validity_assessment_id UNIQUE (assessment_id)
);
CREATE UNIQUE INDEX ix_assessment_validity_assessment_id ON assessment_validity (assessment_id);

COMMIT;
```

This SQL was generated from `b8911a00feb0`'s own `downgrade()` (via
`alembic downgrade b8911a00feb0:a3e28145799b --sql`) plus the enum types from
`d4a7e21b9f30_validity_module_data_model.py` — it recreates exactly what the
unedited `upgrade()` expects to find and remove. After running it, deploy
normally: `alembic upgrade head` runs the original migration, which deletes
the (zero) `validity` rows and drops everything back out, ending in the same
state a healthy database reaches on its own.

## Verified

Reproduced against a `pg_dump --schema-only` of the real dev DB (2026-09-28),
stamped to dev's actual recorded revision (`a3e28145799b`):

- Without this repair: `alembic upgrade head` fails exactly as in the CD log above.
- With this repair, then the original (unedited) `b8911a00feb0`: `alembic upgrade head`
  reaches `head` cleanly, a rerun is a no-op, `alembic check` shows no drift
  from this repair, all `cd.yml`/`cd-dev.yml` seed scripts succeed, and
  `pytest tests` passes in full (1051 passed).

## Related

- `e7f4a2c1d9b8` — a similar (but forward-only, git-tracked) repair for a
  different piece of the same underlying drift: `consents` and
  `analysis_results.psychoemotional` from `c9f21d7e4a3b`. That one could be a
  normal migration because it only ever *adds* missing structure and never
  needs to run before an already-merged step.
