"""PRO-307: движок метрик МЦВ. Примеры §5.8 (Аружан) и §6.6 воспроизводятся
точь-в-точь; СО и D всегда чётные."""
import random

import pytest

from app.services.psychoemotional import engine

# §5.8 — Аружан
_ARUZHAN_L1 = [4, 3, 2, 1, 5, 6, 0, 7]
_ARUZHAN_L2 = [3, 4, 2, 0, 1, 5, 6, 7]

# аутогенная норма как список 2
_NORM = [3, 4, 2, 5, 1, 6, 0, 7]


def test_aruzhan_example_matches_the_5_8_table() -> None:
    m = engine.compute(_ARUZHAN_L1, _ARUZHAN_L2)

    # пары §5.8: +(красный3, жёлтый4) ×(зелёный2, серый0) =(синий1, фиол.5) −(коричн.6, чёрн.7)
    assert m.pairs["plus"] == [3, 4]
    assert m.pairs["cross"] == [2, 0]
    assert m.pairs["equal"] == [1, 5]
    assert m.pairs["minus"] == [6, 7]
    assert m.pairs["root_conflict"] == [3, 7]

    assert m.anxiety["score"] == 0
    assert m.compensation["score"] == 0
    assert m.so == 6
    assert m.so_level == "norm"
    assert m.vk == 1.5
    assert m.vk_level == "balance"
    assert m.d_value == 8
    assert m.split["split_count"] == 2
    assert m.split["instability"] is False


def test_contrast_profile_from_5_8() -> None:
    # список 2 = [0,7,6,3,5,1,2,4] → тревога 6, компенсация 6, СО высокий
    m = engine.compute(_NORM, [0, 7, 6, 3, 5, 1, 2, 4])
    assert m.anxiety["score"] == 6
    assert m.compensation["score"] == 6
    assert m.so == 30
    assert m.so_level == "high"


def test_so_of_the_norm_is_zero() -> None:
    assert engine.compute(_NORM, _NORM).so == 0


def test_so_of_1234560_is_12() -> None:
    # §6.6 worked example
    assert engine.compute(_NORM, [1, 2, 3, 4, 5, 6, 7, 0]).so == 12


def test_vk_6_7_worked_example() -> None:
    # §6.7: [3,4,2,5,1,6,0,7] → (18-1-2)/(18-5-3) = 15/10 = 1.5
    assert engine.vegetative_coefficient([3, 4, 2, 5, 1, 6, 0, 7]) == 1.5


def test_vk_bounds() -> None:
    # красный/жёлтый на 7,8 · синий/зелёный на 1,2 → (18-15)/(18-3) = 3/15 = 0.2
    assert engine.vegetative_coefficient([1, 2, 5, 6, 0, 7, 3, 4]) == 0.2
    # обратное → 15/3 = 5.0
    assert engine.vegetative_coefficient([3, 4, 5, 6, 0, 7, 1, 2]) == 5.0


@pytest.mark.parametrize("seed", range(40))
def test_so_and_d_are_always_even(seed: int) -> None:
    rng = random.Random(seed)
    l1 = rng.sample(range(8), 8)
    l2 = rng.sample(range(8), 8)
    m = engine.compute(l1, l2)
    assert m.so % 2 == 0
    assert m.d_value % 2 == 0
    assert 0 <= m.so <= 32
    assert 0 <= m.d_value <= 32
    assert 0.2 <= m.vk <= 5.0
    assert 0 <= m.anxiety["score"] <= 12
    assert 0 <= m.compensation["score"] <= 9


def test_d_flags() -> None:
    same = engine.compute(_NORM, list(_NORM))
    assert same.d_value == 0 and same.d_memory is True

    m = engine.compute([0, 1, 2, 3, 4, 5, 6, 7], [7, 6, 5, 4, 3, 2, 1, 0])
    assert m.d_value >= 20 and m.d_situationally_unstable is True


def test_split_pairs_instability_flag() -> None:
    # список 1 пары рядом, в списке 2 все разнесены
    m = engine.compute([0, 1, 2, 3, 4, 5, 6, 7], [0, 4, 1, 5, 2, 6, 3, 7])
    assert m.split["split_count"] >= 3
    assert m.split["instability"] is True


def test_purple_forward_note_no_score() -> None:
    m = engine.compute(_NORM, [5, 1, 2, 3, 4, 6, 0, 7])  # фиолетовый на позиции 1
    assert m.compensation["purple_forward"] is True
    assert m.compensation["breakdown"].get(5) is None  # 5 не в подсчёте
    assert 5 not in engine.EXTRA_COLOR_IDS


def test_structural_performance_direction() -> None:
    # Р = поз(зел)+поз(кр)+поз(жёлт); меньше сумма → выше работоспособность
    good = engine.compute(_NORM, [3, 4, 2, 1, 5, 6, 0, 7])  # кр/жёлт/зел впереди
    poor = engine.compute(_NORM, [1, 5, 6, 0, 7, 3, 4, 2])  # кр/жёлт/зел в конце
    assert good.structural["performance"] < poor.structural["performance"]
    assert 6 <= good.structural["performance"] <= 21


def test_tech_invalid_raises() -> None:
    with pytest.raises(engine.PsychoEmotionalTechInvalid):
        engine.compute([0, 0, 1, 2, 3, 4, 5, 6], _NORM)
    with pytest.raises(engine.PsychoEmotionalTechInvalid):
        engine.compute(_NORM, [1, 2, 3])
