import math

from app.core.axes import AXIS_CODES
from app.schemas.akinator_question import AkinatorQuestionCreate
from scripts.seed_akinator_content import PROFESSIONS, QUESTIONS, SECTIONS

# Calibration-pass guard: professions whose profiles are this cosine-similar
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
    assert len(SECTIONS) == 16
    assert len(PROFESSIONS) == 67
    # 41 original + 4 resolves_pair disambiguators added in the calibration pass.
    assert len(QUESTIONS) == 45


def test_profession_slugs_are_unique():
    slugs = [p["slug"] for p in PROFESSIONS]
    assert len(slugs) == len(set(slugs))


def test_section_slugs_are_unique():
    slugs = [s["slug"] for s in SECTIONS]
    assert len(slugs) == len(set(slugs))


def test_every_profession_points_to_a_known_section():
    section_slugs = {s["slug"] for s in SECTIONS}
    for prof in PROFESSIONS:
        assert prof["section"] in section_slugs, prof["slug"]


def test_every_profession_has_a_non_empty_profile():
    for prof in PROFESSIONS:
        assert prof["profile"], f"{prof['slug']}: empty profile"


def test_label_junior_is_a_simpler_distinct_string_where_set():
    """Calibration pass: label_junior exists to swap technical/unfamiliar
    profession names (e.g. "Хирург") for a friendlier everyday word ("Врач")
    when talking to junior — it must actually say something different, not
    just repeat `name`."""
    for prof in PROFESSIONS:
        label = prof.get("label_junior")
        if label is None:
            continue
        assert label.strip(), f"{prof['slug']}: label_junior is blank"
        assert label != prof["name"], f"{prof['slug']}: label_junior duplicates name"


def test_every_profession_profile_uses_valid_axis_codes_and_values():
    for prof in PROFESSIONS:
        for code, value in prof["profile"].items():
            assert code in AXIS_CODES, f"{prof['slug']}: unknown axis '{code}'"
            assert value in (-2, -1, 1, 2), f"{prof['slug']}: bad value {code}={value}"


def test_every_question_passes_schema_and_axis_validation():
    """AC1: 41 AkinatorQuestion entries with valid axis_weights."""
    for q in QUESTIONS:
        AkinatorQuestionCreate.model_validate({**q, "is_active": True})


def test_every_resolves_pair_references_known_professions():
    profession_slugs = {p["slug"] for p in PROFESSIONS}
    for q in QUESTIONS:
        if q["resolves_pair"] is None:
            continue
        for slug in q["resolves_pair"]:
            assert slug in profession_slugs, f"order {q['order']}: unknown profession '{slug}'"


def test_question_orders_are_unique_and_sequential():
    orders = [q["order"] for q in QUESTIONS]
    assert orders == list(range(len(QUESTIONS)))


def test_highly_similar_professions_have_a_disambiguating_question():
    """Calibration-pass regression guard: any two professions whose profiles
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
    for i in range(len(PROFESSIONS)):
        for j in range(i + 1, len(PROFESSIONS)):
            prof_a, prof_b = PROFESSIONS[i], PROFESSIONS[j]
            similarity = _cosine(prof_a["profile"], prof_b["profile"])
            if similarity < SIMILARITY_COVERAGE_THRESHOLD:
                continue
            if frozenset((prof_a["slug"], prof_b["slug"])) not in covered_pairs:
                uncovered.append((round(similarity, 3), prof_a["slug"], prof_b["slug"]))

    assert not uncovered, f"profession pairs too similar with no resolves_pair coverage: {uncovered}"
