"""mac_sessions: enforce one session per assessment (fixes a race)

`get_or_create_session` (mac_service.py) did SELECT-then-INSERT with no DB
constraint — two near-simultaneous requests (React StrictMode double-firing
the mount effect in dev, or any client retry) can both miss the existing row
and each INSERT their own session. `_build_mac_section` then does
`scalar_one_or_none()` on `assessment_id`, which raises `MultipleResultsFound`
on a duplicate — swallowed by the psych-block isolation try/except, so the
symptom is silent: the psychologist just sees `mac: null`, no error anywhere.

Dedup first (a UNIQUE constraint can't be added over violating rows): for
every assessment_id with more than one session, keep the one with the most
`mac_responses` (tie-break: earliest `started_at`) and delete the rest —
`mac_responses`/`mac_notes` cascade off `mac_sessions.id`, so a duplicate
with no responses just disappears cleanly.

Revision ID: b7e3a5f9c1d4
Revises: a4c8f19e6d2b
Create Date: 2026-09-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7e3a5f9c1d4"
down_revision: Union[str, None] = "a4c8f19e6d2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEDUP_SQL = """
DELETE FROM mac_sessions WHERE id IN (
    SELECT id FROM (
        SELECT
            s.id,
            ROW_NUMBER() OVER (
                PARTITION BY s.assessment_id
                ORDER BY (SELECT count(*) FROM mac_responses r WHERE r.session_id = s.id) DESC,
                         s.started_at ASC
            ) AS rn
        FROM mac_sessions s
    ) ranked
    WHERE rn > 1
)
"""


def upgrade() -> None:
    op.execute(_DEDUP_SQL)
    op.create_unique_constraint(
        "uq_mac_sessions_assessment_id", "mac_sessions", ["assessment_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_mac_sessions_assessment_id", "mac_sessions", type_="unique")
