"""Sync the АСТУР v1 bank row with app/data/astur_bank_v1.json (PRO-442)

The 12 «Классификации» items were rewritten in place in the source file: all
six words now come from one broad category and exactly one pair shares a
narrower feature (the original АСТУР format), instead of a pair among random
household objects. The v1 row was inserted from that file by `a7c3e1f9b2d4`
and is never re-read, so already-migrated databases need this sync; on a fresh
database it is a no-op (the row already matches the file).

An open draft that is still an untouched copy of the old v1 is synced too —
publishing it would otherwise silently bring the old words back. A draft
with admin edits is left alone: publishing it asks to confirm the 12 changed
classification keys anyway.

Completed attempts keep their frozen `result_snapshot`; only attempts
finalized after this run are scored with the new keys.

Downgrade is a no-op: the previous words live only in git history.

Revision ID: 624c5e6208ee
Revises: e7f4a2c1d9b8
Create Date: 2026-09-30 06:13:18.544410

"""
import hashlib
import json
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '624c5e6208ee'
down_revision: Union[str, None] = 'e7f4a2c1d9b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_V1_PATH = Path(__file__).resolve().parents[2] / "app" / "data" / "astur_bank_v1.json"
# content hash of v1 before this migration (the file as of a7c3e1f9b2d4)
_OLD_V1_HASH = "fe7e5127744300935ccab117038032766cd0ac01c25558e2dfa91fa8ca0122e4"


def _hash(document: dict) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upgrade() -> None:
    document = json.loads(_V1_PATH.read_text(encoding="utf-8"))
    versions = sa.table(
        "astur_bank_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("document", postgresql.JSONB()),
        sa.column("content_hash", sa.String()),
    )
    op.execute(versions.update().where(versions.c.version == 1).values(document=document, content_hash=_hash(document)))

    drafts = op.get_bind().execute(
        sa.select(versions.c.id, versions.c.document).where(sa.cast(versions.c.status, sa.String()) == "draft")
    )
    for draft_id, draft_document in drafts.all():
        if _hash(draft_document) == _OLD_V1_HASH:
            op.execute(versions.update().where(versions.c.id == draft_id).values(document=document))


def downgrade() -> None:
    pass
