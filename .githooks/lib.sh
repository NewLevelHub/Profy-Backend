# Shared by the hooks in this folder. Enable once per clone (start.sh does it):
#   git config core.hooksPath .githooks
# Turn the migration hooks off for one command: MIGRATIONS_HOOKS=0 git push

find_python() {
  for candidate in python3 python py; do
    # `python3` on Windows can be the Microsoft Store stub, which exists but
    # can't run anything — so actually run it rather than trusting `command -v`.
    if "$candidate" -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

run_migrations_fix() {
  if [ "${MIGRATIONS_HOOKS:-1}" = "0" ]; then
    return 0
  fi
  if ! python_bin=$(find_python); then
    echo "[migrations] Python 3.9+ не найден — проверка миграций пропущена (её сделает CI)." >&2
    return 0
  fi
  "$python_bin" "$(git rev-parse --show-toplevel)/scripts/migrations_fix.py" "$@"
}
