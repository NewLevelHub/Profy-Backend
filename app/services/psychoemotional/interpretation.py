"""Текстовое толкование психоэмоционального теста для специалиста (PRO-448).

Никакой генерации ИИ: метрики прохождения (`PsychoEmotionalMetrics.as_dict()`,
по списку 2) → ключи статического каталога
`app/i18n/catalog/psychoemotional_interpretation.py` → текст на языке запроса.

Порядок чтения (`psychoemotional-templates.md §8`):
  reading     — нестабильность прохождения: задаёт рамку доверия к остальному;
  highlights  — связка −X/+Y, тревога по основным цветам, компенсация
                дополнительными; сильные сигналы первыми;
  indices     — абзац к уровню тревоги / СО / ВК;
  positions   — пара цветов каждой функциональной группы (+ × = −) и
                главное противоречие: первый цвет против последнего.
Связка заменяет отдельные тексты про оба своих цвета. Тексты пар написаны в
тоне «старается / возможно», поэтому рядом с высокой тревогой не читаются как
«всё хорошо» и отдельного подавления не требуют.
"""
from app.i18n.catalog import tr
from app.schemas.result_v2 import (
    PsychoEmotionalHighlight,
    PsychoEmotionalIndexNote,
    PsychoEmotionalInterpretation,
    PsychoEmotionalPositionNote,
)
from app.services.psychoemotional.constants import BASIC_COLOR_IDS, BORDER_COLOR_ID, EXTRA_COLOR_IDS
from app.services.psychoemotional.engine import SIGN_CROSS, SIGN_EQUAL, SIGN_MINUS, SIGN_PLUS

_SIGNS = (SIGN_PLUS, SIGN_CROSS, SIGN_EQUAL, SIGN_MINUS)


def _first_at(color_ids: tuple[int, ...], pos: dict[int, int], positions: tuple[int, ...]) -> int | None:
    """Цвет из `color_ids` на первой из `positions`, где он есть (8 раньше 7 и т. п.)."""
    for position in positions:
        for color_id in color_ids:
            if pos[color_id] == position:
                return color_id
    return None


def _highlights(pos: dict[int, int], texts: dict) -> list[PsychoEmotionalHighlight]:
    frustrated = _first_at(BASIC_COLOR_IDS, pos, (8, 7))
    compensating = _first_at((*EXTRA_COLOR_IDS, BORDER_COLOR_ID), pos, (1, 2))
    link_key = f"{frustrated}.{compensating}"
    linked = frustrated is not None and compensating is not None and link_key in texts["link"]

    notes: list[PsychoEmotionalHighlight] = []
    if linked:
        notes.append(
            PsychoEmotionalHighlight(key=f"link.{link_key}", text=texts["link"][link_key], position_depth=3)
        )

    for color_id in BASIC_COLOR_IDS:
        if pos[color_id] < 6 or (linked and color_id == frustrated):
            continue
        key = f"{color_id}.{pos[color_id]}"
        notes.append(
            PsychoEmotionalHighlight(
                key=f"anxiety.{key}", text=texts["anxiety"][key], position_depth=pos[color_id] - 5
            )
        )

    for color_id in EXTRA_COLOR_IDS:
        if pos[color_id] > 3 or (linked and color_id == compensating):
            continue
        key = f"{color_id}.{pos[color_id]}"
        notes.append(
            PsychoEmotionalHighlight(
                key=f"comp.{key}", text=texts["comp"][key], position_depth=4 - pos[color_id]
            )
        )

    violet = pos[BORDER_COLOR_ID]
    if violet <= 3 and not (linked and compensating == BORDER_COLOR_ID):
        notes.append(
            PsychoEmotionalHighlight(
                key="comp.5.forward", text=texts["comp"]["5.forward"], position_depth=4 - violet
            )
        )

    return sorted(notes, key=lambda note: -note.position_depth)  # stable: равные — в порядке блоков


def _positions(pairs: dict, texts: dict) -> list[PsychoEmotionalPositionNote]:
    """Пары ключуются отсортированными ID (группа симметрична), главное
    противоречие — в порядке «первый, последний» (оно направленное)."""
    notes = [
        PsychoEmotionalPositionNote(
            sign=sign, colors=list(pairs[sign]), text=texts["pair"][sign]["".join(map(str, sorted(pairs[sign])))]
        )
        for sign in _SIGNS
    ]
    first, last = pairs["root_conflict"]
    notes.append(PsychoEmotionalPositionNote(sign="plus_minus", colors=[first, last], text=texts["pm"][f"{first}{last}"]))
    return notes


def interpret(metrics: dict, list2: list[int]) -> PsychoEmotionalInterpretation:
    """Метрики прохождения → гипотезы на языке запроса.

    Качество прохождения (флаг достоверности и причины) здесь не озвучивается:
    карточка специалиста уже показывает его бейджем, повтор в толковании —
    лишний текст.
    """
    texts = tr("psychoemotional_interpretation")
    pos = {color_id: rank for rank, color_id in enumerate(list2, start=1)}

    reading = []
    if metrics["split"]["instability"]:
        reading.append(texts["reading"]["split"])
    if metrics["d"]["situationally_unstable"]:
        reading.append(texts["reading"]["d_high"])

    indices = [
        PsychoEmotionalIndexNote(metric=metric, level=level, text=texts["level"][metric][level])
        for metric, level in (
            ("anxiety", metrics["anxiety"]["level"]),
            ("so", metrics["so"]["level"]),
            ("vk", metrics["vk"]["level"]),
        )
    ]

    return PsychoEmotionalInterpretation(
        reading=reading,
        highlights=_highlights(pos, texts),
        indices=indices,
        positions=_positions(metrics["pairs"], texts),
    )
