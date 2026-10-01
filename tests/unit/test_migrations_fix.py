"""scripts/migrations_fix.py (PRO-429) against throwaway git repos.

Each test builds a tiny repo with a `dev` branch and a feature branch holding
fake-but-parseable Alembic migrations, then runs the script the way the hooks
and CI do (a subprocess inside that repo, `--base dev --no-fetch`).
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrations_fix.py"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _migration(revision: str, down, body: str = "    op.execute('select 1')") -> str:
    down_repr = repr(down)
    revises = ", ".join(down) if isinstance(down, tuple) else down
    return (
        f'"""{revision}\n\nRevision ID: {revision}\nRevises: {revises}\n"""\n'
        "from typing import Sequence, Union\n\nfrom alembic import op\n\n"
        f"revision: str = {revision!r}\n"
        f"down_revision: Union[str, None] = {down_repr}\n\n\n"
        f"def upgrade() -> None:\n{body}\n\n\n"
        "def downgrade() -> None:\n    pass\n"
    )


class Repo:
    def __init__(self, path: Path):
        self.path = path
        self.git("init", "-q", "-b", "dev")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("config", "core.autocrlf", "false")
        (path / "alembic" / "versions").mkdir(parents=True)

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.path, check=True, capture_output=True, text=True
        ).stdout

    def add(self, revision: str, down, **kw) -> Path:
        file = self.path / "alembic" / "versions" / f"{revision}_m.py"
        file.write_bytes(_migration(revision, down, **kw).encode())
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"add {revision}")
        return file

    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--base", "dev", "--no-fetch"],
            cwd=self.path,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def down_of(self, revision: str) -> str:
        text = (self.path / "alembic" / "versions" / f"{revision}_m.py").read_text(encoding="utf-8")
        return next(l for l in text.splitlines() if l.startswith("down_revision"))


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    r.add("aaa", None)
    return r


def test_clean_branch_passes(repo: Repo):
    repo.git("checkout", "-q", "-b", "feature")
    repo.add("bbb", "aaa")
    assert repo.run("check").returncode == 0
    assert repo.run("fix").returncode == 0


def test_parallel_migration_is_relinked_after_pulling_dev(repo: Repo):
    repo.git("checkout", "-q", "-b", "feature")
    repo.add("fff", "aaa")
    repo.git("checkout", "-q", "dev")
    repo.add("ddd", "aaa")  # a colleague's migration lands in dev meanwhile
    repo.git("checkout", "-q", "feature")
    repo.git("merge", "-q", "--no-edit", "dev")

    assert repo.run("check").returncode == 1  # two heads

    result = repo.run("fix", "--commit")
    assert result.returncode == 3, result.stdout
    assert repo.down_of("fff") == "down_revision: Union[str, None] = 'ddd'"
    text = (repo.path / "alembic/versions/fff_m.py").read_text(encoding="utf-8")
    assert "Revises: ddd" in text
    assert "relink migrations" in repo.git("log", "-1", "--format=%s")
    assert repo.git("status", "--porcelain") == ""
    assert repo.run("check").returncode == 0


def test_own_chain_is_moved_as_a_whole(repo: Repo):
    repo.git("checkout", "-q", "-b", "feature")
    repo.add("f1", "aaa")
    repo.add("f2", "f1")
    repo.git("checkout", "-q", "dev")
    repo.add("ddd", "aaa")
    repo.git("checkout", "-q", "feature")
    repo.git("merge", "-q", "--no-edit", "dev")

    assert repo.run("fix").returncode == 3
    assert "'ddd'" in repo.down_of("f1")
    assert "'f1'" in repo.down_of("f2")  # inner link untouched


def test_empty_merge_migration_is_dropped(repo: Repo):
    repo.git("checkout", "-q", "-b", "feature")
    repo.add("fff", "aaa")
    repo.git("checkout", "-q", "dev")
    repo.add("ddd", "aaa")
    repo.git("checkout", "-q", "feature")
    repo.git("merge", "-q", "--no-edit", "dev")
    repo.add("mmm", ("ddd", "fff"), body="    pass")  # what `alembic merge heads` makes

    assert repo.run("fix", "--commit").returncode == 3
    assert not (repo.path / "alembic/versions/mmm_m.py").exists()
    assert "'ddd'" in repo.down_of("fff")
    assert repo.run("check").returncode == 0


def test_push_blocked_while_branch_misses_dev_migrations(repo: Repo):
    repo.git("checkout", "-q", "-b", "feature")
    repo.add("fff", "aaa")
    repo.git("checkout", "-q", "dev")
    repo.add("ddd", "aaa")
    repo.git("checkout", "-q", "feature")

    result = repo.run("fix", "--commit", "--hook", "pre-push")
    assert result.returncode == 1
    assert "git pull origin dev" in result.stdout
    # post-merge/post-rewrite stay silent in that state
    assert repo.run("fix", "--commit", "--hook", "post").returncode == 0


def test_editing_a_merged_migration_is_rejected(repo: Repo):
    repo.git("checkout", "-q", "-b", "feature")
    file = repo.path / "alembic/versions/aaa_m.py"
    file.write_text(file.read_text(encoding="utf-8").replace("select 1", "select 2"), encoding="utf-8")
    repo.git("commit", "-qam", "edit merged migration")

    result = repo.run("check")
    assert result.returncode == 1
    assert "aaa_m.py" in result.stdout
    assert repo.run("check", "--allow-modified").returncode == 0


def test_deleting_a_merged_migration_is_rejected(repo: Repo):
    repo.add("bbb", "aaa")
    repo.git("checkout", "-q", "-b", "feature")
    repo.git("rm", "-q", "alembic/versions/bbb_m.py")
    repo.git("commit", "-qm", "drop merged migration")
    assert repo.run("check").returncode == 1


def test_duplicate_revision_id_is_rejected(repo: Repo):
    repo.git("checkout", "-q", "-b", "feature")
    repo.add("bbb", "aaa")
    dup = repo.path / "alembic/versions/bbb_copy.py"
    dup.write_bytes(_migration("bbb", "aaa").encode())
    repo.git("add", "-A")
    repo.git("commit", "-qm", "dup")
    result = repo.run("check")
    assert result.returncode == 1
    assert "повторяется" in result.stdout


def test_crlf_files_keep_crlf(repo: Repo):
    repo.git("checkout", "-q", "-b", "feature")
    file = repo.add("fff", "aaa")
    file.write_bytes(file.read_bytes().replace(b"\n", b"\r\n"))
    repo.git("commit", "-qam", "crlf")
    repo.git("checkout", "-q", "dev")
    repo.add("ddd", "aaa")
    repo.git("checkout", "-q", "feature")
    repo.git("merge", "-q", "--no-edit", "dev")

    assert repo.run("fix").returncode == 3
    data = file.read_bytes()
    assert b"'ddd'" in data and b"\r\n" in data and b"\r\r" not in data
