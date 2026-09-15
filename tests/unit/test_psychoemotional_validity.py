"""PRO-308: флаг достоверности прохождения психоэмоционального теста (§B7).

Пять признаков считаются независимо; сводный флаг по правилу 0 / 1 / 2+.
Δt-признаки берут готовые массивы, D / split-пары приходят уже посчитанными.
"""
import pytest

from app.config import psychoemotional_thresholds
from app.models.psychoemotional_run import PsychoEmotionalValidityFlag
from app.services.psychoemotional import validity

_T = psychoemotional_thresholds.validity

# 16 «нормальных» кликов: медиана заметно выше 500 мс, сумма заметно выше 20 с.
_OK_DELTAS_8 = [2000, 2200, 1800, 2500, 2100, 1900, 2300, 2000]


def _evaluate(**overrides) -> validity.RunValidity:
    base = dict(
        list1_dt_ms=list(_OK_DELTAS_8),
        list2_dt_ms=list(_OK_DELTAS_8),
        pause_actual_sec=130,
        d_value=8,
        split_count=1,
    )
    base.update(overrides)
    return validity.evaluate(**base)


def test_clean_run_has_no_reasons_and_flag_ok() -> None:
    res = _evaluate()
    assert res.reasons == []
    assert res.flag is PsychoEmotionalValidityFlag.ok
    assert res.flag_value == "ok"
    assert all(v is False for v in res.details["signs"].values())


def test_mechanical_pick_isolated_is_a_single_caution() -> None:
    # 9 быстрых + 7 очень медленных: медиана < 500, но сумма >> 20 с →
    # срабатывает только «механический выбор».
    fast_then_slow = [100] * 9 + [6000] * 7
    res = _evaluate(
        list1_dt_ms=fast_then_slow[:8],
        list2_dt_ms=fast_then_slow[8:],
        d_value=6,
        split_count=1,
    )
    assert res.details["signs"][validity.REASON_MECHANICAL_PICK] is True
    assert res.details["signs"][validity.REASON_TOO_FAST_OVERALL] is False
    assert res.reasons == [validity.REASON_MECHANICAL_PICK]
    assert res.flag is PsychoEmotionalValidityFlag.caution


def test_too_fast_overall_isolated_is_a_single_caution() -> None:
    # ровные 1000 мс: медиана не < 500, но сумма 16 000 мс < 20 с.
    res = _evaluate(list1_dt_ms=[1000] * 8, list2_dt_ms=[1000] * 8, d_value=6)
    assert res.details["signs"][validity.REASON_MECHANICAL_PICK] is False
    assert res.details["signs"][validity.REASON_TOO_FAST_OVERALL] is True
    assert res.reasons == [validity.REASON_TOO_FAST_OVERALL]
    assert res.flag is PsychoEmotionalValidityFlag.caution


def test_missing_timing_never_flags_speed() -> None:
    # пустые массивы Δt: sum([]) == 0, но «слишком быстро» не должно срабатывать.
    res = _evaluate(list1_dt_ms=[], list2_dt_ms=[])
    assert res.details["signs"][validity.REASON_MECHANICAL_PICK] is False
    assert res.details["signs"][validity.REASON_TOO_FAST_OVERALL] is False
    assert res.details["timing_sample"] == 0
    assert res.flag is PsychoEmotionalValidityFlag.ok


def test_partial_timing_below_majority_is_not_assessed() -> None:
    # 8 из 16 кликов с таймингом — меньше большинства, скорость не оценивается.
    res = _evaluate(list1_dt_ms=[50] * 8, list2_dt_ms=[])
    assert res.details["signs"][validity.REASON_MECHANICAL_PICK] is False
    assert res.details["signs"][validity.REASON_TOO_FAST_OVERALL] is False


def test_identical_lists_flag() -> None:
    res = _evaluate(d_value=0, split_count=0)
    assert res.details["signs"][validity.REASON_IDENTICAL_LISTS] is True
    assert res.reasons == [validity.REASON_IDENTICAL_LISTS]
    assert res.flag is PsychoEmotionalValidityFlag.caution


def test_unstable_by_split_pairs() -> None:
    res = _evaluate(d_value=8, split_count=3)
    assert res.reasons == [validity.REASON_UNSTABLE_CHOICES]
    assert res.flag is PsychoEmotionalValidityFlag.caution


def test_unstable_by_high_divergence() -> None:
    res = _evaluate(d_value=24, split_count=0)
    assert res.details["signs"][validity.REASON_UNSTABLE_CHOICES] is True
    assert res.details["signs"][validity.REASON_IDENTICAL_LISTS] is False
    assert res.reasons == [validity.REASON_UNSTABLE_CHOICES]
    assert res.flag is PsychoEmotionalValidityFlag.caution


def test_pause_not_held_flag() -> None:
    res = _evaluate(pause_actual_sec=90)
    assert res.reasons == [validity.REASON_PAUSE_NOT_HELD]
    assert res.flag is PsychoEmotionalValidityFlag.caution


def test_pause_exactly_at_the_minimum_is_held() -> None:
    res = _evaluate(pause_actual_sec=int(_T["pause_min_sec"]))
    assert res.details["signs"][validity.REASON_PAUSE_NOT_HELD] is False


def test_two_signs_make_low() -> None:
    # пауза не выдержана + одинаковые списки.
    res = _evaluate(pause_actual_sec=10, d_value=0, split_count=0)
    assert set(res.reasons) == {
        validity.REASON_IDENTICAL_LISTS,
        validity.REASON_PAUSE_NOT_HELD,
    }
    assert res.flag is PsychoEmotionalValidityFlag.low


def test_all_five_signs_low_and_reasons_in_fixed_order() -> None:
    res = validity.evaluate(
        list1_dt_ms=[100] * 8,
        list2_dt_ms=[100] * 8,
        pause_actual_sec=5,
        d_value=0,
        split_count=4,
    )
    assert res.reasons == [
        validity.REASON_MECHANICAL_PICK,
        validity.REASON_TOO_FAST_OVERALL,
        validity.REASON_IDENTICAL_LISTS,
        validity.REASON_UNSTABLE_CHOICES,
        validity.REASON_PAUSE_NOT_HELD,
    ]
    assert res.flag is PsychoEmotionalValidityFlag.low


def test_reason_order_is_table_order_regardless_of_which_fired() -> None:
    # сработают признаки 5 и 3 — на выходе порядок таблицы §B7, не порядок проверки.
    res = _evaluate(pause_actual_sec=30, d_value=0, split_count=0)
    assert res.reasons == [
        validity.REASON_IDENTICAL_LISTS,
        validity.REASON_PAUSE_NOT_HELD,
    ]


def test_details_carry_measured_values_and_thresholds_version() -> None:
    res = _evaluate(list1_dt_ms=[1000] * 8, list2_dt_ms=[1000] * 8)
    assert res.details["median_dt_ms"] == 1000
    assert res.details["total_active_ms"] == 16000
    assert res.details["timing_sample"] == 16
    assert res.details["thresholds_version"] == psychoemotional_thresholds.version


def test_negative_and_bool_deltas_are_ignored() -> None:
    # мусорные значения не должны влиять на медиану/сумму.
    res = _evaluate(
        list1_dt_ms=[-5, True, False, 1000, 1000, 1000, 1000, 1000],
        list2_dt_ms=[1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000],
    )
    assert res.details["timing_sample"] == 13  # 5 из первого массива + 8 из второго
    assert res.details["median_dt_ms"] == 1000


@pytest.mark.parametrize(
    "n_reasons,expected",
    [
        (0, PsychoEmotionalValidityFlag.ok),
        (1, PsychoEmotionalValidityFlag.caution),
        (2, PsychoEmotionalValidityFlag.low),
        (5, PsychoEmotionalValidityFlag.low),
    ],
)
def test_summary_flag_rule_0_1_2plus(n_reasons: int, expected) -> None:
    knobs: dict = {}
    if n_reasons >= 1:
        knobs["pause_actual_sec"] = 10
    if n_reasons >= 2:
        knobs["d_value"] = 0
        knobs["split_count"] = 0
    if n_reasons >= 5:
        knobs["list1_dt_ms"] = [100] * 8
        knobs["list2_dt_ms"] = [100] * 8
        knobs["split_count"] = 4
    res = _evaluate(**knobs)
    assert res.flag is expected
