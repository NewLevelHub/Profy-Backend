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
        ((B.interests, S, 9), 0),   # Технообзоры и туториалы           → tech+media
        ((B.interests, S, 10), 0),  # Сервис ремонта техники            → realistic+tech
        ((B.interests, S, 11), 0),  # Механизмы и инженерные экспонаты  → tech+realistic+investigative
        ((B.interests, S, 12), 2),  # Климат и природные явления        → science+nature
        # thinking
        ((B.thinking, S, 1), 0),    # Закономерность в данных           → logical+mathematical
        ((B.thinking, S, 2), 0),    # Разбиваю на части                 → logical+systematic
        ((B.thinking, S, 3), 0),    # Формулы и расчёты                 → mathematical+logical
        ((B.thinking, S, 4), 0),    # Логика и математика               → logical+mathematical
        ((B.thinking, S, 5), 0),    # Точные ответы                     → logical+mathematical
        ((B.thinking, S, 6), 3),    # По шагам, цепочкой                → logical
        ((B.thinking, S, 7), 0),    # План по темам и дням              → systematic+strategic
        ((B.thinking, S, 8), 0),    # Разберу где сломалось             → logical+systematic
        ((B.thinking, S, 9), 1),    # Пошаговый алгоритм                → systematic+logical
        ((B.thinking, S, 10), 0),   # Судоку, числовые                  → mathematical+logical
        ((B.thinking, S, 11), 1),   # Бюджет и расчёты                  → mathematical+numbers
        ((B.thinking, S, 12), 0),   # Плюсы и минусы списком            → logical+systematic
        # personality (Likert 0=1pt … 4=5pt)
        ((B.personality, S, 1), 4), # Пробую новое                      → openness:5
        ((B.personality, S, 2), 4), # Довожу до конца                   → conscientiousness:5
        ((B.personality, S, 3), 2), # Комфортно объяснять               → extraversion:3
        ((B.personality, S, 4), 2), # Работать в команде                → agreeableness+teamwork:3
        ((B.personality, S, 5), 4), # Спокойно к ошибкам               → emotional_stability:5
        ((B.personality, S, 6), 2), # Брать ответственность             → leadership:3
        ((B.personality, S, 7), 4), # Разобраться сам                   → independence:5
        ((B.personality, S, 8), 1), # Трудно сохранять спокойствие (rev) → emotional_stability:4
        ((B.personality, S, 9), 2), # Легко начинаю разговор            → extraversion:3
        ((B.personality, S, 10), 1),# Качественно делать свою часть     → conscientiousness+independence
        ((B.personality, S, 11), 0),# Разберу ошибки, составлю план     → conscientiousness+emotional_stability
        ((B.personality, S, 12), 1),# Свой проект или хобби             → independence+openness
        # motivation (interest/challenge/etc. are non-scoring)
        ((B.motivation, S, 1), 0),  # Чтобы было интересно
        ((B.motivation, S, 2), 0),  # Решаю сложную задачу
        ((B.motivation, S, 3), 1),  # Возможность научиться сложному
        ((B.motivation, S, 4), 0),  # «Оригинально и креативно»         → creative_think
        ((B.motivation, S, 5), 1),  # Трудный и интересный
        ((B.motivation, S, 6), 0),  # Скучные задачи расстроили бы
        ((B.motivation, S, 7), 0),  # Сам предмет интересен
        ((B.motivation, S, 8), 1),  # Стабильная позиция
        ((B.motivation, S, 9), 0),  # Процесс создания нового           → creative_think
        ((B.motivation, S, 10), 0), # Азарт нерешённой задачи
        ((B.motivation, S, 11), 1), # Амбициозные цели
        ((B.motivation, S, 12), 3), # Признанный эксперт
        # academic
        ((B.academic, S, 1), 0),    # Математика/информатика            → mathematical+tech+numbers
        ((B.academic, S, 2), 0),    # ИИ и data science                 → tech+mathematical+investigative
        ((B.academic, S, 3), 0),    # Доказать теорему                  → mathematical+logical
        ((B.academic, S, 4), 2),    # Хакатоны и техпроекты             → tech+creative_think
        ((B.academic, S, 5), 0),    # Точные предметы                   → mathematical+numbers
        ((B.academic, S, 6), 3),    # IT/инженерный класс               → tech+spatial
        ((B.academic, S, 7), 0),    # Докопаться до сути самому         → investigative+logical
        ((B.academic, S, 8), 0),    # Анализ данных и программирование  → tech+numbers
        # directions
        ((B.directions, S, 1), 0),  # Технологии и разработка           → tech+investigative
        ((B.directions, S, 2), 0),  # Технологии умнее                  → tech
        ((B.directions, S, 3), 0),  # Инженер-новатор                   → tech+investigative+creative_think
        ((B.directions, S, 4), 0),  # Код, приложение, сайт             → tech+creative_think
        ((B.directions, S, 5), 0),  # Tech-команда / стартап            → tech+enterprising
        ((B.directions, S, 6), 0),  # Стажировка в IT-компании          → tech+investigative
        ((B.directions, S, 7), 0),  # Приложение или бот                → tech+creative_think
        ((B.directions, S, 8), 0),  # «Как устроены нейросети»          → tech+investigative
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
        ((B.interests, S, 9), 1),   # Влоги, эстетика, креатив          → media+artistic
        ((B.interests, S, 10), 3),  # Контент для соцсетей              → media+artistic
        ((B.interests, S, 11), 2),  # Интерактивное цифровое искусство  → artistic+creative_think
        ((B.interests, S, 12), 3),  # Тренды культуры и дизайна         → artistic+media
        # thinking
        ((B.thinking, S, 1), 1),    # Придумать оригинальную историю    → creative_think+verbal
        ((B.thinking, S, 2), 1),    # Неожиданный подход                → creative_think
        ((B.thinking, S, 3), 1),    # Формулировать мысли словами       → verbal
        ((B.thinking, S, 4), 3),    # Творческое задание без ответа     → creative_think
        ((B.thinking, S, 5), 1),    # Открытые задачи                   → creative_think
        ((B.thinking, S, 6), 1),    # Словами, точные формулировки      → verbal
        ((B.thinking, S, 7), 2),    # Схемы и интеллект-карты           → spatial
        ((B.thinking, S, 8), 1),    # Обходное решение                  → practical
        ((B.thinking, S, 9), 3),    # Метафора или аналогия             → creative_think+verbal
        ((B.thinking, S, 10), 3),   # 20 применений предмету            → creative_think
        ((B.thinking, S, 11), 3),   # Решать вопросы по ситуации        → practical
        ((B.thinking, S, 12), 3),   # Пробую малый шаг и корректирую    → practical+creative_think
        # personality
        ((B.personality, S, 1), 4),
        ((B.personality, S, 2), 3),
        ((B.personality, S, 3), 3),
        ((B.personality, S, 4), 2),
        ((B.personality, S, 5), 3),
        ((B.personality, S, 6), 1),
        ((B.personality, S, 7), 3),
        ((B.personality, S, 8), 2),  # (reversed)                       → emotional_stability:3
        ((B.personality, S, 9), 3),  # Легко начинаю разговор           → extraversion:4
        ((B.personality, S, 10), 3), # Неожиданные идеи                 → openness
        ((B.personality, S, 11), 2), # Обсужу с друзьями                → extraversion+agreeableness
        ((B.personality, S, 12), 1), # Свой проект или хобби            → independence+openness
        # motivation
        ((B.motivation, S, 1), 2),  # Чтобы создавать своё              → creative_think
        ((B.motivation, S, 2), 2),  # Когда создаю новое                → creative_think
        ((B.motivation, S, 3), 0),  # Свобода делать по-своему
        ((B.motivation, S, 4), 0),  # «Оригинально и креативно»         → creative_think
        ((B.motivation, S, 5), 0),  # Делать по-своему
        ((B.motivation, S, 6), 1),  # Нельзя ничего менять
        ((B.motivation, S, 7), 0),  # Сам предмет интересен
        ((B.motivation, S, 8), 2),  # Творческая работа с признанием    → creative_think
        ((B.motivation, S, 9), 0),  # Процесс создания нового           → creative_think
        ((B.motivation, S, 10), 2), # Чтобы результат впечатлил
        ((B.motivation, S, 11), 0), # Свобода и доверие
        ((B.motivation, S, 12), 0), # Создал чего не было               → creative_think
        # academic
        ((B.academic, S, 1), 3),    # Языки/литература/журналистика     → verbal
        ((B.academic, S, 2), 1),    # Дизайн и цифровое искусство       → artistic+tech
        ((B.academic, S, 3), 3),    # Творческая работа или проект      → artistic+creative_think
        ((B.academic, S, 4), 3),    # Творческие конкурсы/выставки      → artistic
        ((B.academic, S, 5), 1),    # Гуманитарные с текстами           → verbal
        ((B.academic, S, 6), 2),    # Социально-гуманитарный            → verbal+social
        ((B.academic, S, 7), 3),    # Применять на практике             → realistic+practical
        ((B.academic, S, 8), 2),    # Медиа и сторителлинг              → media+verbal
        # directions
        ((B.directions, S, 1), 1),  # Творчество и дизайн               → artistic+creative_think
        ((B.directions, S, 2), 4),  # Новое искусство и культура        → artistic+creative_think
        ((B.directions, S, 3), 1),  # Художник или режиссёр             → artistic
        ((B.directions, S, 4), 1),  # Творческие работы / дизайн        → artistic
        ((B.directions, S, 5), 1),  # Студия, агентство, креатив        → artistic
        ((B.directions, S, 6), 1),  # Креативное агентство              → artistic+media
        ((B.directions, S, 7), 1),  # Медиапроект — канал, подкаст      → media+artistic
        ((B.directions, S, 8), 1),  # «Как снимают большое кино»        → artistic+media
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
        ((B.interests, S, 9), 2),   # Разборы книг и идей               → verbal+investigative
        ((B.interests, S, 10), 1),  # Вожатый или наставник             → social+helping_motiv
        ((B.interests, S, 11), 1),  # Зал про мозг и эксперименты       → science+investigative
        ((B.interests, S, 12), 1),  # Почему люди ведут себя так        → investigative+social
        # thinking
        ((B.thinking, S, 1), 2),    # Почему возник конфликт            → social_think
        ((B.thinking, S, 2), 2),    # Пробую руками / проб и ошибок     → practical
        ((B.thinking, S, 3), 2),    # Чувствовать настроение людей      → social_think
        ((B.thinking, S, 4), 1),    # Эссе и аргументация               → verbal
        ((B.thinking, S, 5), 2),    # Задачи про людей                  → social_think
        ((B.thinking, S, 6), 2),    # Примеры и аналогии из жизни       → creative_think+social_think
        ((B.thinking, S, 7), 3),    # Готовиться вдвоём, объяснять      → social_think+verbal
        ((B.thinking, S, 8), 3),    # Поговорю с командой               → social_think
        ((B.thinking, S, 9), 2),    # Разбор на реальном примере        → practical
        ((B.thinking, S, 10), 2),   # Детективная история               → logical+social_think
        ((B.thinking, S, 11), 2),   # Договориться со всеми             → social_think+verbal
        ((B.thinking, S, 12), 1),   # Советуюсь с людьми                → social_think
        # personality
        ((B.personality, S, 1), 3),
        ((B.personality, S, 2), 3),
        ((B.personality, S, 3), 4), # Комфортно выступать               → extraversion:5
        ((B.personality, S, 4), 4), # Работать в команде                → agreeableness+teamwork:5
        ((B.personality, S, 5), 3),
        ((B.personality, S, 6), 4), # Брать ответственность             → leadership:5
        ((B.personality, S, 7), 1), # Предпочитаю разбираться сам — нет → independence:2
        ((B.personality, S, 8), 2),  # (reversed)                       → emotional_stability:3
        ((B.personality, S, 9), 4),  # Легко начинаю разговор           → extraversion:5
        ((B.personality, S, 10), 2), # Поддерживать и помогать          → agreeableness+teamwork
        ((B.personality, S, 11), 2), # Обсужу с друзьями/наставником    → extraversion+agreeableness
        ((B.personality, S, 12), 3), # Помочь родным или другу          → agreeableness
        # motivation
        ((B.motivation, S, 1), 2),  # Чтобы помогать людям              → helping_motiv
        ((B.motivation, S, 2), 1),  # Вижу что кому-то помог            → helping_motiv
        ((B.motivation, S, 3), 3),  # Стабильность и правила
        ((B.motivation, S, 4), 1),  # «Ты реально помог нам»            → helping_motiv
        ((B.motivation, S, 5), 3),  # Польза другим                     → helping_motiv
        ((B.motivation, S, 6), 3),  # Работаешь один — расстроит        → teamwork
        ((B.motivation, S, 7), 2),  # Шаг к надёжному будущему
        ((B.motivation, S, 8), 3),  # Работа меняет жизни людей         → helping_motiv
        ((B.motivation, S, 9), 3),  # Польза проекта людям              → helping_motiv
        ((B.motivation, S, 10), 3), # Помогаю тому кто рассчитывает     → helping_motiv
        ((B.motivation, S, 11), 3), # Ясность и стабильность
        ((B.motivation, S, 12), 1), # Помог многим людям                → helping_motiv
        # academic
        ((B.academic, S, 1), 4),    # Обществознание/право/экономика    → social+enterprising+numbers
        ((B.academic, S, 2), 2),    # Психология и педагогика           → social+helping_motiv
        ((B.academic, S, 3), 1),    # Аргументированное эссе            → verbal
        ((B.academic, S, 4), 1),    # Дебаты, модель ООН                → verbal+enterprising
        ((B.academic, S, 5), 1),    # Гуманитарные предметы             → verbal
        ((B.academic, S, 6), 2),    # Социально-гуманитарный класс      → verbal+social
        ((B.academic, S, 7), 2),    # Обсуждать и разбирать вслух       → social+verbal
        ((B.academic, S, 8), 3),    # Психология общения                → social+social_think
        # directions
        ((B.directions, S, 1), 2),  # Помощь людям и общество           → social+helping_motiv
        ((B.directions, S, 2), 3),  # Образование и общество лучше      → social+helping_motiv
        ((B.directions, S, 3), 2),  # Врач или учёный                   → science+helping_motiv
        ((B.directions, S, 4), 3),  # Запущенный проект/инициатива      → enterprising+leadership
        ((B.directions, S, 5), 3),  # Помогающая профессия              → social+helping_motiv
        ((B.directions, S, 6), 2),  # Клиника или лаборатория           → science+helping_motiv
        ((B.directions, S, 7), 3),  # Социальная инициатива             → social+helping_motiv
        ((B.directions, S, 8), 4),  # «Как право меняет общество»       → verbal+social
        # goal
        ((B.goal_clarification, S, 1), 2),
        ((B.goal_clarification, S, 2), 1),
        ((B.goal_clarification, S, 3), 1),
    ],

    # ── 4. Senior — Business / Entrepreneur ─────────────────────────────────
    "Senior — Business / Entrepreneur": [
        # interests
        ((B.interests, S, 1), 3),   # Идея для проекта или бизнеса      → enterprising+creative_think
        ((B.interests, S, 2), 3),   # Организовать команду              → enterprising+leadership
        ((B.interests, S, 3), 3),   # Стартапы, предприниматели         → enterprising:3
        ((B.interests, S, 4), 3),   # Выступил и услышали               → enterprising+extraversion
        ((B.interests, S, 5), 3),   # Координатор                       → enterprising+conventional+leadership
        ((B.interests, S, 6), 3),   # Бизнес-интенсив / дебаты          → enterprising+verbal
        ((B.interests, S, 7), 0),   # Числа, статистика, расчёты        → conventional+numbers+math
        ((B.interests, S, 8), 2),   # Встречи, переговоры               → enterprising+social+extraversion
        ((B.interests, S, 9), 3),   # Аналитика и рейтинги              → numbers+conventional
        ((B.interests, S, 10), 2),  # Промоутер или продавец            → enterprising+extraversion
        ((B.interests, S, 11), 0),  # Механизмы и инженерное            → tech+realistic+investigative
        ((B.interests, S, 12), 0),  # Статистика финансов               → numbers+conventional
        # thinking
        ((B.thinking, S, 1), 4),    # Стратегия на шаги вперёд          → strategic
        ((B.thinking, S, 2), 3),    # Картина целиком, планирую         → strategic+systematic
        ((B.thinking, S, 3), 2),    # Настроение и мотивы людей         → social_think
        ((B.thinking, S, 4), 2),    # Инженерный кейс                   → spatial+systematic+strategic
        ((B.thinking, S, 5), 3),    # Системы и процессы                → systematic+strategic
        ((B.thinking, S, 6), 1),    # Словами, формулировки             → verbal
        ((B.thinking, S, 7), 0),    # План по темам и дням              → systematic+strategic
        ((B.thinking, S, 8), 2),    # Влияние на цель, переиграю план   → strategic
        ((B.thinking, S, 9), 0),    # График или диаграмма              → spatial+numbers
        ((B.thinking, S, 10), 2),   # Детективная история               → logical+social_think
        ((B.thinking, S, 11), 0),   # Маршрут и логистика               → strategic+systematic
        ((B.thinking, S, 12), 2),   # Сценарии на годы вперёд           → strategic
        # personality
        ((B.personality, S, 1), 3),
        ((B.personality, S, 2), 3),
        ((B.personality, S, 3), 4), # Комфортно выступать               → extraversion:5
        ((B.personality, S, 4), 3),
        ((B.personality, S, 5), 3),
        ((B.personality, S, 6), 4), # Вести за собой                    → leadership:5
        ((B.personality, S, 7), 2),
        ((B.personality, S, 8), 1),  # (reversed)                       → emotional_stability:4
        ((B.personality, S, 9), 4),  # Легко начинаю разговор           → extraversion:5
        ((B.personality, S, 10), 0), # Координировать и распределять    → leadership:2
        ((B.personality, S, 11), 1), # Быстро переключусь               → emotional_stability
        ((B.personality, S, 12), 0), # Встретиться с компанией          → extraversion
        # motivation
        ((B.motivation, S, 1), 1),  # Хорошо зарабатывать
        ((B.motivation, S, 2), 3),  # Признают и ценят
        ((B.motivation, S, 3), 2),  # Хорошее вознаграждение
        ((B.motivation, S, 4), 2),  # «Ты лучший в этом»
        ((B.motivation, S, 5), 2),  # Результат увидят многие
        ((B.motivation, S, 6), 1),  # Нельзя ничего менять
        ((B.motivation, S, 7), 3),  # Зависит будущий доход
        ((B.motivation, S, 8), 0),  # Своё дело                         → enterprising
        ((B.motivation, S, 9), 1),  # Заработать на идее                → enterprising
        ((B.motivation, S, 10), 2), # Впечатлить результатом
        ((B.motivation, S, 11), 0), # Свобода и доверие
        ((B.motivation, S, 12), 2), # Успешное прибыльное дело          → enterprising
        # academic
        ((B.academic, S, 1), 4),    # Обществознание/право/экономика    → social+enterprising+numbers
        ((B.academic, S, 2), 3),    # Бизнес и менеджмент               → enterprising:3
        ((B.academic, S, 3), 1),    # Аргументированное эссе            → verbal
        ((B.academic, S, 4), 1),    # Дебаты, модель ООН                → verbal+enterprising
        ((B.academic, S, 5), 0),    # Точные предметы с формулами       → mathematical+numbers
        ((B.academic, S, 6), 2),    # Социально-гуманитарный            → verbal+social
        ((B.academic, S, 7), 2),    # Обсуждать и разбирать вслух       → social+verbal
        ((B.academic, S, 8), 4),    # Предпринимательство и финансы     → enterprising+numbers
        # directions
        ((B.directions, S, 1), 3),  # Бизнес и предпринимательство      → enterprising:3
        ((B.directions, S, 2), 3),  # Образование и общество            → social+helping_motiv
        ((B.directions, S, 3), 3),  # Основатель компании               → enterprising:3
        ((B.directions, S, 4), 3),  # Запущенный проект/инициатива      → enterprising+leadership
        ((B.directions, S, 5), 0),  # Tech-команда / стартап            → tech+enterprising
        ((B.directions, S, 6), 3),  # Бизнес-инкубатор                  → enterprising+leadership
        ((B.directions, S, 7), 4),  # Бизнес с реальными продажами      → enterprising:3
        ((B.directions, S, 8), 3),  # «Компания с нуля»                 → enterprising:3
        # goal
        ((B.goal_clarification, S, 1), 2),
        ((B.goal_clarification, S, 2), 1),
        ((B.goal_clarification, S, 3), 2),
    ],

    # ── 5. Middle — Technology ───────────────────────────────────────────────
    "Middle — Technology": [
        # interests
        ((B.interests, M, 1), 0),   # Конструктор / собрать что-то      → realistic
        ((B.interests, M, 2), 0),   # Робототехника / информатика        → tech+investigative
        ((B.interests, M, 3), 0),   # Как устроено и как сделать        → investigative+tech+realistic
        ((B.interests, M, 4), 0),   # Техника и музыка                  → realistic+tech
        ((B.interests, M, 5), 2),   # Делать опыты и наблюдать          → science+investigative
        ((B.interests, M, 6), 0),   # Клуб изобретателей                → tech+investigative+creative_think
        ((B.interests, M, 7), 0),   # Действующая модель                → realistic+tech
        ((B.interests, M, 8), 0),   # Головоломки и квесты              → investigative+logical
        ((B.interests, M, 9), 2),   # Найти и проверить факты           → investigative
        ((B.interests, M, 10), 1),  # Программы и настройки             → tech+investigative
        ((B.interests, M, 11), 0),  # Музей техники                     → tech+realistic+investigative
        ((B.interests, M, 12), 2),  # Чинить и настраивать вещи         → realistic+tech
        # thinking
        ((B.thinking, M, 1), 0),    # Найти закономерность              → logical
        ((B.thinking, M, 2), 0),    # Считать в уме                     → mathematical
        ((B.thinking, M, 3), 0),    # Шаг за шагом                      → logical+systematic
        ((B.thinking, M, 4), 0),    # Математический ребус              → mathematical+logical
        ((B.thinking, M, 5), 0),    # Один правильный ответ             → logical
        ((B.thinking, M, 6), 1),    # Слежу за ходами соперника         → logical+social_think
        ((B.thinking, M, 7), 0),    # Инструкция по шагам               → systematic
        ((B.thinking, M, 8), 0),    # Понять почему случилось           → social_think
        ((B.thinking, M, 9), 0),    # Числа и даты                      → mathematical
        ((B.thinking, M, 10), 0),   # Разбиваю на части                 → logical+systematic
        ((B.thinking, M, 11), 0),   # Нарисую план с поворотами         → spatial
        ((B.thinking, M, 12), 3),   # Измерю что поместится             → mathematical+spatial
        # personality
        ((B.personality, M, 1), 4),
        ((B.personality, M, 2), 4),
        ((B.personality, M, 3), 2),
        ((B.personality, M, 4), 2),
        ((B.personality, M, 5), 4),
        ((B.personality, M, 6), 2),  # Вести за собой ребят             → leadership:3
        ((B.personality, M, 7), 4),  # Сначала пробую сам               → independence:5
        ((B.personality, M, 8), 1),  # Аккуратно свою часть             → conscientiousness+independence
        ((B.personality, M, 9), 3),  # Позанимаюсь сам                  → independence+conscientiousness
        ((B.personality, M, 10), 3), # Помогу если попросит             → agreeableness:1
        ((B.personality, M, 11), 0), # Один — сам продумаю              → independence:2
        ((B.personality, M, 12), 0), # Спокойно переделаю               → emotional_stability+conscientiousness
        # motivation
        ((B.motivation, M, 1), 0),  # Чтобы было интересно
        ((B.motivation, M, 2), 0),  # Справился со сложным
        ((B.motivation, M, 3), 2),  # Решать трудные задачки
        ((B.motivation, M, 4), 0),  # Весело и интересно
        ((B.motivation, M, 5), 0),  # Трудное, но интересное
        ((B.motivation, M, 6), 0),  # Интересно узнавать новое
        ((B.motivation, M, 7), 0),  # «Как оригинально!»                → creative_think
        ((B.motivation, M, 8), 0),  # Хочу справиться сам
        ((B.motivation, M, 9), 0),  # Накоплю на цель
        ((B.motivation, M, 10), 1), # Сложные уровни
        ((B.motivation, M, 11), 3), # Спокойно почитаю
        ((B.motivation, M, 12), 0), # Интересная работа
        # academic
        ((B.academic, M, 1), 0),    # Математика                        → mathematical+numbers
        ((B.academic, M, 2), 0),    # Решать примеры и задачи           → mathematical
        ((B.academic, M, 3), 0),    # Счёт и логика                     → mathematical+logical
        ((B.academic, M, 4), 3),    # Компьютерный / робот              → tech
        ((B.academic, M, 5), 0),    # Программировать                   → tech+logical
        ((B.academic, M, 6), 1),    # Задачи на смекалку                → mathematical+logical
        ((B.academic, M, 7), 0),    # Формулы и правила счёта           → mathematical
        ((B.academic, M, 8), 0),    # Программирование и роботы         → tech+logical
        # directions
        ((B.directions, M, 1), 0),  # Игры и программы                  → tech+creative_think
        ((B.directions, M, 2), 0),  # Изобретать новое                  → investigative+creative_think+tech
        ((B.directions, M, 3), 0),  # Делать роботов и программы        → tech
        ((B.directions, M, 4), 0),  # Робототехнический турнир          → tech
        ((B.directions, M, 5), 0),  # Фильм про изобретателя            → tech+investigative+creative_think
        ((B.directions, M, 6), 0),  # Приложение для жителей            → tech+creative_think
        ((B.directions, M, 7), 0),  # Научить робота трюку              → tech+logical
        ((B.directions, M, 8), 0),  # Создаю программы и игры           → tech
        # goal
        ((B.goal_clarification, M, 1), 1),
        ((B.goal_clarification, M, 2), 0),
        ((B.goal_clarification, M, 3), 0),
    ],

    # ── 6. Middle — Creative / Artistic ──────────────────────────────────────
    "Middle — Creative / Artistic": [
        # interests
        ((B.interests, M, 1), 2),   # Порисовать / придумать историю    → artistic+creative_think
        ((B.interests, M, 2), 1),   # Рисование, музыка, театр          → artistic
        ((B.interests, M, 3), 1),   # Видео про творчество              → artistic
        ((B.interests, M, 4), 1),   # Оформлять и делать декорации      → artistic+creative_think
        ((B.interests, M, 5), 1),   # Читать и писать сочинения         → verbal
        ((B.interests, M, 6), 1),   # Художественная студия             → artistic
        ((B.interests, M, 7), 2),   # Картина, поделка, номер           → artistic+creative_think
        ((B.interests, M, 8), 1),   # Строить свои миры                 → creative_think+tech+artistic
        ((B.interests, M, 9), 1),   # Оформить и нарисовать             → artistic
        ((B.interests, M, 10), 0),  # Монтировать видео/анимации        → media+artistic
        ((B.interests, M, 11), 2),  # Выставка или театр                → artistic
        ((B.interests, M, 12), 3),  # Ролики для своего канала          → media+enterprising
        # thinking
        ((B.thinking, M, 1), 1),    # Придумать концовку истории        → creative_think+verbal
        ((B.thinking, M, 2), 1),    # Сочинять и рассказывать           → verbal+creative_think
        ((B.thinking, M, 3), 1),    # Хитрый способ                     → creative_think
        ((B.thinking, M, 4), 1),    # Написать рассказ                  → verbal
        ((B.thinking, M, 5), 1),    # Придумать что угодно              → creative_think
        ((B.thinking, M, 6), 3),    # Неожиданный ход                   → creative_think
        ((B.thinking, M, 7), 3),    # Своё, не как на коробке           → creative_think
        ((B.thinking, M, 8), 1),    # Подберу правильные слова          → verbal+social_think
        ((B.thinking, M, 9), 1),    # Истории и стихи                   → verbal
        ((B.thinking, M, 10), 1),   # Свой способ решения               → creative_think
        ((B.thinking, M, 11), 3),   # Фото ориентиров                   → spatial+creative_think
        ((B.thinking, M, 12), 0),   # Крепость или костюм               → creative_think
        # personality
        ((B.personality, M, 1), 4),  # Свои идеи                        → openness:5
        ((B.personality, M, 2), 2),
        ((B.personality, M, 3), 3),
        ((B.personality, M, 4), 2),
        ((B.personality, M, 5), 2),
        ((B.personality, M, 6), 1),
        ((B.personality, M, 7), 3),  # Сначала пробую сам               → independence:4
        ((B.personality, M, 8), 3),  # Придумывать идеи                 → openness:2
        ((B.personality, M, 9), 1),  # Возьму себя в руки               → emotional_stability:2
        ((B.personality, M, 10), 1), # Позову в компанию                → agreeableness+extraversion
        ((B.personality, M, 11), 1), # В паре с другом                  → teamwork+agreeableness
        ((B.personality, M, 12), 1), # Обыграю недостаток               → openness:2
        # motivation
        ((B.motivation, M, 1), 2),  # Придумать что-то своё             → creative_think
        ((B.motivation, M, 2), 2),  # Создал что-то новое               → creative_think
        ((B.motivation, M, 3), 0),  # Делать по-своему
        ((B.motivation, M, 4), 0),  # Весело и интересно
        ((B.motivation, M, 5), 2),  # Творческое, фантазировать         → creative_think
        ((B.motivation, M, 6), 0),  # Интересно узнавать новое
        ((B.motivation, M, 7), 0),  # «Как оригинально!»                → creative_think
        ((B.motivation, M, 8), 3),  # Обходной способ                   → creative_think+freedom
        ((B.motivation, M, 9), 1),  # Материалы, ещё больше товаров     → enterprising
        ((B.motivation, M, 10), 0), # Свои правила и ходы
        ((B.motivation, M, 11), 2), # Придумаю игру или сценку          → creative_think
        ((B.motivation, M, 12), 0), # Интересная работа
        # academic
        ((B.academic, M, 1), 4),    # ИЗО / музыка                      → artistic
        ((B.academic, M, 2), 3),    # Поделка или проект                → realistic+artistic
        ((B.academic, M, 3), 2),    # Хвалят в творчестве               → artistic
        ((B.academic, M, 4), 1),    # Литературный / театральный        → verbal+artistic
        ((B.academic, M, 5), 1),    # Красиво рисовать                  → artistic
        ((B.academic, M, 6), 2),    # Сочиняем свой рассказ             → verbal
        ((B.academic, M, 7), 1),    # Стихи и определения               → verbal
        ((B.academic, M, 8), 1),    # Театр и актёрское мастерство      → artistic+extraversion
        # directions
        ((B.directions, M, 1), 1),  # Художник, музыкант, блогер        → artistic+media
        ((B.directions, M, 2), 1),  # Творить красивое                  → artistic
        ((B.directions, M, 3), 1),  # Рисовать мультфильмы или игры     → artistic+media
        ((B.directions, M, 4), 1),  # Конкурс рисунка или песни         → artistic
        ((B.directions, M, 5), 1),  # Фильм про художника               → artistic
        ((B.directions, M, 6), 1),  # Яркие муралы                      → artistic
        ((B.directions, M, 7), 2),  # Организовать праздник             → enterprising+leadership
        ((B.directions, M, 8), 1),  # Рисую, снимаю, выступаю           → artistic+media
        # goal
        ((B.goal_clarification, M, 1), 1),
        ((B.goal_clarification, M, 2), 0),
        ((B.goal_clarification, M, 3), 0),
    ],

    # ── 7. Middle — Social / Helper ──────────────────────────────────────────
    "Middle — Social / Helper": [
        # interests
        ((B.interests, M, 1), 3),   # Поболтать и поиграть с друзьями   → social+extraversion
        ((B.interests, M, 2), 4),   # Дебаты или школьный актив         → enterprising+verbal+social
        ((B.interests, M, 3), 3),   # Игры, блоги, свой канал           → media+enterprising
        ((B.interests, M, 4), 2),   # Встречать гостей и помогать       → social+helping_motiv
        ((B.interests, M, 5), 1),   # Читать и писать сочинения         → verbal
        ((B.interests, M, 6), 2),   # Клуб помощи и волонтёрства        → social+helping_motiv
        ((B.interests, M, 7), 3),   # Стенд про животных                → nature
        ((B.interests, M, 8), 2),   # Командные игры с друзьями         → social+extraversion
        ((B.interests, M, 9), 3),   # Раздать газету, рассказать всем   → social+extraversion+enterprising
        ((B.interests, M, 10), 3),  # Фильмы про природу                → nature
        ((B.interests, M, 11), 2),  # Выставка или театр                → artistic
        ((B.interests, M, 12), 0),  # Ухаживать за животными            → nature
        # thinking
        ((B.thinking, M, 1), 2),    # Почему герой поступил так         → social_think
        ((B.thinking, M, 2), 2),    # Понимать что чувствуют            → social_think
        ((B.thinking, M, 3), 2),    # Прошу помощи, советуюсь           → social_think
        ((B.thinking, M, 4), 1),    # Написать рассказ                  → verbal
        ((B.thinking, M, 5), 2),    # Задача про дружбу и людей         → social_think
        ((B.thinking, M, 6), 1),    # Слежу за ходами соперника         → logical+social_think
        ((B.thinking, M, 7), 2),    # Сразу пробую собирать             → practical
        ((B.thinking, M, 8), 1),    # Поговорю с каждым                 → verbal+social_think
        ((B.thinking, M, 9), 1),    # Истории и стихи                   → verbal
        ((B.thinking, M, 10), 2),   # Обсуждаю с кем-нибудь             → social_think
        ((B.thinking, M, 11), 2),   # Встречу и проведу сам             → practical
        ((B.thinking, M, 12), 1),   # Приспособлю для дела              → practical
        # personality
        ((B.personality, M, 1), 2),
        ((B.personality, M, 2), 2),
        ((B.personality, M, 3), 3),  # В центре внимания                → extraversion:4
        ((B.personality, M, 4), 4),  # Работать вместе                  → agreeableness+teamwork:5
        ((B.personality, M, 5), 3),
        ((B.personality, M, 6), 3),  # Вести за собой ребят             → leadership:4
        ((B.personality, M, 7), 1),  # Сначала сам — не про меня        → independence:2
        ((B.personality, M, 8), 2),  # Помогать тем у кого не выходит   → agreeableness:2
        ((B.personality, M, 9), 2),  # Попрошу объяснить                → agreeableness:1
        ((B.personality, M, 10), 1), # Позову в нашу компанию           → agreeableness+extraversion
        ((B.personality, M, 11), 2), # В большой команде                → teamwork+extraversion
        ((B.personality, M, 12), 2), # Попрошу помочь доделать          → agreeableness:1
        # motivation
        ((B.motivation, M, 1), 1),  # Помочь кому-то                    → helping_motiv
        ((B.motivation, M, 2), 1),  # Полезное для других               → helping_motiv
        ((B.motivation, M, 3), 1),  # Работать с друзьями               → teamwork
        ((B.motivation, M, 4), 1),  # Помогать людям                    → helping_motiv
        ((B.motivation, M, 5), 1),  # Простое и спокойное
        ((B.motivation, M, 6), 3),  # Полезное для других               → helping_motiv
        ((B.motivation, M, 7), 1),  # «Ты очень помог!»                 → helping_motiv
        ((B.motivation, M, 8), 1),  # Позову друга — вместе             → teamwork
        ((B.motivation, M, 9), 2),  # Подарок близким                   → helping_motiv
        ((B.motivation, M, 10), 2), # Играть с командой                 → teamwork
        ((B.motivation, M, 11), 0), # Помогу учителю или младшим        → helping_motiv
        ((B.motivation, M, 12), 2), # Полезной для людей                → helping_motiv
        # academic
        ((B.academic, M, 1), 1),    # Русский / литература              → verbal
        ((B.academic, M, 2), 1),    # Читать и писать                   → verbal
        ((B.academic, M, 3), 1),    # Сочинения и пересказы             → verbal
        ((B.academic, M, 4), 1),    # Литературный / театральный        → verbal+artistic
        ((B.academic, M, 5), 3),    # Выступать и говорить              → verbal+extraversion
        ((B.academic, M, 6), 2),    # Сочиняем свой рассказ             → verbal
        ((B.academic, M, 7), 1),    # Стихи и определения               → verbal
        ((B.academic, M, 8), 1),    # Театр и актёрское мастерство      → artistic+extraversion
        # directions
        ((B.directions, M, 1), 2),  # Врач, учитель, помогает           → social+helping_motiv
        ((B.directions, M, 2), 2),  # Помогать и заботиться             → social+helping_motiv
        ((B.directions, M, 3), 2),  # Лечить людей или животных         → science+helping_motiv+nature
        ((B.directions, M, 4), 1),  # Конкурс рисунка или песни         → artistic
        ((B.directions, M, 5), 2),  # Врач который спасает              → science+helping_motiv+social
        ((B.directions, M, 6), 2),  # Приют для животных                → nature+helping_motiv+social
        ((B.directions, M, 7), 1),  # Помирить поссорившихся            → social+social_think
        ((B.directions, M, 8), 2),  # Помогаю людям и забочусь          → social+helping_motiv
        # goal
        ((B.goal_clarification, M, 1), 0),
        ((B.goal_clarification, M, 2), 0),
        ((B.goal_clarification, M, 3), 0),
    ],

    # ── 8. Junior — Explorer (wide interests) ───────────────────────────────
    "Junior — Explorer (wide interests)": [
        # interests
        ((B.interests, J, 1), 3),   # Разбираться как работают игрушки  → investigative
        ((B.interests, J, 2), 0),   # Пазлы и головоломки               → investigative+logical
        ((B.interests, J, 3), 0),   # Помогать и делиться               → social+helping_motiv
        ((B.interests, J, 4), 1),   # Космос, техника                   → investigative+tech
        ((B.interests, J, 5), 3),   # Придумать и нарисовать свой мир   → artistic+creative_think
        ((B.interests, J, 6), 0),   # Собрать робота                    → technology+investigative
        ((B.interests, J, 7), 0),   # Почему идёт снег                  → investigative+science
        ((B.interests, J, 8), 3),   # Придумать новый способ расставить → creative_think+enterprising
        ((B.interests, J, 9), 3),   # Изучаю насекомых и растения       → nature+investigative
        ((B.interests, J, 10), 0),  # Провести опыт                     → science+investigative
        ((B.interests, J, 11), 1),  # Слова и истории                   → verbal+artistic
        ((B.interests, J, 12), 0),  # Компьютерная про роботов          → technology+investigative
        # thinking
        ((B.thinking, J, 1), 0),    # Собирать пазлы                    → spatial+logical
        ((B.thinking, J, 2), 1),    # Придумать как играть по-другому   → creative_think
        ((B.thinking, J, 3), 2),    # Сочинить сказку                   → creative_think+verbal
        ((B.thinking, J, 4), 2),    # Стихи и истории                   → verbal
        ((B.thinking, J, 5), 1),    # Начну с красивой части пазла      → creative_think
        ((B.thinking, J, 6), 3),    # Придумаю неожиданный ход          → creative_think
        ((B.thinking, J, 7), 2),    # Покажу как играть на примере      → practical
        ((B.thinking, J, 8), 1),    # Разложу шоколадки руками          → practical
        ((B.thinking, J, 9), 3),    # Придумаю историю кто оставил лужу → creative_think+verbal
        ((B.thinking, J, 10), 0),   # Представлю карту в голове         → spatial
        ((B.thinking, J, 11), 2),   # Придумаю считалку                 → creative_think+verbal
        ((B.thinking, J, 12), 0),   # Коробка → домик для игрушек       → creative_think
        # personality
        ((B.personality, J, 1), 4),   # Нравится пробовать новое          → openness:5
        ((B.personality, J, 2), 3),   # Убираю игрушки, заканчиваю        → conscientiousness:4
        ((B.personality, J, 3), 3),   # Весело с другими детьми           → extraversion+agreeableness:4
        ((B.personality, J, 4), 4),   # Не расстраиваюсь если не вышло    → emotional_stability:5
        ((B.personality, J, 5), 0),   # Конечно попробую новое            → openness:2
        ((B.personality, J, 6), 0),   # Сначала закончу открытку          → conscientiousness:2
        ((B.personality, J, 7), 0),   # Сам подхожу к незнакомым ребятам  → extraversion:2
        ((B.personality, J, 8), 1),   # Найдём игру для обоих             → agreeableness+teamwork
        ((B.personality, J, 9), 0),   # Начну строить заново              → emotional_stability+conscientiousness
        ((B.personality, J, 10), 0),  # Договориться кто что рисует       → teamwork+agreeableness
        ((B.personality, J, 11), 0),  # С удовольствием буду ведущим      → leadership+extraversion
        ((B.personality, J, 12), 1),  # Сначала сам, потом спрошу         → independence+conscientiousness
        # motivation
        ((B.motivation, J, 1), 2),  # Придумал что-то сам               → creative_think
        ((B.motivation, J, 2), 1),  # С друзьями вместе                 → teamwork
        ((B.motivation, J, 3), 0),  # Сложное и интересное              → challenge+interest
        ((B.motivation, J, 4), 0),  # Помогать и делиться               → helping_motiv
        ((B.motivation, J, 5), 0),  # Когда нравится и интересно        → interest:2
        ((B.motivation, J, 6), 0),  # Справился со сложным              → challenge:2
        ((B.motivation, J, 7), 0),  # Делать по-своему                  → freedom:2
        ((B.motivation, J, 8), 1),  # Научился чему-то новому           → interest:2
        ((B.motivation, J, 9), 3),  # Интересно именно мне              → interest:2
        ((B.motivation, J, 10), 0), # Сложное — надо думать             → challenge:2
        ((B.motivation, J, 11), 0), # Нравится придумывать              → creative_think+interest
        ((B.motivation, J, 12), 0), # Вместе веселее                    → teamwork:2
        # goal
        ((B.goal_clarification, J, 1), 0),
        ((B.goal_clarification, J, 2), 0),
        ((B.goal_clarification, J, 3), 0),
    ],

    # ── 9. Junior — Technology / Science ────────────────────────────────────
    # Child who loves how things work, puzzles, robots, experiments, numbers.
    # Expected top directions: IT/Science/AI (category signals: investigative,
    # logical, mathematical, technology, systematic).
    "Junior — Technology / Science": [
        # interests — tech/investigative/science options
        ((B.interests, J, 1), 3),   # Разбираться как работают игрушки  → investigative:2
        ((B.interests, J, 2), 0),   # Пазлы и головоломки               → investigative:2, logical:1
        ((B.interests, J, 3), 2),   # Мастерить вместе                  → realistic:2
        ((B.interests, J, 4), 1),   # Про космос и технику              → investigative:1, technology:1
        ((B.interests, J, 5), 1),   # Развивающая игра                  → investigative:1, logical:1
        ((B.interests, J, 6), 0),   # Собрать робота                    → technology:2, investigative:1
        ((B.interests, J, 7), 0),   # Почему идёт снег                  → investigative:2, science:1
        ((B.interests, J, 8), 0),   # Расставить вещи точно по местам   → conventional:2
        ((B.interests, J, 9), 3),   # Изучаю насекомых и растения       → nature:2, investigative:1
        ((B.interests, J, 10), 0),  # Провести опыт                     → science:2, investigative:1
        ((B.interests, J, 11), 0),  # Игра где считать очки             → numbers:2, conventional:1
        ((B.interests, J, 12), 0),  # Компьютерная про роботов          → technology:2, investigative:1
        # thinking — logical/mathematical/systematic options
        ((B.thinking, J, 1), 0),    # Собирать пазлы                    → spatial:2, logical:1
        ((B.thinking, J, 2), 0),    # Чиню сам                          → practical:2
        ((B.thinking, J, 3), 0),    # Найти отличия                     → logical:2
        ((B.thinking, J, 4), 0),    # Цифры и числа                     → mathematical:2
        ((B.thinking, J, 5), 0),    # Угловые детали сначала            → systematic:2, logical:1
        ((B.thinking, J, 6), 1),    # Слежу за ходами — логический анализ → logical:2, social_think:1
        ((B.thinking, J, 7), 0),    # Расскажу по шагам                 → verbal:2, systematic:1
        ((B.thinking, J, 8), 0),    # Посчитаю в голове                 → mathematical:2
        ((B.thinking, J, 9), 0),    # Прослежу мокрые следы             → logical:2
        ((B.thinking, J, 10), 0),   # Карта в голове с поворотами       → spatial:2
        ((B.thinking, J, 11), 0),   # По шагам 1–5 потом 6–10          → systematic:2, strategic:1
        ((B.thinking, J, 12), 3),   # Посчитаю сколько кубиков влезет   → mathematical:1
        # personality — independent, conscientious
        ((B.personality, J, 1), 3),   # Нравится пробовать новое          → openness:4
        ((B.personality, J, 2), 4),   # Убираю игрушки, заканчиваю        → conscientiousness:5
        ((B.personality, J, 3), 1),   # Умеренно общительный              → extraversion+agreeableness:2
        ((B.personality, J, 4), 3),   # Спокоен к ошибкам                 → emotional_stability:4
        ((B.personality, J, 5), 0),   # Конечно попробую новое            → openness:2
        ((B.personality, J, 6), 0),   # Сначала закончу открытку          → conscientiousness:2
        ((B.personality, J, 7), 3),   # Играю сам по себе                 → independence:1
        ((B.personality, J, 8), 3),   # В свою игру — присоединяйся       → independence:1
        ((B.personality, J, 9), 0),   # Начну заново — построю лучше      → emotional_stability:2, conscientiousness:1
        ((B.personality, J, 10), 1),  # Рисовать свою часть хорошо        → conscientiousness:1, independence:1
        ((B.personality, J, 11), 1),  # Возьму ведение если надо          → leadership:1
        ((B.personality, J, 12), 0),  # Один — сам хочу разобраться       → independence:2
        # motivation — challenge/interest (mostly excluded); minimal scored output
        ((B.motivation, J, 1), 0),  # Получилось трудное                → challenge:2 (excluded)
        ((B.motivation, J, 2), 0),  # По своим правилам                 → freedom:2 (excluded)
        ((B.motivation, J, 3), 0),  # Сложное и интересное              → challenge+interest (excluded)
        ((B.motivation, J, 4), 0),  # Помогать и делиться               → helping_motiv:2
        ((B.motivation, J, 5), 0),  # Когда интересно                   → interest:2 (excluded)
        ((B.motivation, J, 6), 0),  # Очень сложное — справился         → challenge:2 (excluded)
        ((B.motivation, J, 7), 1),  # Задание трудное и надо думать     → challenge:2 (excluded)
        ((B.motivation, J, 8), 3),  # Сделал сложное сам                → challenge+freedom (excluded)
        ((B.motivation, J, 9), 1),  # Сам знал что сделал хорошо       → challenge+interest (excluded)
        ((B.motivation, J, 10), 0), # Сложное где надо думать           → challenge:2 (excluded)
        ((B.motivation, J, 11), 0), # Нравится придумывать              → creative_think:2
        ((B.motivation, J, 12), 1), # Одному — сам решаю как делать     → freedom:2 (excluded)
        # goal
        ((B.goal_clarification, J, 1), 2),  # Знаю сферу
        ((B.goal_clarification, J, 2), 1),  # Выбрать направление
        ((B.goal_clarification, J, 3), 1),  # Иногда думаю
    ],

    # ── 10. Junior — Creative / Artistic ─────────────────────────────────────
    # Child who loves drawing, stories, making things, role play, and art.
    # Expected top directions: Design/Art, Media/Journalism (signals: artistic,
    # creative_think, verbal).
    "Junior — Creative / Artistic": [
        # interests — artistic/creative options
        ((B.interests, J, 1), 1),   # Рисовать и раскрашивать           → artistic:2
        ((B.interests, J, 2), 1),   # Придумывать сказки, ролевые игры  → artistic:2, creative_think:1
        ((B.interests, J, 3), 3),   # Рассказывать истории              → verbal:1, artistic:1
        ((B.interests, J, 4), 2),   # Сказки и мультики про приключения → artistic:1, creative_think:1
        ((B.interests, J, 5), 3),   # Придумать и нарисовать свой мир   → artistic:2, creative_think:1
        ((B.interests, J, 6), 1),   # Нарисовать комикс, своего персонажа → artistic:2, creative_think:1
        ((B.interests, J, 7), 1),   # Как придумывают мультфильмы       → artistic:2, creative_think:1
        ((B.interests, J, 8), 1),   # Нарисовать красивые таблички      → artistic:2, conventional:1
        ((B.interests, J, 9), 0),   # Предлагаю игру и объясняю правила → enterprising:2, leadership:1
        ((B.interests, J, 10), 1),  # Красивая поделка в подарок        → artistic:2
        ((B.interests, J, 11), 1),  # Придумывать слова и истории       → verbal:2, artistic:1
        ((B.interests, J, 12), 1),  # Набор для рисования и творчества  → artistic:2
        # thinking — creative_think/verbal options
        ((B.thinking, J, 1), 1),    # Придумывать истории               → creative_think:2
        ((B.thinking, J, 2), 1),    # Придумаю как играть по-другому    → creative_think:2
        ((B.thinking, J, 3), 2),    # Сочинить сказку                   → creative_think:2, verbal:1
        ((B.thinking, J, 4), 2),    # Стихи и истории                   → verbal:2
        ((B.thinking, J, 5), 1),    # Начну с красивой части пазла      → creative_think:1
        ((B.thinking, J, 6), 3),    # Придумаю неожиданный ход          → creative_think:2
        ((B.thinking, J, 7), 0),    # Расскажу по шагам словами         → verbal:2, systematic:1
        ((B.thinking, J, 8), 2),    # Нарисую кружочки и распределю     → spatial:1, mathematical:1
        ((B.thinking, J, 9), 3),    # Придумаю историю кто оставил лужу → creative_think:2, verbal:1
        ((B.thinking, J, 10), 0),   # Карта в голове с поворотами       → spatial:2
        ((B.thinking, J, 11), 2),   # Придумаю весёлую считалку         → creative_think:2, verbal:1
        ((B.thinking, J, 12), 0),   # Домик для игрушек из коробки      → creative_think:2
        # personality — openness high, extraversion moderate
        ((B.personality, J, 1), 4),   # Нравится пробовать новое          → openness:5
        ((B.personality, J, 2), 2),   # Умеренно доводит до конца         → conscientiousness:3
        ((B.personality, J, 3), 3),   # Весело с другими детьми           → extraversion+agreeableness:4
        ((B.personality, J, 4), 3),   # Спокоен к ошибкам                 → emotional_stability:4
        ((B.personality, J, 5), 0),   # Конечно попробую новое            → openness:2
        ((B.personality, J, 6), 1),   # Немного погуляю, вернусь доделать → conscientiousness:1
        ((B.personality, J, 7), 0),   # Сам подхожу к незнакомым          → extraversion:2
        ((B.personality, J, 8), 1),   # Найдём игру для обоих             → agreeableness:1, teamwork:1
        ((B.personality, J, 9), 1),   # Немного расстроюсь, попробую снова → emotional_stability:1
        ((B.personality, J, 10), 2),  # Помогать тем у кого не получается → agreeableness:2
        ((B.personality, J, 11), 0),  # С удовольствием буду ведущим      → leadership:2, extraversion:1
        ((B.personality, J, 12), 2),  # Вместе с кем-то — так интереснее  → teamwork:2, extraversion:1
        # motivation — creative_think heavy
        ((B.motivation, J, 1), 2),  # Придумал что-то сам               → creative_think:2
        ((B.motivation, J, 2), 1),  # С друзьями вместе                 → teamwork:2
        ((B.motivation, J, 3), 0),  # Сложное и интересное              → challenge+interest (excluded)
        ((B.motivation, J, 4), 1),  # Дарить то что сам сделал          → creative_think:1, helping_motiv:1
        ((B.motivation, J, 5), 0),  # Когда интересно                   → interest:2 (excluded)
        ((B.motivation, J, 6), 1),  # Придумал полностью сам            → freedom:1, creative_think:1
        ((B.motivation, J, 7), 0),  # Когда можно делать по-своему      → freedom:2 (excluded)
        ((B.motivation, J, 8), 1),  # Научился чему-то новому           → interest:2 (excluded)
        ((B.motivation, J, 9), 2),  # Другим от этого стало лучше       → helping_motiv:2
        ((B.motivation, J, 10), 2), # Придумывать и фантазировать       → freedom:1, creative_think:1
        ((B.motivation, J, 11), 0), # Нравится придумывать              → creative_think:2
        ((B.motivation, J, 12), 0), # Вместе веселее                    → teamwork:2
        # goal
        ((B.goal_clarification, J, 1), 1),  # Есть пара идей
        ((B.goal_clarification, J, 2), 0),  # Понять свои сильные стороны
        ((B.goal_clarification, J, 3), 0),  # Ещё рано, не думал
    ],

    # ── 11. Junior — Social / Helper ─────────────────────────────────────────
    # Child who loves playing with friends, helping others, organizing games.
    # Expected top directions: Psychology/Pedagogy, Law/Society (signals:
    # social, helping_motiv, verbal, social_think).
    "Junior — Social / Helper": [
        # interests — social/helping options
        ((B.interests, J, 1), 2),   # Играть с друзьями                 → social:2
        ((B.interests, J, 2), 3),   # Игры где надо быть главным        → enterprising:1, leadership:1
        ((B.interests, J, 3), 0),   # Помогать друзьям и делиться       → social:2, helping_motiv:1
        ((B.interests, J, 4), 3),   # Про супергероев что помогают      → social:1, helping_motiv:1
        ((B.interests, J, 5), 2),   # Поиграть с друзьями               → social:2
        ((B.interests, J, 6), 2),   # Помочь малышам научить правилам   → social:2, helping_motiv:1
        ((B.interests, J, 7), 2),   # Как подружиться с новым ребёнком  → social:2
        ((B.interests, J, 8), 2),   # Позвать друзей убирать вместе     → social:2
        ((B.interests, J, 9), 1),   # Слежу чтобы всем было хорошо     → social:2, helping_motiv:1
        ((B.interests, J, 10), 2),  # Помочь другу разобраться в игре   → social:2, helping_motiv:1
        ((B.interests, J, 11), 3),  # Игра где договариваться и меняться → enterprising:1, social:1
        ((B.interests, J, 12), 3),  # Игра где копить монеты            → numbers:2, enterprising:1
        # thinking — social_think/verbal options
        ((B.thinking, J, 1), 3),    # Играть с друзьями в команде       → social_think:2
        ((B.thinking, J, 2), 2),    # Зовёт кого-то на помощь          → social_think:1
        ((B.thinking, J, 3), 2),    # Сочинить сказку                   → creative_think:2, verbal:1
        ((B.thinking, J, 4), 2),    # Стихи и истории                   → verbal:2
        ((B.thinking, J, 5), 3),    # Попрошу кого-нибудь помочь        → social_think:1
        ((B.thinking, J, 6), 1),    # Слежу за ходами друга            → logical:2, social_think:1
        ((B.thinking, J, 7), 0),    # Расскажу по шагам словами         → verbal:2, systematic:1
        ((B.thinking, J, 8), 3),    # Попрошу кого-то помочь подсчитать → social_think:1
        ((B.thinking, J, 9), 1),    # Сразу скажу маме или папе         → social_think:1
        ((B.thinking, J, 10), 3),   # Запомню объяснение словами        → verbal:1, social_think:1
        ((B.thinking, J, 11), 3),   # Буду задавать вопросы             → logical:1, social_think:1
        ((B.thinking, J, 12), 2),   # Поставлю и попробую (ступенька)   → practical:2
        # personality — agreeableness/extraversion/teamwork high
        ((B.personality, J, 1), 3),   # Нравится пробовать новое          → openness:4
        ((B.personality, J, 2), 2),   # Умеренно доводит до конца         → conscientiousness:3
        ((B.personality, J, 3), 4),   # Очень весело с другими детьми     → extraversion+agreeableness:5
        ((B.personality, J, 4), 4),   # Не расстраиваюсь                  → emotional_stability:5
        ((B.personality, J, 5), 3),   # Попробую если и друг попробует    → agreeableness:1
        ((B.personality, J, 6), 2),   # Пойду гулять, открытку сделаю потом → {}
        ((B.personality, J, 7), 0),   # Сам подхожу к незнакомым          → extraversion:2
        ((B.personality, J, 8), 0),   # Давай сначала в твою игру         → agreeableness:2
        ((B.personality, J, 9), 2),   # Попрошу кого-нибудь помочь        → agreeableness:1
        ((B.personality, J, 10), 2),  # Помогать тем у кого не получается → agreeableness:2
        ((B.personality, J, 11), 2),  # Лучше буду участником             → extraversion:1, agreeableness:1
        ((B.personality, J, 12), 2),  # Вместе с кем-то — так интереснее  → teamwork:2, extraversion:1
        # motivation — helping_motiv heavy
        ((B.motivation, J, 1), 1),  # Когда помог кому-то               → helping_motiv:2
        ((B.motivation, J, 2), 1),  # С друзьями вместе                 → teamwork:2
        ((B.motivation, J, 3), 1),  # Лёгкое и весёлое                  → interest+stability (excluded)
        ((B.motivation, J, 4), 0),  # Помогать и делиться               → helping_motiv:2
        ((B.motivation, J, 5), 1),  # Знаю что порадую кого-то          → helping_motiv:1
        ((B.motivation, J, 6), 2),  # Помог другу или близкому          → helping_motiv:2
        ((B.motivation, J, 7), 2),  # Делаем что-то вместе с другими    → teamwork:2
        ((B.motivation, J, 8), 0),  # Когда помог кому-то               → helping_motiv:2
        ((B.motivation, J, 9), 2),  # Чтобы другим стало лучше          → helping_motiv:2
        ((B.motivation, J, 10), 3), # Где делаем всё вместе             → teamwork:2
        ((B.motivation, J, 11), 2), # Хочу подарить или помочь          → helping_motiv:2
        ((B.motivation, J, 12), 0), # Вместе — так веселее              → teamwork:2
        # goal
        ((B.goal_clarification, J, 1), 0),  # Совсем не знаю
        ((B.goal_clarification, J, 2), 0),  # Понять свои сильные стороны
        ((B.goal_clarification, J, 3), 0),  # Ещё рано, не думал
    ],
}


# ---------------------------------------------------------------------------
# Calibration findings (post-junior expansion, 2025-07)
# ---------------------------------------------------------------------------
#
# After tripling junior questions (interests/thinking/personality/motivation
# each went from ~4 to 12 questions), all 3 focused junior profiles and the
# Explorer profile were run.  Key observations:
#
# 1. NO DEGENERATION — scores do not collapse to all-99% or all-zero.
#    The formula cap (min(ratio, 1.2)) and averaging of required categories
#    prevent saturation even when personality traits score very high.
#
# 2. MEANINGFUL DIFFERENTIATION — top-5 shifts correctly across profiles:
#    Junior Tech     → IT(93%) / AI(78%) / Science(77%) / Data Science(57%)
#    Junior Creative → Design(89%) / Media(70%) / Marketing(51%)
#    Junior Social   → Psychology(95%) / Law(68%) / Medicine(55%)
#    Junior Explorer → Design(59%) / Science(51%) / Marketing(50%)  ← intentionally compressed
#
# 3. PERSONALITY CROWDING is NOT a problem.  Expanded personality questions
#    add raw weight to conscientiousness/agreeableness/extraversion, but:
#    (a) domain categories from 12 interest questions still dominate raw totals;
#    (b) personality traits do not appear in direction required_scores, so they
#        do not inflate match_scores;
#    (c) the normalization denominator (max raw category) is driven by domain
#        signals (investigative, social, creative_think), not personality.
#
# 4. NO THRESHOLD ADJUSTMENTS NEEDED.  All required_scores in seed_directions.py
#    remain valid.  Junior profiles can reach high match_scores (93%, 95%) for
#    well-matching directions because the formula compensates a weaker required
#    category via a strong companion (e.g., investigative=100 offsets low science
#    for "Наука и исследования"; similarly logical=83 offsets technology=42 for IT).
#
# 5. KNOWN BEHAVIOR: high conscientiousness in junior profiles can push
#    "Управление проектами" into #4-5 slot (required: strategic:55,
#    conscientiousness:45).  This is acceptable — the gap vs. the correct
#    direction is always ≥30 percentage points, so the recommendation stays clear.
#
# ---------------------------------------------------------------------------
# Calibration findings (post-middle/senior expansion, 2026-07)
# ---------------------------------------------------------------------------
#
# Middle and senior blocks were brought to the same per-block target as junior
# (interests/thinking/personality/motivation → 12 each; academic/directions → 8;
# senior university → 10 preference questions).  Personality blocks are now a
# mix of Likert items (incl. one reversed item for senior) and situational
# choice questions.  Findings:
#
# 1. NO DEGENERATION — max-based normalization plus the min(ratio, 1.2) cap
#    keeps scores stable at the larger question volume.  Junior profiles are
#    unchanged vs. the previous run (no regression).
#
# 2. MEANINGFUL DIFFERENTIATION — top-1 is correct with a clear margin:
#    Senior Tech     → IT(99%) / AI(87%) / Data Science(62%)
#    Senior Creative → Design(90%) / Media(80%) / Marketing(50%)
#    Senior Social   → Psychology(99%) / Law(90%) / Medicine(70%)
#    Senior Business → Business(71%) / Marketing(48%) / Finance(35%)
#    Middle Tech     → IT(99%) / AI(90%) / Data Science(56%)
#    Middle Creative → Design(90%) / Media(72%) / Marketing(55%)
#    Middle Social   → Psychology(99%) / Law(90%) / Media(79%)
#
# 3. LIKERT EXPANSION IS SAFE — new Likert items (leadership/independence for
#    middle, reversed emotional_stability + extraversion for senior) add at most
#    5 raw points per trait; domain categories from 12 interests + 8 academic +
#    8 directions questions still dominate the normalization denominator, and
#    personality traits appear in required_scores only for Business (leadership)
#    and Project Management (conscientiousness).
#
# 4. KNOWN BEHAVIOR: Senior Business tops out at ~71% because its required
#    leadership:45 is normalized against a dominant enterprising signal
#    (leadership ≈ 26% of max).  Top-1 is still Business with a ≥20 pp gap —
#    acceptable; no threshold changes made.
#
# 5. Law/госуправление reaches 90% for strongly verbal social profiles
#    (verbal 75-92%, social 83-100%): both of its requirements are genuinely
#    satisfied.  Psychology stays ahead at 99%, so the ranking is stable.
#
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
