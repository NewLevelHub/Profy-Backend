"""PRO-305 / PRO-306: МЦВ stimulus constants — HEX byte-matches the
methodology note (тестЛюшера.md §4), autogenic norm + position map are the
fixed §B5.5 values."""
from app.services.psychoemotional import constants as c


def test_hex_matches_methodology_note_byte_for_byte() -> None:
    # тестЛюшера.md §4 / psych-block-spec.md §B3
    assert {cid: col["hex"] for cid, col in c.COLORS.items()} == {
        1: "#004983",
        2: "#1D9772",
        3: "#F12F23",
        4: "#F2DD00",
        5: "#D42481",
        6: "#C55223",
        7: "#231F20",
        0: "#98938D",
    }


def test_black_is_not_pure_black() -> None:
    # §B3: «почти чёрный с тёплым подтоном (не #000000)»
    assert c.COLORS[7]["hex"] != "#000000"


def test_colour_id_sets() -> None:
    assert c.COLOR_IDS == frozenset(range(8))
    assert c.BASIC_COLOR_IDS == (1, 2, 3, 4)
    assert c.EXTRA_COLOR_IDS == (0, 6, 7)
    assert c.BORDER_COLOR_ID == 5  # фиолетовый — вне подсчёта компенсации
    assert c.CHOICE_COUNT == 8


def test_autogenic_norm_and_positions() -> None:
    assert c.AUTOGENIC_NORM == (3, 4, 2, 5, 1, 6, 0, 7)
    assert c.AUTOGENIC_NORM_POSITION == {3: 1, 4: 2, 2: 3, 5: 4, 1: 5, 6: 6, 0: 7, 7: 8}
    # norm is a permutation of all 8 colour ids
    assert set(c.AUTOGENIC_NORM) == c.COLOR_IDS
    assert len(c.AUTOGENIC_NORM) == c.CHOICE_COUNT


def test_so_of_the_norm_itself_is_zero() -> None:
    """СО = Σ|позиция в списке2 − позиция в норме|; список2 == норма → 0."""
    list2 = list(c.AUTOGENIC_NORM)
    so = sum(
        abs((list2.index(cid) + 1) - c.AUTOGENIC_NORM_POSITION[cid])
        for cid in c.COLOR_IDS
    )
    assert so == 0
