"""The profession catalog (scripts/riasec_professions.py) and every data file
keyed off it must agree — a renamed profession has to keep its slug and take
its O*NET vector and content along (PRO-432)."""
import json
from pathlib import Path

from scripts.riasec_professions import KK_NAMES, PROFESSIONS
from scripts.seed_riasec_directions import dedupe_by_title, slugify

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(relative: str):
    return json.loads((_SCRIPTS / relative).read_text(encoding="utf-8"))


def _catalog() -> list[dict]:
    return dedupe_by_title(PROFESSIONS)


def test_slugs_are_unique():
    slugs = [d["slug"] for d in _catalog()]
    assert len(slugs) == len(set(slugs))


def test_renamed_profession_keeps_its_pinned_slug():
    entries = [{"title": "Новое название", "holland_code": "CSE", "slug": "arhivarius"}]
    assert dedupe_by_title(entries) == [{"title": "Новое название", "slug": "arhivarius", "holland_code": "CSE"}]
    assert dedupe_by_title([{"title": "Архивариус", "holland_code": "CSE"}])[0]["slug"] == slugify("Архивариус")


def test_every_direction_has_ru_and_kk_content_by_slug():
    """Content is keyed by slug — a rename that changed the slug would leave
    the direction without a description."""
    slugs = {d["slug"] for d in _catalog()}
    assert {e["slug"] for e in _load("direction_content_review.json")} == slugs
    assert {e["slug"] for e in _load("direction_content_review_kk.json")} == slugs


def test_onet_vectors_point_at_current_titles():
    """Vectors are keyed by the ru title — a stale title silently drops the
    direction back to the code-based fallback in career matching."""
    titles = {p["title"] for p in PROFESSIONS}
    stale = {e["title"] for e in _load("data/our_professions_onet_riasec.json")} - titles
    assert not stale


def test_kk_glossary_matches_the_catalog():
    by_slug = {d["slug"]: d["title"] for d in _catalog()}
    for entry in _load("data/direction_glossary_kk.json"):
        assert entry["name_ru"] == by_slug[entry["slug"]]
        assert entry["name_kk"] == KK_NAMES[entry["name_ru"]]
