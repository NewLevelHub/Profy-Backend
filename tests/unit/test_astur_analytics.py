"""PRO-427 §16 — per-item analytics never surface one-off free-text answers."""
from types import SimpleNamespace

from app.services.astur.analytics import _content_item_stats, age_band
from tests.astur_fixtures import v1_bank

BANK = v1_bank()
GENERALIZATION = BANK.subtest("generalization")


def _run(text: str | None, *, skipped: bool = False):
    entry = {"status": "skipped", "value": None} if skipped else {"status": "answered", "value": text}
    return SimpleNamespace(
        locale="ru",
        answers={"generalization": {"1": entry}},
        result_snapshot={"item_scores": {"generalization-01": 0}},
    )


def test_unrecognized_answers_need_three_occurrences_and_are_masked() -> None:
    runs = [_run("растут в лесу")] * 3 + [_run("мой номер 87011234567")] + [_run(None, skipped=True)]
    first = _content_item_stats(GENERALIZATION, runs)[0]
    assert first["unrecognized_answers"] == [{"text": "растут в лесу", "locale": "ru", "count": 3}]
    assert (first["answered"], first["skipped"], first["unanswered"]) == (4, 1, 0)

    runs = [_run("звоните 87011234567")] * 3
    [shown] = _content_item_stats(GENERALIZATION, runs)[0]["unrecognized_answers"]
    assert "87011234567" not in shown["text"]


def test_age_bands() -> None:
    assert [age_band(a) for a in (None, 13, 14, 15, 16, 17, 18)] == [
        "unknown", "under_14", "14_15", "14_15", "16_17", "16_17", "18_plus",
    ]
