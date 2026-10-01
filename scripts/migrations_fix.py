#!/usr/bin/env python3
"""Keep the Alembic history linear across parallel branches (PRO-429).

Two developers branching off the same head each add a migration; git merges
the two files without a conflict, and the result is an Alembic history with
two heads that only blows up at `alembic upgrade head` on deploy. This script
removes that failure mode instead of papering over it with merge migrations.

Commands:

  fix    Re-point this branch's own migrations (the ones the base branch does
         not have yet) so they sit on top of the base branch's head, drop any
         empty merge migration among them (no longer needed), then run every
         `check`. With --commit, commits exactly the files it touched.
  check  Change nothing, just verify (this is what CI runs):
           - exactly one head, every down_revision exists, revision ids unique;
           - no migration that already exists in the base branch was edited,
             deleted or renamed. Those have been applied on dev/prod; editing
             one is what left the dev database's schema out of sync with its
             alembic_version (see e7f4a2c1d9b8). Fix forward with a new
             migration instead.

Only a branch's own migrations are ever rewritten — a migration that has
reached the base branch never is.

Standard library + git only: no database, no app imports, safe to run on the
host. The hooks in .githooks/ call it on `git push`, `git pull`/`git merge`
and `git rebase`; see the "Migrations" section of CLAUDE.md.

Exit codes: 0 = all good, 1 = needs a human (details printed), 3 = files were
fixed (and committed with --commit).
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

VERSIONS_DIR = "alembic/versions"
EXIT_OK, EXIT_ERROR, EXIT_FIXED = 0, 1, 3
PREFIX = "[migrations]"


class MigrationError(Exception):
    """A problem the script cannot (or must not) fix on its own."""


@dataclass
class Migration:
    revision: str
    down_revisions: tuple[str, ...]
    path: str  # repo-relative, forward slashes
    source: str  # LF line endings
    # (first line, last line) 1-based and (start col, end col) as UTF-8 byte
    # offsets of the down_revision *value*, as reported by ast.
    down_lines: tuple[int, int] | None
    down_cols: tuple[int, int] | None
    is_empty_merge: bool


def _run_git(
    root: Path | None, *args: str, check: bool = True, env: dict[str, str] | None = None
) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", env=env
    )
    if check and result.returncode != 0:
        raise MigrationError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def repo_root() -> Path:
    return Path(_run_git(None, "rev-parse", "--show-toplevel").strip())


# ── reading migrations ──────────────────────────────────────────────────────


def _is_pass_only(func: ast.FunctionDef | None) -> bool:
    if func is None:
        return True
    return all(
        isinstance(stmt, ast.Pass)
        or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
        for stmt in func.body
    )


def parse_migration(path: str, source: str) -> Migration | None:
    """None if the file is not a migration (no module-level `revision`)."""
    tree = ast.parse(source, filename=path)
    assignments: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id in ("revision", "down_revision"):
            assignments[target.id] = value
    if "revision" not in assignments:
        return None

    revision = ast.literal_eval(assignments["revision"])
    down_node = assignments.get("down_revision")
    down = ast.literal_eval(down_node) if down_node is not None else None
    if down is None:
        down_revisions: tuple[str, ...] = ()
    elif isinstance(down, str):
        down_revisions = (down,)
    else:
        down_revisions = tuple(down)

    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    return Migration(
        revision=revision,
        down_revisions=down_revisions,
        path=path,
        source=source,
        down_lines=(down_node.lineno, down_node.end_lineno) if down_node is not None else None,
        down_cols=(down_node.col_offset, down_node.end_col_offset) if down_node is not None else None,
        is_empty_merge=len(down_revisions) > 1
        and _is_pass_only(funcs.get("upgrade"))
        and _is_pass_only(funcs.get("downgrade")),
    )


def read_tree_at(root: Path, ref: str) -> dict[str, str]:
    """{path: source} of every migration file in `ref` — one git process for all blobs."""
    listing = _run_git(root, "ls-tree", "-r", ref, "--", f"{VERSIONS_DIR}/")
    entries = []
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        _mode, kind, sha = meta.split()
        if kind == "blob" and path.endswith(".py"):
            entries.append((path, sha))
    if not entries:
        return {}

    batch = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=root,
        input="".join(f"{sha}\n" for _, sha in entries).encode(),
        capture_output=True,
        check=True,
    ).stdout
    sources, pos = {}, 0
    for path, _sha in entries:
        header_end = batch.index(b"\n", pos)
        size = int(batch[pos:header_end].split()[2])
        body = batch[header_end + 1 : header_end + 1 + size]
        pos = header_end + 1 + size + 1  # blob is followed by a newline
        sources[path] = body.decode("utf-8").replace("\r\n", "\n")
    return sources


def read_worktree(root: Path) -> dict[str, str]:
    return {
        f"{VERSIONS_DIR}/{p.name}": p.read_bytes().decode("utf-8").replace("\r\n", "\n")
        for p in sorted((root / VERSIONS_DIR).glob("*.py"))
    }


def build_graph(sources: dict[str, str], problems: list[str]) -> dict[str, Migration]:
    graph: dict[str, Migration] = {}
    for path, source in sorted(sources.items()):
        migration = parse_migration(path, source)
        if migration is None:
            continue
        if migration.revision in graph:
            problems.append(
                f"revision id {migration.revision!r} повторяется: "
                f"{graph[migration.revision].path} и {path}. "
                f"Id создаёт только `alembic revision`, не придумывайте его вручную."
            )
            continue
        graph[migration.revision] = migration
    return graph


def heads_of(graph: dict[str, Migration]) -> list[str]:
    parents = {p for m in graph.values() for p in m.down_revisions}
    return sorted(r for r in graph if r not in parents)


# ── checks ──────────────────────────────────────────────────────────────────


def graph_problems(graph: dict[str, Migration]) -> list[str]:
    problems = []
    for migration in graph.values():
        for parent in migration.down_revisions:
            if parent not in graph:
                problems.append(
                    f"{migration.path}: down_revision {parent!r} не найден среди миграций."
                )
    heads = heads_of(graph)
    if len(heads) != 1:
        problems.append(
            f"Голов {len(heads)} (нужна одна): {', '.join(heads) or '—'}. "
            f"Запустите `python scripts/migrations_fix.py fix`."
        )
    return problems


def immutability_problems(reference: dict[str, str], current: dict[str, str]) -> list[str]:
    """Migrations that are already in the base branch must stay byte-for-byte as they are."""
    problems = []
    for path, source in sorted(reference.items()):
        if path not in current:
            problems.append(f"{path}: уже есть в базовой ветке, но удалена или переименована.")
        elif current[path] != source:
            problems.append(f"{path}: уже есть в базовой ветке, но изменена.")
    if problems:
        problems.append(
            "Эти миграции уже применены на dev/prod — правка или удаление ломает там схему. "
            "Верните файлы как были и исправьте новой миграцией. Если правка осознанная и "
            "согласована, в CI поставьте на PR метку `migration-edit-approved`."
        )
    return problems


# ── fixing ──────────────────────────────────────────────────────────────────


def _first_added_at(root: Path, path: str) -> float:
    """Commit time the file was first added; uncommitted files sort last."""
    out = _run_git(root, "log", "--diff-filter=A", "--format=%ct", "--", path, check=False)
    stamps = out.split()
    return float(stamps[-1]) if stamps else float("inf")


def rewrite_down_revision(migration: Migration, new_parent: str) -> str:
    if migration.down_lines is None or migration.down_cols is None:
        raise MigrationError(f"{migration.path}: нет строки down_revision — нечего перевешивать.")
    lines = migration.source.split("\n")
    first, last = migration.down_lines
    start_col, end_col = migration.down_cols
    first_line, last_line = lines[first - 1].encode(), lines[last - 1].encode()
    quote = "'" if first_line[start_col : start_col + 1] == b"'" else '"'
    lines[first - 1 : last] = [
        first_line[:start_col].decode() + f"{quote}{new_parent}{quote}" + last_line[end_col:].decode()
    ]
    source = "\n".join(lines)
    # Keep the docstring's "Revises:" in sync — a stale one misleads the next
    # person reading the file (c8d2e6a1f470 still says b7e3a5f9c1d4).
    return re.sub(r"^Revises:[^\n]*$", f"Revises: {new_parent}", source, count=1, flags=re.M)


def plan_relink(
    root: Path, current: dict[str, Migration], base: dict[str, Migration]
) -> tuple[dict[str, str], list[str], str]:
    """-> ({path: new source}, [paths to delete], resulting head)."""
    base_heads = heads_of(base)
    if len(base_heads) != 1:
        raise MigrationError(
            f"В базовой ветке {len(base_heads)} голов ({', '.join(base_heads)}) — "
            f"это нужно чинить в самой базовой ветке, не в вашей."
        )
    target = base_heads[0]

    own = {r: m for r, m in current.items() if r not in base}
    removed = set()
    for revision, migration in own.items():
        if len(migration.down_revisions) > 1:
            if not migration.is_empty_merge:
                raise MigrationError(
                    f"{migration.path}: merge-миграция с кодом внутри. Автоматически её не "
                    f"разобрать — перенесите операции в обычную миграцию и удалите merge."
                )
            removed.add(revision)
        elif not migration.down_revisions:
            raise MigrationError(f"{migration.path}: down_revision = None у новой миграции.")
    kept = {r: m for r, m in own.items() if r not in removed}

    def own_parents(migration: Migration) -> list[str]:
        return [p for p in migration.down_revisions if p in kept]

    children: dict[str, list[str]] = defaultdict(list)
    for revision, migration in kept.items():
        for parent in migration.down_revisions:
            if parent not in current:
                raise MigrationError(f"{migration.path}: down_revision {parent!r} не найден.")
        for parent in own_parents(migration):
            children[parent].append(revision)
    for parent, kids in children.items():
        if len(kids) > 1:
            raise MigrationError(
                f"У миграции {parent} в вашей ветке несколько дочерних ({', '.join(sorted(kids))}). "
                f"Выстройте их в одну цепочку вручную (поправьте down_revision)."
            )

    chains = []
    for revision, migration in kept.items():
        if own_parents(migration):
            continue
        chain = [revision]
        while children.get(chain[-1]):
            chain.append(children[chain[-1]][0])
        chains.append(chain)
    if sum(len(c) for c in chains) != len(kept):
        raise MigrationError("Цикл в down_revision среди миграций ветки — разберите вручную.")

    # Several independent chains (e.g. two migrations made off the same head
    # in one branch): stack them in the order they were added.
    chains.sort(key=lambda c: (_first_added_at(root, kept[c[0]].path), kept[c[0]].path))
    changes = {}
    for chain in chains:
        root_migration = kept[chain[0]]
        if root_migration.down_revisions != (target,):
            changes[root_migration.path] = rewrite_down_revision(root_migration, target)
        target = chain[-1]
    return changes, sorted(own[r].path for r in removed), target


# ── commands ────────────────────────────────────────────────────────────────


def commit_paths(root: Path, paths: list[str], message: str) -> None:
    """Commit exactly `paths` on top of HEAD.

    Built from plumbing on a throwaway index instead of `git commit -- paths`:
    that porcelain refuses inside post-merge (git still has MERGE_HEAD there —
    "cannot do a partial commit during a merge"), and this way whatever the
    developer has staged stays staged and out of our commit.
    """
    index = root / _run_git(root, "rev-parse", "--git-path", "migrations_fix.index").strip()
    env = dict(os.environ, GIT_INDEX_FILE=str(index))
    try:
        _run_git(root, "read-tree", "HEAD", env=env)
        for path in paths:
            if (root / path).exists():
                _run_git(root, "update-index", "--add", "--", path, env=env)
            else:
                _run_git(root, "update-index", "--force-remove", "--", path, env=env)
        tree = _run_git(root, "write-tree", env=env).strip()
    finally:
        index.unlink(missing_ok=True)
    sign = ["-S"] if _run_git(root, "config", "--bool", "commit.gpgsign", check=False).strip() == "true" else []
    commit = _run_git(root, "commit-tree", *sign, tree, "-p", "HEAD", "-m", message).strip()
    _run_git(root, "update-ref", "-m", "migrations_fix: relink", "HEAD", commit)
    _run_git(root, "reset", "--quiet", "--", *paths)  # real index := new HEAD for these paths


def default_base(root: Path) -> str:
    if os.environ.get("MIGRATIONS_BASE"):
        return os.environ["MIGRATIONS_BASE"]
    branch = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    # Feature branches and dev itself land in dev; only main is released on its own.
    return "origin/main" if branch == "main" else "origin/dev"


def fetch_base(root: Path, base: str) -> None:
    if not base.startswith("origin/"):
        return
    result = subprocess.run(
        ["git", "fetch", "--quiet", "origin", base.removeprefix("origin/")],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"{PREFIX} не удалось обновить {base} (нет сети?) — сверяюсь с локальной копией.")


def run_checks(
    root: Path, base: str, sources: dict[str, str], allow_modified: bool
) -> list[str]:
    problems: list[str] = []
    graph = build_graph(sources, problems)
    problems += graph_problems(graph)
    if not allow_modified:
        merge_base = _run_git(root, "merge-base", "HEAD", base).strip()
        problems += immutability_problems(read_tree_at(root, merge_base), sources)
    return problems


def report(problems: list[str]) -> int:
    if not problems:
        print(f"{PREFIX} OK: одна голова, влитые миграции не тронуты.")
        return EXIT_OK
    for problem in problems:
        print(f"{PREFIX} ✗ {problem}")
    return EXIT_ERROR


def cmd_check(root: Path, args: argparse.Namespace) -> int:
    return report(run_checks(root, args.base, read_worktree(root), args.allow_modified))


def cmd_fix(root: Path, args: argparse.Namespace) -> int:
    if args.commit:
        dirty = _run_git(root, "status", "--porcelain", "--", VERSIONS_DIR).strip()
        if dirty:
            if args.hook == "pre-push":
                print(f"{PREFIX} в {VERSIONS_DIR} есть незакоммиченные изменения — проверка пропущена, её сделает CI.")
            if args.hook:
                return EXIT_OK
            raise MigrationError(
                f"В {VERSIONS_DIR} есть незакоммиченные изменения — закоммитьте их сначала:\n{dirty}"
            )
    if not args.no_fetch:
        fetch_base(root, args.base)

    worktree = read_worktree(root)
    problems: list[str] = []
    current = build_graph(worktree, problems)
    base = build_graph(read_tree_at(root, args.base), [])
    own = [r for r in current if r not in base]

    missing = sorted(r for r in base if r not in current)
    if missing and own:
        if args.hook == "post":
            return EXIT_OK  # merged something other than the base; nothing to say yet
        raise MigrationError(
            f"В {args.base} появились миграции, которых нет в вашей ветке ({', '.join(missing)}). "
            f"Подтяните их: `git pull origin {args.base.removeprefix('origin/')}` — "
            f"ваши миграции перевесятся автоматически. Потом снова git push."
        )
    if problems:
        return report(problems)

    changes, removals, new_head = plan_relink(root, current, base) if own else ({}, [], "")
    if not changes and not removals:
        return report(run_checks(root, args.base, worktree, args.allow_modified))

    for path, new_source in changes.items():
        file = root / path
        crlf = b"\r\n" in file.read_bytes()
        data = new_source.replace("\n", "\r\n") if crlf else new_source
        file.write_bytes(data.encode("utf-8"))
        print(f"{PREFIX} перевешена: {path}")
    for path in removals:
        (root / path).unlink()
        print(f"{PREFIX} удалена лишняя merge-миграция: {path}")

    problems = run_checks(root, args.base, read_worktree(root), args.allow_modified)
    if problems:
        return report(problems)

    touched = sorted(changes) + removals
    if args.commit:
        commit_paths(
            root,
            touched,
            f"chore(alembic): relink migrations onto {args.base} head\n\n"
            f"Automated by scripts/migrations_fix.py. New head: {new_head}.",
        )
        print(f"{PREFIX} изменения закоммичены.")
    print(
        f"{PREFIX} Новая голова: {new_head}. Если вы уже применяли свою миграцию в локальной БД, "
        f"пересоздайте локальную БД — иначе Alembic пропустит миграции из {args.base}."
    )
    return EXIT_FIXED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", nargs="?", choices=("fix", "check"), default="fix")
    parser.add_argument("--base", help="базовая ветка (по умолчанию origin/dev; на main — origin/main)")
    parser.add_argument("--commit", action="store_true", help="закоммитить исправление")
    parser.add_argument("--no-fetch", action="store_true", help="не делать git fetch базовой ветки")
    parser.add_argument(
        "--allow-modified",
        action="store_true",
        help="разрешить правку уже влитых миграций (только по согласованию)",
    )
    parser.add_argument("--hook", choices=("pre-push", "post"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not sys.stdout.isatty():
        # Git hooks pipe our output; on Windows the pipe defaults to cp1251,
        # which Git Bash then shows as mojibake.
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        root = repo_root()
        args.base = args.base or default_base(root)
        return cmd_check(root, args) if args.command == "check" else cmd_fix(root, args)
    except MigrationError as error:
        print(f"{PREFIX} ✗ {error}")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
