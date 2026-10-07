"""PRO-338 Ф0.6 — generic ipsative point-allocation engine. Pure-function
validation/aggregation, no DB/Redis involved (mirrors the Belbin shape:
7 blocks x 8 items, 10 points per block — used here as a representative
single block, not the full battery)."""
import pytest
from fastapi import HTTPException

from app.services import ipsative_battery

_BELBIN_BLOCK_ITEMS = [f"i{n}" for n in range(1, 9)]  # 8 items, like one Belbin block


def _even_split(total: int, items: list[str]) -> dict[str, int]:
    """Not a realistic ipsative answer (real ones concentrate points on a
    few items), just the simplest input whose sum is exactly `total`."""
    base, remainder = divmod(total, len(items))
    return {item: base + (1 if i < remainder else 0) for i, item in enumerate(items)}


def test_valid_allocation_passes_silently() -> None:
    allocation = _even_split(10, _BELBIN_BLOCK_ITEMS)
    # No exception, no return value to check — the contract is "didn't raise".
    ipsative_battery.validate_allocation(allocation, expected_items=_BELBIN_BLOCK_ITEMS, total=10)


def test_wrong_total_is_422() -> None:
    allocation = _even_split(9, _BELBIN_BLOCK_ITEMS)  # one short of 10
    with pytest.raises(HTTPException) as exc_info:
        ipsative_battery.validate_allocation(allocation, expected_items=_BELBIN_BLOCK_ITEMS, total=10)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["actual_total"] == 9
    assert exc_info.value.detail["expected_total"] == 10


@pytest.mark.parametrize("total", [0, 6, 10])
def test_draft_allows_unspent_points(total: int) -> None:
    ipsative_battery.validate_allocation(
        _even_split(total, _BELBIN_BLOCK_ITEMS),
        expected_items=_BELBIN_BLOCK_ITEMS, total=10, allow_partial=True,
    )


@pytest.mark.parametrize("locale", ["ru", "kk"])
def test_draft_over_budget_is_rejected_in_request_locale(locale: str) -> None:
    from app.i18n import use_locale
    from app.i18n.catalog import api_errors

    with use_locale(locale), pytest.raises(HTTPException) as exc_info:
        ipsative_battery.validate_allocation(
            _even_split(11, _BELBIN_BLOCK_ITEMS),
            expected_items=_BELBIN_BLOCK_ITEMS, total=10, allow_partial=True,
        )
    catalog = api_errors.RU if locale == "ru" else api_errors.KK
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["detail"] == catalog["allocation_total_exceeded"].format(
        total=10, actual_total=11,
    )


@pytest.mark.parametrize("allocation", [{"i1": 6}, {"i1": -1, **{f"i{n}": 0 for n in range(2, 9)}}])
def test_partial_draft_still_validates_items_and_nonnegative_values(allocation) -> None:
    with pytest.raises(HTTPException):
        ipsative_battery.validate_allocation(
            allocation, expected_items=_BELBIN_BLOCK_ITEMS, total=10, allow_partial=True,
        )


def test_negative_value_is_422_even_if_total_is_correct() -> None:
    """A client could zero out points elsewhere to compensate for one
    negative value and still hit the right sum — the negative-value check
    must be independent of the sum check, not skipped once the sum passes."""
    allocation = {"i1": -2, "i2": 12, **{i: 0 for i in _BELBIN_BLOCK_ITEMS[2:]}}
    with pytest.raises(HTTPException) as exc_info:
        ipsative_battery.validate_allocation(allocation, expected_items=_BELBIN_BLOCK_ITEMS, total=10)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["negative_items"] == {"i1": -2}


def test_missing_item_is_422() -> None:
    allocation = _even_split(10, _BELBIN_BLOCK_ITEMS[:-1])  # only 7 of 8 items
    with pytest.raises(HTTPException) as exc_info:
        ipsative_battery.validate_allocation(allocation, expected_items=_BELBIN_BLOCK_ITEMS, total=10)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["missing_items"] == [_BELBIN_BLOCK_ITEMS[-1]]
    assert exc_info.value.detail["unexpected_items"] == []


def test_unknown_item_is_422() -> None:
    allocation = _even_split(10, _BELBIN_BLOCK_ITEMS)
    allocation["not_a_real_item"] = allocation.pop("i1")
    with pytest.raises(HTTPException) as exc_info:
        ipsative_battery.validate_allocation(allocation, expected_items=_BELBIN_BLOCK_ITEMS, total=10)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["missing_items"] == ["i1"]
    assert exc_info.value.detail["unexpected_items"] == ["not_a_real_item"]


def test_client_side_validation_is_never_trusted() -> None:
    """A payload that would look "fine" to a naive frontend sum check (right
    total) but sneaks in a wrong item set must still be rejected — the
    frontend's own remaining-points UI is a UX hint, never the source of
    truth (Ф0.6's whole premise)."""
    allocation = {"i1": 5, "i2": 5, "bogus": 0}  # sums to 10, but wrong items
    with pytest.raises(HTTPException):
        ipsative_battery.validate_allocation(allocation, expected_items=_BELBIN_BLOCK_ITEMS, total=10)


def test_aggregate_by_key_sums_across_multiple_blocks() -> None:
    # Two blocks; items "a"/"c" map to role X, "b"/"d" map to role Y.
    block_1 = {"a": 6, "b": 4}
    block_2 = {"c": 3, "d": 7}
    item_to_key_map = {"a": "X", "b": "Y", "c": "X", "d": "Y"}

    totals = ipsative_battery.aggregate_by_key([block_1, block_2], item_to_key_map)

    assert totals == {"X": 9, "Y": 11}


def test_aggregate_by_key_raises_on_unmapped_item() -> None:
    """An item_id with no entry in item_to_key_map is a content-authoring
    bug — must fail loudly (KeyError), not silently drop those points."""
    with pytest.raises(KeyError):
        ipsative_battery.aggregate_by_key([{"a": 10}], item_to_key_map={})
