"""PRO-338 Ф2.2 — content integrity for belbin_bank.py. No DB involved
(Belbin has no Question-model content, unlike every other bank in this
codebase — see that module's docstring), mirrors the other *_bank.py
tests' convention where it still applies."""
from scripts.belbin_bank import BLOCK_TOTAL, INSTRUCTION, ITEM_ROLE, ROLES, SECTIONS, TOTAL

_SECTION_NAMES = ["I", "II", "III", "IV", "V", "VI", "VII"]


def test_has_exactly_7_sections_of_8_items() -> None:
    assert [s["section"] for s in SECTIONS] == _SECTION_NAMES
    for section in SECTIONS:
        assert len(section["items"]) == 8


def test_totals_are_10_per_block_and_70_overall() -> None:
    assert BLOCK_TOTAL == 10
    assert TOTAL == 70


def test_every_item_has_a_role_from_the_8_role_set() -> None:
    for section in SECTIONS:
        for item in section["items"]:
            assert item["role"] in ROLES


def test_every_section_covers_all_8_roles_exactly_once() -> None:
    for section in SECTIONS:
        roles = [item["role"] for item in section["items"]]
        assert sorted(roles) == sorted(ROLES.keys())


def test_item_role_map_has_56_unique_ids() -> None:
    assert len(ITEM_ROLE) == 56
    all_ids = [item["id"] for section in SECTIONS for item in section["items"]]
    assert len(all_ids) == len(set(all_ids)) == 56


def test_item_ids_are_section_prefixed_and_1_indexed() -> None:
    for section in SECTIONS:
        expected_ids = [f"{section['section']}{i}" for i in range(1, 9)]
        assert [item["id"] for item in section["items"]] == expected_ids


def test_instruction_text_mentions_10_points_and_7_sections() -> None:
    assert "10 баллов" in INSTRUCTION
    assert "7 разделов" in INSTRUCTION


def test_corrected_roles_from_ф2_1_research_are_applied() -> None:
    """Ф2.1's research doc found 2 mislabeled roles in the ticket's own
    "known" text for sections II/III — this content bank must use the
    corrected roles, not the ticket's original (swapped) labels."""
    by_id = {item["id"]: item for section in SECTIONS for item in section["items"]}

    # Section II item 2 ("великодушен... оригинальные предложения") is
    # coordinator (П), not the ticket's original team_worker (К); item 6
    # ("поддаюсь настроению группы") is team_worker (К), not the ticket's
    # original coordinator (П).
    assert by_id["II2"]["role"] == "coordinator"
    assert by_id["II6"]["role"] == "team_worker"

    # Section III item 2 ("осмотрительность... предотвращает ошибки") is
    # finisher (Д), not the ticket's original evaluator (О) — which caused
    # the "2/7 for О" anomaly the ticket itself flagged as suspicious; item
    # 7 stays evaluator (О), unduplicated.
    assert by_id["III2"]["role"] == "finisher"
    assert by_id["III7"]["role"] == "evaluator"
