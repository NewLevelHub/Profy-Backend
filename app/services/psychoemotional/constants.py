"""МЦВ Собчик — фиксированные константы стимульного материала и нормы.

Источник: `psych-block-spec.md §B2/§B3/§B5.5`, `тестЛюшера.md §4`. HEX-цвета —
приёмочный критерий PRO-306, побайтово из методзаписки; не менять без сверки.
`ID цвета (0–7) ≠ позиция выбора (ранг 1–8)`.
"""

# ID → имя · HEX (sRGB) · категория (basic 1–4, extra 0/6/7, border 5).
COLORS: dict[int, dict[str, str]] = {
    1: {"name": "синий", "hex": "#004983", "category": "basic"},
    2: {"name": "зелёный", "hex": "#1D9772", "category": "basic"},
    3: {"name": "красный", "hex": "#F12F23", "category": "basic"},
    4: {"name": "жёлтый", "hex": "#F2DD00", "category": "basic"},
    5: {"name": "фиолетовый", "hex": "#D42481", "category": "border"},
    6: {"name": "коричневый", "hex": "#C55223", "category": "extra"},
    7: {"name": "чёрный", "hex": "#231F20", "category": "extra"},
    0: {"name": "серый", "hex": "#98938D", "category": "extra"},
}

COLOR_IDS: frozenset[int] = frozenset(COLORS)  # {0,1,2,3,4,5,6,7}
BASIC_COLOR_IDS: tuple[int, ...] = (1, 2, 3, 4)  # индекс тревоги (§B5.3)
EXTRA_COLOR_IDS: tuple[int, ...] = (0, 6, 7)  # индекс компенсации (§B5.4); 5 — пограничный, вне подсчёта
BORDER_COLOR_ID: int = 5  # фиолетовый — отдельная пометка «выдвинут вперёд», без баллов

CHOICE_COUNT: int = 8  # ровно 8 плашек в каждом круге

# Аутогенная норма (эталон нервно-психического благополучия): цвета по
# позициям 1–8 (§B5.5).
AUTOGENIC_NORM: tuple[int, ...] = (3, 4, 2, 5, 1, 6, 0, 7)
# color_id → его ранг (позиция 1–8) в норме — используется в формуле СО.
AUTOGENIC_NORM_POSITION: dict[int, int] = {
    color_id: rank for rank, color_id in enumerate(AUTOGENIC_NORM, start=1)
}  # {3: 1, 4: 2, 2: 3, 5: 4, 1: 5, 6: 6, 0: 7, 7: 8}

# --- self-checks (приёмочные критерии PRO-305/PRO-306) --------------------
_SPEC_HEX: dict[int, str] = {
    1: "#004983", 2: "#1D9772", 3: "#F12F23", 4: "#F2DD00",
    5: "#D42481", 6: "#C55223", 7: "#231F20", 0: "#98938D",
}
assert {cid: c["hex"] for cid, c in COLORS.items()} == _SPEC_HEX, (
    "HEX drift vs тестЛюшера.md §4 — приёмочный критерий PRO-306"
)
assert AUTOGENIC_NORM_POSITION == {3: 1, 4: 2, 2: 3, 5: 4, 1: 5, 6: 6, 0: 7, 7: 8}
assert COLOR_IDS == frozenset(range(8))
assert len(AUTOGENIC_NORM) == CHOICE_COUNT and set(AUTOGENIC_NORM) == COLOR_IDS
