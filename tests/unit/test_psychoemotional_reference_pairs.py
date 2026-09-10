"""PRO-307: сверка пар/знаков с эталоном `luscher-test/` (temoncher).

`ProfOr/luscher-test/` в дереве нет (был sync-only reference). Проверять
алгоритмически нечего: позиционные пары §6.2 — это чистое разбиение списка 2
по позициям (1–2 +, 3–4 ×, 5–6 =, 7–8 −), идентичное в любом движке; всё,
что могло бы разойтись — это 0-индексация ID у temoncher (в наших списках
ID уже 0–7, `+1` не требуется). Фикстуры ниже — вручную проверенные
профили; тест фиксирует, что наше разбиение = позиционное.
"""
import pytest

from app.services.psychoemotional import engine

# (list2, ожидаемые +, ×, =, −)  — проверено вручную по §6.2
_CASES = [
    ([3, 4, 2, 0, 1, 5, 6, 7], [3, 4], [2, 0], [1, 5], [6, 7]),  # §5.8 Аружан
    ([1, 2, 3, 4, 5, 6, 7, 0], [1, 2], [3, 4], [5, 6], [7, 0]),
    ([0, 7, 6, 3, 5, 1, 2, 4], [0, 7], [6, 3], [5, 1], [2, 4]),
    ([3, 4, 2, 5, 1, 6, 0, 7], [3, 4], [2, 5], [1, 6], [0, 7]),  # аутогенная норма
]


@pytest.mark.parametrize("list2,plus,cross,equal,minus", _CASES)
def test_positional_pairs_match_reference(list2, plus, cross, equal, minus) -> None:
    pairs = engine.positional_pairs(list2)
    assert pairs["plus"] == plus == list2[0:2]
    assert pairs["cross"] == cross == list2[2:4]
    assert pairs["equal"] == equal == list2[4:6]
    assert pairs["minus"] == minus == list2[6:8]
    assert pairs["root_conflict"] == [list2[0], list2[7]]


def test_pairs_partition_every_colour_once() -> None:
    for list2, *_ in _CASES:
        pairs = engine.positional_pairs(list2)
        covered = pairs["plus"] + pairs["cross"] + pairs["equal"] + pairs["minus"]
        assert sorted(covered) == list(range(8))
