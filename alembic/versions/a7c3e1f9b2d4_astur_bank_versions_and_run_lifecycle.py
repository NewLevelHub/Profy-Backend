"""АСТУР bank versions + attempt lifecycle (PRO-427)

- `astur_bank_versions`: immutable published bank versions (text + keys +
  scoring methods + timers). Version 1 is the pre-PRO-427 bank, loaded from
  `app/data/astur_bank_v1.json` — exactly the keys every existing attempt was
  scored with.
- `astur_runs`: status (in_progress / completed / invalidated), pinned bank
  version, completion time, scoring version, content hash, frozen result
  snapshot, protocol quality, client timezone. At most one in_progress
  attempt per assessment.
  Existing rows: every attempt gets bank version 1; an attempt with every
  subtest submitted → completed (completed_at = created_at, the only known
  time); the newest unfinished attempt of an assessment → in_progress (can
  be resumed); older unfinished ones → invalidated. Snapshots of completed
  legacy attempts are frozen afterwards by
  `scripts/backfill_astur_legacy_snapshots.py` (idempotent, run on deploy).
  The never-persisted derived columns (raw_score, subtest_scores, spn_group,
  recommended_profile, lability_*_accuracy — always computed on read) are
  dropped. No answer data is touched.
- `analysis_results.psych_ai_analysis_fingerprint`: input fingerprint of the
  cached psychologist AI analysis; NULL = stale.

Rollback: `alembic downgrade` restores the previous astur_runs shape
(derived columns come back empty, as they always were), drops the new
columns and the versions table. Raw answers survive both directions.

Revision ID: a7c3e1f9b2d4
Revises: d4a7c2e9f1b3
Create Date: 2026-09-25 00:00:00.000000

"""
import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c3e1f9b2d4"
down_revision: str | None = "d4a7c2e9f1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_V1_PATH = Path(__file__).resolve().parents[2] / "app" / "data" / "astur_bank_v1.json"
_CONTENT_SUBTESTS = (
    "awareness", "analogies", "classification", "generalization",
    "logical_schemas", "numeric_series", "geometric_figures",
)
_QUICK_COMMANDS = 8

bank_status = postgresql.ENUM("draft", "published", name="astur_bank_version_status_enum", create_type=False)
run_status = postgresql.ENUM("in_progress", "completed", "invalidated", name="astur_run_status_enum", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    bank_status.create(bind, checkfirst=True)
    run_status.create(bind, checkfirst=True)

    op.create_table(
        "astur_bank_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=True, unique=True),
        sa.Column("status", bank_status, nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column(
            "based_on_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("astur_bank_versions.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_astur_bank_versions_single_draft", "astur_bank_versions", ["status"],
        unique=True, postgresql_where=sa.text("status = 'draft'"),
    )

    document = json.loads(_V1_PATH.read_text(encoding="utf-8"))
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    v1_id = uuid.uuid4()
    versions = sa.table(
        "astur_bank_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.Integer()),
        sa.column("status", bank_status),
        sa.column("document", postgresql.JSONB()),
        sa.column("content_hash", sa.String()),
        sa.column("notes", sa.Text()),
        sa.column("published_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(versions, [{
        "id": v1_id,
        "version": 1,
        "status": "published",
        "document": document,
        "content_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "notes": "Банк до PRO-427 (черновик v1 из спецификации), перенесён без изменений.",
        "published_at": datetime.now(timezone.utc),
    }])

    op.add_column("astur_runs", sa.Column("status", run_status, nullable=False, server_default="in_progress"))
    op.add_column("astur_runs", sa.Column("bank_version_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("astur_runs", sa.Column("client_timezone", sa.String(64), nullable=True))
    op.add_column("astur_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("astur_runs", sa.Column("scoring_version", sa.String(32), nullable=True))
    op.add_column("astur_runs", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("astur_runs", sa.Column("result_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("astur_runs", sa.Column("protocol_quality", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.execute(sa.text("UPDATE astur_runs SET bank_version_id = CAST(:v1 AS uuid)").bindparams(v1=str(v1_id)))
    subtests_array = "ARRAY[" + ", ".join(f"'{k}'" for k in _CONTENT_SUBTESTS) + "]"
    op.execute(f"""
        UPDATE astur_runs
        SET status = 'completed', completed_at = created_at
        WHERE answers ?& {subtests_array}
          AND (SELECT count(*) FROM jsonb_object_keys(lability_answers)) >= {_QUICK_COMMANDS}
    """)
    op.execute("""
        UPDATE astur_runs r
        SET status = 'invalidated'
        WHERE r.status = 'in_progress'
          AND EXISTS (
              SELECT 1 FROM astur_runs newer
              WHERE newer.assessment_id = r.assessment_id
                AND (newer.created_at, newer.id) > (r.created_at, r.id)
          )
    """)
    op.alter_column("astur_runs", "bank_version_id", nullable=False)
    op.create_foreign_key(
        "fk_astur_runs_bank_version_id", "astur_runs", "astur_bank_versions",
        ["bank_version_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index(
        "uq_astur_runs_single_active", "astur_runs", ["assessment_id"],
        unique=True, postgresql_where=sa.text("status = 'in_progress'"),
    )

    for column in (
        "raw_score", "subtest_scores", "spn_group", "recommended_profile",
        "lability_first_half_accuracy", "lability_second_half_accuracy",
    ):
        op.drop_column("astur_runs", column)

    op.add_column("analysis_results", sa.Column("psych_ai_analysis_fingerprint", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_results", "psych_ai_analysis_fingerprint")

    op.add_column("astur_runs", sa.Column("raw_score", sa.Integer(), nullable=True))
    op.add_column(
        "astur_runs",
        sa.Column("subtest_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("astur_runs", sa.Column("spn_group", sa.Integer(), nullable=True))
    op.add_column(
        "astur_runs",
        sa.Column("recommended_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("astur_runs", sa.Column("lability_first_half_accuracy", sa.Float(), nullable=True))
    op.add_column("astur_runs", sa.Column("lability_second_half_accuracy", sa.Float(), nullable=True))

    op.drop_index("uq_astur_runs_single_active", table_name="astur_runs")
    op.drop_constraint("fk_astur_runs_bank_version_id", "astur_runs", type_="foreignkey")
    for column in (
        "protocol_quality", "result_snapshot", "content_hash", "scoring_version",
        "completed_at", "client_timezone", "bank_version_id", "status",
    ):
        op.drop_column("astur_runs", column)

    op.drop_index("uq_astur_bank_versions_single_draft", table_name="astur_bank_versions")
    op.drop_table("astur_bank_versions")
    bind = op.get_bind()
    run_status.drop(bind, checkfirst=True)
    bank_status.drop(bind, checkfirst=True)
