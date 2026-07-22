#!/usr/bin/env python3
"""Lookup canonical akinator slugs for an informal specialty query.

Usage:
    python scripts/lookup_specialty_alias.py <query>

Examples:
    python scripts/lookup_specialty_alias.py devops
    python scripts/lookup_specialty_alias.py DevOps
    python scripts/lookup_specialty_alias.py ml
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.specialty_aliases import SPECIALTY_ALIASES  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: lookup_specialty_alias.py <query>")
        sys.exit(1)

    query = " ".join(sys.argv[1:]).lower().strip()
    if not query:
        print("Usage: lookup_specialty_alias.py <query>")
        sys.exit(1)

    found = {alias: slugs for alias, slugs in SPECIALTY_ALIASES.items() if query in alias}

    if not found:
        print(f"Not found: {query!r}")
        print(f"\nAvailable aliases ({len(SPECIALTY_ALIASES)} total):")
        for alias in sorted(SPECIALTY_ALIASES):
            print(f"  {alias}")
    else:
        for alias, slugs in sorted(found.items()):
            print(f"{alias!r} -> {slugs}")


if __name__ == "__main__":
    main()
