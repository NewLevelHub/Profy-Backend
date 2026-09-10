"""Сборка текстовых подсказок специалисту из статического каталога
(`app/data/psychoemotional_hints.json`, PRO-304). Никакой генерации ИИ:
вход — паттерн из метрик по списку 2, выход — упорядоченный список ключей +
готовый текст.

Приоритет (§8):
  1  связка −X/+Y · тревога · компенсация · нестабильность;
  2  функциональные пары (+/×/=/−);
  3  одиночные цвета — в v1 не пишем.
При выраженной тревоге подсказки уровня 2 про «расслабление / спокойствие»
подавляются.
"""
import json
from pathlib import Path

from app.services.psychoemotional.constants import BASIC_COLOR_IDS, EXTRA_COLOR_IDS
from app.services.psychoemotional.engine import PsychoEmotionalMetrics

_HINTS_PATH = Path(__file__).parent.parent.parent / "data" / "psychoemotional_hints.json"
_RAW = json.loads(_HINTS_PATH.read_text(encoding="utf-8"))

TEMPLATES: dict[str, str] = _RAW["templates"]
_PRIORITY_BY_PREFIX: dict[str, int] = _RAW["priority"]
HINTS_VERSION: int = _RAW["version"]

# §8: при выраженной тревоге тексты уровня 2 «про спокойствие / релаксацию» уходят.
_SUPPRESS_ON_HIGH_ANXIETY = ("расслаб", "релакс", "спокойн")
_HIGH_ANXIETY_LEVELS = ("high", "very_high")

_SIGN_POSITIONS = {
    "plus": (0, 1),
    "cross": (2, 3),
    "equal": (4, 5),
    "minus": (6, 7),
}


def priority_of(key: str) -> int:
    return _PRIORITY_BY_PREFIX.get(key.split(".", 1)[0], 3)


def _rank_map(order: list[int]) -> dict[int, int]:
    return {color_id: rank for rank, color_id in enumerate(order, start=1)}


def assemble(metrics: PsychoEmotionalMetrics) -> dict:
    """→ {"hint_keys": [...], "text": "..."}. Ключи уникальны, отсортированы
    по приоритету (стабильно — порядок внутри уровня сохранён)."""
    pos = _rank_map(metrics.list2)
    keys: list[str] = []

    # --- уровень 1 -----------------------------------------------------------
    if metrics.split["instability"]:
        keys.append("instability.split")
    if metrics.d_situationally_unstable:
        keys.append("instability.d_high")

    # связка −X/+Y: сильнейший фрустрированный основной (поз. 8 → 7) +
    # сильнейший компенсирующий (поз. 1 → 2), фиолетовый тоже считается (§6.5).
    frustrated = next(
        (cid for cid in BASIC_COLOR_IDS if pos[cid] == 8),
        next((cid for cid in BASIC_COLOR_IDS if pos[cid] == 7), None),
    )
    compensating = next(
        (cid for cid in (*EXTRA_COLOR_IDS, 5) if pos[cid] == 1),
        next((cid for cid in (*EXTRA_COLOR_IDS, 5) if pos[cid] == 2), None),
    )
    if frustrated is not None and compensating is not None:
        keys.append(f"link.{frustrated}.{compensating}")

    for cid in BASIC_COLOR_IDS:
        if pos[cid] in (6, 7, 8):
            keys.append(f"anxiety.{cid}.{pos[cid]}")

    for cid in EXTRA_COLOR_IDS:
        if pos[cid] in (1, 2, 3):
            keys.append(f"comp.{cid}.{pos[cid]}")
    if metrics.compensation["purple_forward"]:
        keys.append("comp.5.forward")

    # --- уровень 2: функциональные пары -----------------------------------
    for sign, (i, j) in _SIGN_POSITIONS.items():
        keys.append(f"fn.{sign}.{metrics.list2[i]}")
        keys.append(f"fn.{sign}.{metrics.list2[j]}")

    # dedupe (сохраняя порядок), только известные ключи
    seen: set[str] = set()
    ordered = [
        k for k in keys if k in TEMPLATES and not (k in seen or seen.add(k))
    ]

    # подавление при выраженной тревоге — только уровень 2+
    if metrics.anxiety_level in _HIGH_ANXIETY_LEVELS:
        ordered = [
            k
            for k in ordered
            if priority_of(k) == 1
            or not any(w in TEMPLATES[k].lower() for w in _SUPPRESS_ON_HIGH_ANXIETY)
        ]

    ordered.sort(key=priority_of)  # stable — приоритет вперёд, порядок внутри цел
    return {
        "hint_keys": ordered,
        "text": "\n\n".join(TEMPLATES[k] for k in ordered),
    }
