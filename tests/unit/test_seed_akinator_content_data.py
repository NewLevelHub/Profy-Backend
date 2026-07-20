import math

from app.core.axes import AXIS_CODES
from app.schemas.akinator_question import AkinatorQuestionCreate
from scripts.seed_akinator_content import QUESTIONS, SECTIONS, SPECIALTIES

# Calibration-pass guard: specialties whose profiles are this cosine-similar
# are easy for the engine to confuse and MUST have a resolves_pair question
# covering both, or cluster_resolver_service has nothing to disambiguate them
# with (see app/services/cluster_resolver_service.get_eligible_questions,
# which requires >=2 of a resolves_pair's slugs to be in the cluster).
SIMILARITY_COVERAGE_THRESHOLD = 0.85


def _cosine(a: dict[str, int], b: dict[str, int]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def test_counts_match_acceptance_criteria():
    assert len(SECTIONS) == 13
    assert len(SPECIALTIES) == 38
    assert len(QUESTIONS) == 40


def test_specialty_slugs_are_unique():
    slugs = [p["slug"] for p in SPECIALTIES]
    assert len(slugs) == len(set(slugs))


def test_section_slugs_are_unique():
    slugs = [s["slug"] for s in SECTIONS]
    assert len(slugs) == len(set(slugs))


def test_every_specialty_points_to_a_known_section():
    section_slugs = {s["slug"] for s in SECTIONS}
    for spec in SPECIALTIES:
        assert spec["section"] in section_slugs, spec["slug"]


def test_every_specialty_has_a_non_empty_profile():
    for spec in SPECIALTIES:
        assert spec["profile"], f"{spec['slug']}: empty profile"


def test_every_specialty_has_a_non_empty_professions_list():
    """Specialty pivot: `professions` is what the client shows under the
    matched specialty (e.g. Software Engineer -> Backend/Frontend/QA/...) —
    an empty list here would silently break that product requirement."""
    for spec in SPECIALTIES:
        assert spec.get("professions"), f"{spec['slug']}: missing/empty professions list"


def test_label_junior_is_a_simpler_distinct_string_where_set():
    """Calibration pass: label_junior exists to swap technical/unfamiliar
    specialty names (e.g. "Лечебное дело") for a friendlier everyday word
    ("Врач") when talking to junior — it must actually say something
    different, not just repeat `name`."""
    for spec in SPECIALTIES:
        label = spec.get("label_junior")
        if label is None:
            continue
        assert label.strip(), f"{spec['slug']}: label_junior is blank"
        assert label != spec["name"], f"{spec['slug']}: label_junior duplicates name"


def test_every_specialty_profile_uses_valid_axis_codes_and_values():
    for spec in SPECIALTIES:
        for code, value in spec["profile"].items():
            assert code in AXIS_CODES, f"{spec['slug']}: unknown axis '{code}'"
            assert value in (-2, -1, 1, 2), f"{spec['slug']}: bad value {code}={value}"


def test_every_question_passes_schema_and_axis_validation():
    """AC1: every AkinatorQuestion entry has valid axis_weights."""
    for q in QUESTIONS:
        AkinatorQuestionCreate.model_validate({**q, "is_active": True})


def test_every_resolves_pair_references_known_specialties():
    specialty_slugs = {p["slug"] for p in SPECIALTIES}
    for q in QUESTIONS:
        if q["resolves_pair"] is None:
            continue
        for slug in q["resolves_pair"]:
            assert slug in specialty_slugs, f"order {q['order']}: unknown specialty '{slug}'"


def test_question_orders_are_unique():
    """Specialty pivot: retired question orders leave gaps in the sequence
    (e.g. 22, 23, 25 are missing) — order values are no longer contiguous,
    only unique."""
    orders = [q["order"] for q in QUESTIONS]
    assert len(orders) == len(set(orders))


def test_highly_similar_specialties_have_a_disambiguating_question():
    """Calibration-pass regression guard: any two specialties whose profiles
    are >=SIMILARITY_COVERAGE_THRESHOLD cosine-similar must appear together
    in at least one resolves_pair — otherwise the engine (and the cluster
    resolver) has no way to tell them apart."""
    covered_pairs: set[frozenset[str]] = set()
    for q in QUESTIONS:
        pair = q["resolves_pair"]
        if not pair:
            continue
        for slug_a in pair:
            for slug_b in pair:
                if slug_a != slug_b:
                    covered_pairs.add(frozenset((slug_a, slug_b)))

    uncovered = []
    for i in range(len(SPECIALTIES)):
        for j in range(i + 1, len(SPECIALTIES)):
            spec_a, spec_b = SPECIALTIES[i], SPECIALTIES[j]
            similarity = _cosine(spec_a["profile"], spec_b["profile"])
            if similarity < SIMILARITY_COVERAGE_THRESHOLD:
                continue
            if frozenset((spec_a["slug"], spec_b["slug"])) not in covered_pairs:
                uncovered.append((round(similarity, 3), spec_a["slug"], spec_b["slug"]))

    assert not uncovered, f"specialty pairs too similar with no resolves_pair coverage: {uncovered}"
