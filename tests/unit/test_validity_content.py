"""scripts/lie_scale_bank.py + scripts/infrequency_bank.py — content-bank
invariants for the protocol-validity module (PRO-296). Pure content, no DB.

These guard the shape the PRO-297 seed and PRO-299 scoring rely on:
stable codes, a well-formed key, no order collision with the other question
banks, and traps that don't overlap the MC-SDS items.
"""
import re

from scripts.bigfive_question_bank import QUESTIONS as BIGFIVE
from scripts.infrequency_bank import ITEMS as INFREQ
from scripts.lie_scale_bank import ITEMS as MC_SDS
from scripts.mi_question_bank import QUESTIONS as MI
from scripts.riasec_question_bank import QUESTIONS as RIASEC

_WORD = re.compile(r"[а-яё]+", re.IGNORECASE)


def _content_words(text: str) -> set[str]:
    stop = {
        "я", "и", "в", "во", "не", "на", "что", "как", "когда", "бы", "был",
        "было", "были", "случай", "случаи", "иногда", "всегда", "никогда",
        "у", "меня", "мне", "свои", "своих", "к", "кому", "кто", "он", "они",
        "это", "с", "за", "по", "то", "чтобы", "же", "ни", "раз", "жизни",
    }
    return {w.lower() for w in _WORD.findall(text) if w.lower() not in stop and len(w) > 3}


# --- MC-SDS bank --------------------------------------------------------

def test_mc_sds_has_twenty_items_with_stable_codes() -> None:
    assert len(MC_SDS) == 20
    assert [i["key"] for i in MC_SDS] == [f"mc_sds_{n:02d}" for n in range(1, 21)]


def test_mc_sds_key_is_well_formed() -> None:
    assert all(i["keyed"] in ("agree", "disagree") for i in MC_SDS)
    # commonly-reprinted Khanin key: 11 direct / 9 reverse
    assert sum(i["keyed"] == "agree" for i in MC_SDS) == 11
    assert sum(i["keyed"] == "disagree" for i in MC_SDS) == 9


def test_mc_sds_texts_present_and_unique() -> None:
    texts = [i["text"].strip() for i in MC_SDS]
    assert all(texts)
    assert len(set(texts)) == 20


def test_mc_sds_uses_canonical_wording_not_the_corrupted_web_copies() -> None:
    # PRO-294 confirmed the printed reference (Marischuk 1984). These four items
    # are where the widespread HR web copies silently diverge — guard against
    # someone "restoring" them. See psych-block-spec.md §A2 (canonical wordings).
    by_key = {i["key"]: i["text"] for i in MC_SDS}
    assert "библиотек" in by_key["mc_sds_01"] and "документ" not in by_key["mc_sds_01"]
    assert "в столовой" in by_key["mc_sds_04"] and "ресторан" not in by_key["mc_sds_04"]
    assert "антипати" in by_key["mc_sds_05"] and "симпати" not in by_key["mc_sds_05"]
    assert "что-то делать" in by_key["mc_sds_06"]
    assert "с собой взять" in by_key["mc_sds_16"]
    assert "с вопросами" in by_key["mc_sds_18"] and "просьб" not in by_key["mc_sds_18"]
    assert "с улыбкой" in by_key["mc_sds_20"] and "умысл" not in by_key["mc_sds_20"]


def test_mc_sds_rows_are_validity_middle_ru() -> None:
    for i in MC_SDS:
        assert i["instrument"] == "validity"
        assert i["validity_role"] == "sd_key"
        assert i["age_tier"] == "middle"  # middle + senior, never junior
        assert i["locale"] == "ru"


# --- infrequency bank -------------------------------------------------

def test_infrequency_has_three_to_five_traps_with_stable_codes() -> None:
    assert 3 <= len(INFREQ) <= 5
    assert [i["key"] for i in INFREQ] == [f"infreq_{n:02d}" for n in range(1, len(INFREQ) + 1)]


def test_infrequency_expected_answers_cover_both_directions() -> None:
    assert all(i["expected_answer"] in ("agree", "disagree") for i in INFREQ)
    # both directions present => straight-lining either way fails a trap
    assert {i["expected_answer"] for i in INFREQ} == {"agree", "disagree"}


def test_infrequency_rows_are_validity_middle_ru() -> None:
    for i in INFREQ:
        assert i["instrument"] == "validity"
        assert i["validity_role"] == "infrequency"
        assert i["age_tier"] == "middle"
        assert i["locale"] == "ru"


def test_traps_do_not_paraphrase_mc_sds_items() -> None:
    # cheap semantic-overlap guard: no trap shares 2+ content words with any
    # MC-SDS item (psych-block-spec.md §A7).
    sd_word_sets = [_content_words(i["text"]) for i in MC_SDS]
    for trap in INFREQ:
        tw = _content_words(trap["text"])
        for sw in sd_word_sets:
            assert len(tw & sw) < 2, f"trap {trap['key']!r} overlaps an MC-SDS item: {tw & sw}"


# --- ordering vs the other banks ------------------------------------

def test_validity_order_numbers_continue_without_collision() -> None:
    others = {q["order"] for q in (*RIASEC, *BIGFIVE, *MI)}
    validity = [i["order"] for i in (*MC_SDS, *INFREQ)]
    assert len(set(validity)) == len(validity)
    assert others.isdisjoint(validity)
    # contiguous block right after RIASEC + Big Five + MI
    base = len(RIASEC) + len(BIGFIVE) + len(MI)
    assert validity == list(range(base + 1, base + 1 + len(validity)))
