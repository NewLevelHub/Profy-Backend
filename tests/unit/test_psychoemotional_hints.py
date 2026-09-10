"""PRO-307: сборка подсказок — приоритет §8, подавление «релаксации» при
выраженной тревоге, связка −X/+Y."""
from app.services.psychoemotional import engine
from app.services.psychoemotional.hints import (
    TEMPLATES,
    assemble,
    priority_of,
)

_NORM = [3, 4, 2, 5, 1, 6, 0, 7]


def test_catalog_shape() -> None:
    assert len(TEMPLATES) == 71  # 2 + 15 + 12 + 10 + 32
    assert priority_of("instability.split") == 1
    assert priority_of("link.1.6") == 1
    assert priority_of("anxiety.1.7") == 1
    assert priority_of("comp.6.1") == 1
    assert priority_of("fn.plus.1") == 2
    # никаких медицинских ярлыков
    banned = ("депресс", "невроз", "патолог", "дезадапт", "расстройств")
    for text in TEMPLATES.values():
        assert not any(b in text.lower() for b in banned)


def test_priority_ordering_p1_before_p2() -> None:
    m = engine.compute(_NORM, _NORM)
    out = assemble(m)
    priorities = [priority_of(k) for k in out["hint_keys"]]
    assert priorities == sorted(priorities)
    assert out["text"]  # непустой


def test_high_anxiety_suppresses_relaxation_texts() -> None:
    # синий(1) на позиции 1 → без подавления в выдаче был бы fn.plus.1
    # («…спокойных отношениях»); зелёный/красный/жёлтый в хвосте → тревога 6.
    m = engine.compute(_NORM, [1, 5, 6, 0, 7, 2, 3, 4])
    assert m.anxiety_level in ("high", "very_high")

    out = assemble(m)
    assert "fn.plus.1" not in out["hint_keys"]  # вырезан — «спокойн» + приоритет 2
    for key in out["hint_keys"]:
        if priority_of(key) >= 2:
            text = TEMPLATES[key].lower()
            assert not any(w in text for w in ("расслаб", "релакс", "спокойн"))
    # блок тревоги при этом присутствует (приоритет 1 не подавляется)
    assert any(k.startswith("anxiety.") for k in out["hint_keys"])


def test_low_anxiety_keeps_calm_fn_texts() -> None:
    # синий(1) на позиции 1 → в выдаче fn.plus.1 («…спокойных отношениях»);
    # тревога здесь низкая, подавления быть не должно.
    m = engine.compute(_NORM, [1, 3, 2, 4, 5, 6, 0, 7])
    assert m.anxiety_level == "low"
    out = assemble(m)
    assert "fn.plus.1" in out["hint_keys"]
    assert "спокойн" in TEMPLATES["fn.plus.1"].lower()  # текст-триггер подавления, но не вырезан


def test_link_minus_x_plus_y_emitted() -> None:
    # синий(1) на позиции 8 (фрустрирован), коричневый(6) на позиции 1 (компенсирует)
    m = engine.compute(_NORM, [6, 2, 3, 4, 5, 0, 7, 1])
    out = assemble(m)
    assert "link.1.6" in out["hint_keys"]
    # связка приоритетнее одиночных
    assert priority_of("link.1.6") == 1


def test_all_returned_keys_exist_in_catalog() -> None:
    for l2 in ([0, 7, 6, 3, 5, 1, 2, 4], _NORM, [1, 2, 3, 4, 5, 6, 7, 0]):
        out = assemble(engine.compute(_NORM, l2))
        assert all(k in TEMPLATES for k in out["hint_keys"])
        assert len(out["hint_keys"]) == len(set(out["hint_keys"]))  # без дублей
