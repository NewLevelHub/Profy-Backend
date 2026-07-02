"""
Developer/methodologist tool — calibration check for the scoring pipeline.

Runs synthetic answer profiles through the same scoring + direction-matching
formulas used in production and prints human-readable results.  No database
or Redis connection required.

Usage (inside Docker):
    docker-compose -f docker-compose.yml -f docker-compose.local.yml exec api python scripts/calibration_check.py

Usage (locally, with venv activated):
    python scripts/calibration_check.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure UTF-8 output on Windows terminals that default to a narrow codepage.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from types import SimpleNamespace

from app.models.profile import AgeGroup
from app.models.question import QuestionBlock
from app.services.ai_service import CATEGORY_LABELS
from app.services.scoring_service import MOTIVATION_PREF_KEYS, PREFERENCE_KEYS, apply_answer, normalize_scores
from scripts.question_bank import QUESTIONS
from scripts.seed_directions import DIRECTIONS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

B = QuestionBlock
J = AgeGroup.junior
M = AgeGroup.middle
S = AgeGroup.senior


def _build_question_map() -> dict:
    """Index question bank by (block, age_group, order) → lightweight proxy object."""
    qmap: dict = {}
    for q in QUESTIONS:
        key = (q["block"], q["age_group"], q["order"])
        if q["type"] == "likert":
            options = {
                "type": "likert",
                "weights": q["weights"],
                "reversed": q.get("reversed", False),
            }
        else:
            options = q["options"]
        qmap[key] = SimpleNamespace(options=options)
    return qmap


def _score_profile(answers: list[tuple], qmap: dict) -> dict[str, float]:
    """
    Accumulate raw weights for each answer then normalize to 0-100.

    answers: list of ((block, age_group, order), option_index)
      - choice questions: option_index is 0-based index into options list
      - Likert questions: option_index 0-4 maps to Likert scores 1-5
    """
    raw: dict = {}
    for key, option_idx in answers:
        q = qmap.get(key)
        if q is None:
            print(f"  WARNING: question {key} not found in question bank")
            continue
        apply_answer(raw, q, option_idx)
    return normalize_scores(raw)


def _match_directions(normalized: dict[str, float]) -> list[tuple[str, str, int]]:
    """
    Score each direction and return top-5 as (name, slug, match_score).

    Formula mirrors report_service._match_directions_full and
    direction_service.match_directions — keep in sync if the formula changes.
    """
    scored: list[tuple[str, str, int]] = []
    for d in DIRECTIONS:
        required: dict[str, float] = d.get("required_scores") or {}
        bonus: dict[str, float] = d.get("bonus_scores") or {}
        if not required:
            continue
        req_scores = [
            min(normalized.get(cat, 0) / threshold, 1.2)
            for cat, threshold in required.items()
        ]
        base = sum(req_scores) / len(req_scores)
        bonus_total = sum(
            (normalized.get(cat, 0) / 100) * weight
            for cat, weight in bonus.items()
        )
        match_score = min(round(base * 75 + bonus_total), 99)
        scored.append((d["name"], d["slug"], match_score))
    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:5]


def _print_profile(name: str, normalized: dict[str, float], top5: list[tuple]) -> None:
    print(f"\n{'=' * 64}")
    print(f"  PROFILE: {name}")
    print(f"{'=' * 64}")

    print("\n  SCORED CATEGORIES (descending, non-zero):")
    non_zero = [(k, v) for k, v in normalized.items() if v > 0]
    non_zero.sort(key=lambda x: x[1], reverse=True)
    for cat, score in non_zero:
        label = CATEGORY_LABELS.get(cat, cat)
        bar = "█" * int(score / 5)
        print(f"    {cat:<24} {score:>5.1f}  {bar:<20}  {label}")

    print("\n  TOP-5 DIRECTIONS:")
    for i, (dname, _slug, mscore) in enumerate(top5, 1):
        filled = "█" * (mscore // 5)
        print(f"    {i}. [{mscore:>2}%] {filled:<20}  {dname}")
    print()


# ---------------------------------------------------------------------------
# Synthetic profiles
#
# Each answer: ((block, age_group, order), option_index)
#   choice  → 0-based index into question options list
#   likert  → 0-4  (maps internally to Likert scores 1-5)
# ---------------------------------------------------------------------------

PROFILES: dict[str, list[tuple]] = {

    # ── 1. Senior — Technology / Science ────────────────────────────────────
    "Senior — Technology / Science": [
        # interests
        ((B.interests, S, 1), 0),   # Разобраться как работает гаджет  → investigative+tech
        ((B.interests, S, 2), 0),   # Собрать прототип устройства       → realistic+tech
        ((B.interests, S, 3), 0),   # Технологии, инженерия             → investigative+tech
        ((B.interests, S, 4), 1),   # Решение сложной задачи            → investigative+logical
        ((B.interests, S, 5), 0),   # Технический помощник              → realistic+tech
        ((B.interests, S, 6), 0),   # Курс по программированию          → tech+investigative
        ((B.interests, S, 7), 0),   # Числа, статистика                 → conventional+numbers
        ((B.interests, S, 8), 0),   # За компьютером, анализирую        → investigative+tech
        # thinking
        ((B.thinking, S, 1), 0),    # Закономерность в данных           → logical+mathematical
        ((B.thinking, S, 2), 0),    # Разбиваю на части                 → logical+systematic
        ((B.thinking, S, 3), 0),    # Формулы и расчёты                 → mathematical+logical
        ((B.thinking, S, 4), 0),    # Логика и математика               → logical+mathematical
        ((B.thinking, S, 5), 0),    # Точные ответы                     → logical+mathematical
        ((B.thinking, S, 6), 3),    # По шагам, цепочкой                → logical
        # personality (Likert 0=1pt … 4=5pt)
        ((B.personality, S, 1), 4), # Пробую новое                      → openness:5
        ((B.personality, S, 2), 4), # Довожу до конца                   → conscientiousness:5
        ((B.personality, S, 3), 2), # Комфортно объяснять               → extraversion:3
        ((B.personality, S, 4), 2), # Работать в команде                → agreeableness+teamwork:3
        ((B.personality, S, 5), 4), # Спокойно к ошибкам               → emotional_stability:5
        ((B.personality, S, 6), 2), # Брать ответственность             → leadership:3
        ((B.personality, S, 7), 4), # Разобраться сам                   → independence:5
        # motivation (interest/challenge/etc. are non-scoring)
        ((B.motivation, S, 1), 0),  # Чтобы было интересно
        ((B.motivation, S, 2), 0),  # Решаю сложную задачу
        ((B.motivation, S, 3), 1),  # Возможность научиться сложному
        ((B.motivation, S, 4), 0),  # «Оригинально и креативно»         → creative_think
        ((B.motivation, S, 5), 1),  # Трудный и интересный
        ((B.motivation, S, 6), 0),  # Скучные задачи расстроили бы
        # academic
        ((B.academic, S, 1), 0),    # Математика/информатика            → mathematical+tech+numbers
        ((B.academic, S, 2), 0),    # ИИ и data science                 → tech+mathematical+investigative
        ((B.academic, S, 3), 0),    # Доказать теорему                  → mathematical+logical
        ((B.academic, S, 4), 2),    # Хакатоны и техпроекты             → tech+creative_think
        ((B.academic, S, 5), 0),    # Точные предметы                   → mathematical+numbers
        ((B.academic, S, 6), 3),    # IT/инженерный класс               → tech+spatial
        # directions
        ((B.directions, S, 1), 0),  # Технологии и разработка           → tech+investigative
        ((B.directions, S, 2), 0),  # Технологии умнее                  → tech
        ((B.directions, S, 3), 0),  # Инженер-новатор                   → tech+investigative+creative_think
        ((B.directions, S, 4), 0),  # Код, приложение, сайт             → tech+creative_think
        ((B.directions, S, 5), 0),  # Tech-команда / стартап            → tech+enterprising
        # goal (non-scoring)
        ((B.goal_clarification, S, 1), 2),
        ((B.goal_clarification, S, 2), 1),
        ((B.goal_clarification, S, 3), 1),
    ],

    # ── 2. Senior — Creative / Design ───────────────────────────────────────
    "Senior — Creative / Design": [
        # interests
        ((B.interests, S, 1), 1),   # Поснимать видео / визуал          → artistic+media
        ((B.interests, S, 2), 2),   # Дизайн/арт для мероприятия        → artistic+creative_think
        ((B.interests, S, 3), 1),   # Искусство, кино, дизайн, музыка   → artistic
        ((B.interests, S, 4), 2),   # Создал что-то красивое            → artistic
        ((B.interests, S, 5), 2),   # Дизайнер материалов/соцсетей      → artistic+media
        ((B.interests, S, 6), 2),   # Творческая мастерская             → artistic+creative_think
        ((B.interests, S, 7), 1),   # Работать с текстами / идеями      → verbal
        ((B.interests, S, 8), 1),   # В студии, создаю                  → artistic+creative_think
        # thinking
        ((B.thinking, S, 1), 1),    # Придумать оригинальную историю    → creative_think+verbal
        ((B.thinking, S, 2), 1),    # Неожиданный подход                → creative_think
        ((B.thinking, S, 3), 1),    # Формулировать мысли словами       → verbal
        ((B.thinking, S, 4), 3),    # Творческое задание без ответа     → creative_think
        ((B.thinking, S, 5), 1),    # Открытые задачи                   → creative_think
        ((B.thinking, S, 6), 1),    # Словами, точные формулировки      → verbal
        # personality
        ((B.personality, S, 1), 4),
        ((B.personality, S, 2), 3),
        ((B.personality, S, 3), 3),
        ((B.personality, S, 4), 2),
        ((B.personality, S, 5), 3),
        ((B.personality, S, 6), 1),
        ((B.personality, S, 7), 3),
        # motivation
        ((B.motivation, S, 1), 2),  # Чтобы создавать своё              → creative_think
        ((B.motivation, S, 2), 2),  # Когда создаю новое                → creative_think
        ((B.motivation, S, 3), 0),  # Свобода делать по-своему
        ((B.motivation, S, 4), 0),  # «Оригинально и креативно»         → creative_think
        ((B.motivation, S, 5), 0),  # Делать по-своему
        ((B.motivation, S, 6), 1),  # Нельзя ничего менять
        # academic
        ((B.academic, S, 1), 3),    # Языки/литература/журналистика     → verbal
        ((B.academic, S, 2), 1),    # Дизайн и цифровое искусство       → artistic+tech
        ((B.academic, S, 3), 3),    # Творческая работа или проект      → artistic+creative_think
        ((B.academic, S, 4), 3),    # Творческие конкурсы/выставки      → artistic
        ((B.academic, S, 5), 1),    # Гуманитарные с текстами           → verbal
        ((B.academic, S, 6), 2),    # Социально-гуманитарный            → verbal+social
        # directions
        ((B.directions, S, 1), 1),  # Творчество и дизайн               → artistic+creative_think
        ((B.directions, S, 2), 4),  # Новое искусство и культура        → artistic+creative_think
        ((B.directions, S, 3), 1),  # Художник или режиссёр             → artistic
        ((B.directions, S, 4), 1),  # Творческие работы / дизайн        → artistic
        ((B.directions, S, 5), 1),  # Студия, агентство, креатив        → artistic
        # goal
        ((B.goal_clarification, S, 1), 2),
        ((B.goal_clarification, S, 2), 1),
        ((B.goal_clarification, S, 3), 1),
    ],

    # ── 3. Senior — Social / Helping ────────────────────────────────────────
    "Senior — Social / Helping": [
        # interests
        ((B.interests, S, 1), 2),   # Помочь другу разобраться          → social+helping_motiv
        ((B.interests, S, 2), 3),   # Организовать команду              → enterprising+leadership
        ((B.interests, S, 3), 2),   # Психология, как помогать людям    → social+helping_motiv
        ((B.interests, S, 4), 3),   # Выступил и тебя услышали          → enterprising+extraversion
        ((B.interests, S, 5), 1),   # Куратор — объяснять новичков      → social+helping_motiv
        ((B.interests, S, 6), 3),   # Дебатный клуб                     → enterprising+verbal
        ((B.interests, S, 7), 2),   # Работать с людьми / интервью      → social+verbal
        ((B.interests, S, 8), 2),   # Встречи, переговоры, презентации  → enterprising+social+extraversion
        # thinking
        ((B.thinking, S, 1), 2),    # Почему возник конфликт            → social_think
        ((B.thinking, S, 2), 2),    # Пробую руками / проб и ошибок     → practical
        ((B.thinking, S, 3), 2),    # Чувствовать настроение людей      → social_think
        ((B.thinking, S, 4), 1),    # Эссе и аргументация               → verbal
        ((B.thinking, S, 5), 2),    # Задачи про людей                  → social_think
        ((B.thinking, S, 6), 2),    # Примеры и аналогии из жизни       → creative_think+social_think
        # personality
        ((B.personality, S, 1), 3),
        ((B.personality, S, 2), 3),
        ((B.personality, S, 3), 4), # Комфортно выступать               → extraversion:5
        ((B.personality, S, 4), 4), # Работать в команде                → agreeableness+teamwork:5
        ((B.personality, S, 5), 3),
        ((B.personality, S, 6), 4), # Брать ответственность             → leadership:5
        ((B.personality, S, 7), 1), # Предпочитаю разбираться сам — нет → independence:2
        # motivation
        ((B.motivation, S, 1), 2),  # Чтобы помогать людям              → helping_motiv
        ((B.motivation, S, 2), 1),  # Вижу что кому-то помог            → helping_motiv
        ((B.motivation, S, 3), 3),  # Стабильность и правила
        ((B.motivation, S, 4), 1),  # «Ты реально помог нам»            → helping_motiv
        ((B.motivation, S, 5), 3),  # Польза другим                     → helping_motiv
        ((B.motivation, S, 6), 3),  # Работаешь один — расстроит        → teamwork
        # academic
        ((B.academic, S, 1), 4),    # Обществознание/право/экономика    → social+enterprising+numbers
        ((B.academic, S, 2), 2),    # Психология и педагогика           → social+helping_motiv
        ((B.academic, S, 3), 1),    # Аргументированное эссе            → verbal
        ((B.academic, S, 4), 1),    # Дебаты, модель ООН                → verbal+enterprising
        ((B.academic, S, 5), 1),    # Гуманитарные предметы             → verbal
        ((B.academic, S, 6), 2),    # Социально-гуманитарный класс      → verbal+social
        # directions
        ((B.directions, S, 1), 2),  # Помощь людям и общество           → social+helping_motiv
        ((B.directions, S, 2), 3),  # Образование и общество лучше      → social+helping_motiv
        ((B.directions, S, 3), 2),  # Врач или учёный                   → science+helping_motiv
        ((B.directions, S, 4), 3),  # Запущенный проект/инициатива      → enterprising+leadership
        ((B.directions, S, 5), 3),  # Помогающая профессия              → social+helping_motiv
        # goal
        ((B.goal_clarification, S, 1), 2),
        ((B.goal_clarification, S, 2), 1),
        ((B.goal_clarification, S, 3), 1),
    ],

    # ── 4. Middle — Technology ───────────────────────────────────────────────
    "Middle — Technology": [
        # interests
        ((B.interests, M, 1), 0),   # Конструктор / собрать что-то      → realistic
        ((B.interests, M, 2), 0),   # Робототехника / информатика        → tech+investigative
        ((B.interests, M, 3), 0),   # Как устроено и как сделать        → investigative+tech+realistic
        ((B.interests, M, 4), 0),   # Техника и музыка                  → realistic+tech
        ((B.interests, M, 5), 2),   # Делать опыты и наблюдать          → science+investigative
        ((B.interests, M, 6), 0),   # Клуб изобретателей                → tech+investigative+creative_think
        # thinking
        ((B.thinking, M, 1), 0),    # Найти закономерность              → logical
        ((B.thinking, M, 2), 0),    # Считать в уме                     → mathematical
        ((B.thinking, M, 3), 0),    # Шаг за шагом                      → logical+systematic
        ((B.thinking, M, 4), 0),    # Математический ребус              → mathematical+logical
        ((B.thinking, M, 5), 0),    # Один правильный ответ             → logical
        # personality
        ((B.personality, M, 1), 4),
        ((B.personality, M, 2), 4),
        ((B.personality, M, 3), 2),
        ((B.personality, M, 4), 2),
        ((B.personality, M, 5), 4),
        # motivation
        ((B.motivation, M, 1), 0),  # Чтобы было интересно
        ((B.motivation, M, 2), 0),  # Справился со сложным
        ((B.motivation, M, 3), 2),  # Решать трудные задачки
        ((B.motivation, M, 4), 0),  # Весело и интересно
        ((B.motivation, M, 5), 0),  # Трудное, но интересное
        # academic
        ((B.academic, M, 1), 0),    # Математика                        → mathematical+numbers
        ((B.academic, M, 2), 0),    # Решать примеры и задачи           → mathematical
        ((B.academic, M, 3), 0),    # Счёт и логика                     → mathematical+logical
        ((B.academic, M, 4), 3),    # Компьютерный / робот              → tech
        ((B.academic, M, 5), 0),    # Программировать                   → tech+logical
        # directions
        ((B.directions, M, 1), 0),  # Игры и программы                  → tech+creative_think
        ((B.directions, M, 2), 0),  # Изобретать новое                  → investigative+creative_think+tech
        ((B.directions, M, 3), 0),  # Делать роботов и программы        → tech
        ((B.directions, M, 4), 0),  # Робототехнический турнир          → tech
        # goal
        ((B.goal_clarification, M, 1), 1),
        ((B.goal_clarification, M, 2), 0),
        ((B.goal_clarification, M, 3), 0),
    ],

    # ── 5. Junior — Explorer (wide interests) ───────────────────────────────
    "Junior — Explorer (wide interests)": [
        # interests
        ((B.interests, J, 1), 3),   # Разбираться как работают игрушки  → investigative
        ((B.interests, J, 2), 0),   # Пазлы и головоломки               → investigative+logical
        ((B.interests, J, 3), 0),   # Помогать и делиться               → social+helping_motiv
        ((B.interests, J, 4), 1),   # Космос, техника                   → investigative+tech
        ((B.interests, J, 5), 3),   # Придумать и нарисовать свой мир   → artistic+creative_think
        # thinking
        ((B.thinking, J, 1), 0),    # Собирать пазлы                    → spatial+logical
        ((B.thinking, J, 2), 1),    # Придумать как играть по-другому   → creative_think
        ((B.thinking, J, 3), 2),    # Сочинить сказку                   → creative_think+verbal
        ((B.thinking, J, 4), 2),    # Стихи и истории                   → verbal
        # personality
        ((B.personality, J, 1), 4),
        ((B.personality, J, 2), 3),
        ((B.personality, J, 3), 3),
        ((B.personality, J, 4), 4),
        # motivation
        ((B.motivation, J, 1), 2),  # Придумал что-то сам               → creative_think
        ((B.motivation, J, 2), 1),  # С друзьями вместе                 → teamwork
        ((B.motivation, J, 3), 0),  # Сложное и интересное
        ((B.motivation, J, 4), 0),  # Помогать и делиться               → helping_motiv
        # goal
        ((B.goal_clarification, J, 1), 0),
        ((B.goal_clarification, J, 2), 0),
        ((B.goal_clarification, J, 3), 0),
    ],
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    qmap = _build_question_map()
    print(f"\nCalibration check — {len(PROFILES)} profiles, {len(DIRECTIONS)} directions")
    for profile_name, answers in PROFILES.items():
        normalized = _score_profile(answers, qmap)
        top5 = _match_directions(normalized)
        _print_profile(profile_name, normalized, top5)


if __name__ == "__main__":
    main()
