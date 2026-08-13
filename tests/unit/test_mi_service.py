"""No DB/Redis involved — pure-function scoring math."""

from app.services import mi_service


def test_strengths_always_reaches_limit_even_when_aversion_disqualifies_most() -> None:
    """Same guarantee as riasec_service.strengths_weaknesses (see its test's
    docstring) — junior's MI instrument must not collapse "Сильные стороны"
    to near-empty/empty just because most categories got disqualified by
    the aversion filter."""
    normalized = {
        "verbal": 60.0, "logical": 55.0, "musical": 50.0, "visual": 45.0,
        "bodily": 70.0, "interpersonal": 40.0, "intrapersonal": 35.0, "naturalistic": 30.0,
    }
    aversion_counts = {
        "verbal": 8, "logical": 8, "musical": 8, "visual": 8,
        "bodily": 1, "interpersonal": 8, "intrapersonal": 8, "naturalistic": 8,
    }
    counts = {k: 20 for k in normalized}  # 8/20 = 40% >= 30% disqualifies everything but bodily (1/20 = 5%)

    strengths, _ = mi_service.strengths_weaknesses(normalized, aversion_counts, counts, limit=3)

    assert len(strengths) == 3
    assert "bodily" in strengths
    assert len(set(strengths)) == 3


def test_strengths_no_padding_needed_when_filter_already_yields_enough() -> None:
    normalized = {
        "verbal": 90.0, "logical": 80.0, "musical": 70.0, "visual": 10.0,
        "bodily": 5.0, "interpersonal": 5.0, "intrapersonal": 5.0, "naturalistic": 5.0,
    }
    aversion_counts = {k: 0 for k in normalized}
    counts = {k: 20 for k in normalized}

    strengths, _ = mi_service.strengths_weaknesses(normalized, aversion_counts, counts, limit=3)

    assert strengths == ["verbal", "logical", "musical"]
