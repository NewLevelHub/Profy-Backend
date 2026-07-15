"""
Seed script: transfer the manually-reviewed AKN-009 draft content into the DB
via the AKN-002 (Direction tree columns) / AKN-003 (AkinatorQuestion) models.

Source of truth (transcribed as-is, NOT regenerated through the AKN-006/007/008
LLM draft generators):
  - akinatorLogic/profi_full_catalog.md  -> 16 sections (branches) + 67 professions (leaves)
  - akinatorLogic/profi_questions_mvp.md + profi_questions_full_addon.md -> q01-q41

Idempotent: Direction rows are upserted by `slug`. AkinatorQuestion rows are
upserted by `order` — this script owns orders 0-40 (the q01..q41 sequence);
don't reuse that range for other seeded/generated question batches.

Run inside Docker:
    docker-compose exec api python scripts/seed_akinator_content.py
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.akinator_question import AkinatorQuestion
from app.models.direction import Direction

# ---------------------------------------------------------------------------
# 1. Taxonomy — 16 sections (branches) + 67 professions (leaves)
# ---------------------------------------------------------------------------

SECTIONS: list[dict] = [
    {"slug": "akinator-medicine", "name": "Медицина и здоровье"},
    {"slug": "akinator-psychology-help", "name": "Помощь и психология"},
    {"slug": "akinator-animals-nature", "name": "Животные и природа"},
    {"slug": "akinator-it-data", "name": "IT и данные"},
    {"slug": "akinator-engineering-tech", "name": "Инженерия и техника"},
    {"slug": "akinator-construction-manual", "name": "Строительство и руками"},
    {"slug": "akinator-creative-design", "name": "Творчество и дизайн"},
    {"slug": "akinator-stage-media", "name": "Сцена и медиа"},
    {"slug": "akinator-words-communication", "name": "Слово и коммуникация"},
    {"slug": "akinator-education", "name": "Образование"},
    {"slug": "akinator-sports-body", "name": "Спорт и тело"},
    {"slug": "akinator-food-hospitality", "name": "Еда и гостеприимство"},
    {"slug": "akinator-business-sales", "name": "Бизнес и продажи"},
    {"slug": "akinator-beauty-services", "name": "Красота и услуги"},
    {"slug": "akinator-safety-rescue", "name": "Безопасность и спасение"},
    {"slug": "akinator-logistics-service", "name": "Логистика и сервис"},
]

PROFESSIONS: list[dict] = [
    # Медицина и здоровье
    {"slug": "surgeon", "name": "Хирург", "section": "akinator-medicine", "profile": {"People": 1, "Living": 2, "Phys": 2, "Care": 2, "Dev": -1, "Motor": 2, "Exp": 2, "Focus": 2, "Risk": 1, "Struct": 2, "Pace": 1, "Acad": 2, "PhysSt": 1}},
    {"slug": "physician", "name": "Терапевт", "section": "akinator-medicine", "profile": {"People": 2, "Living": 2, "Care": 2, "Exp": 2, "Emp": 1, "Focus": 1, "Struct": 1, "Predict": 1, "Acad": 2}},
    {"slug": "psychiatrist", "name": "Психиатр", "section": "akinator-medicine", "profile": {"People": 2, "Living": 1, "Care": 2, "Exp": 2, "Emp": 2, "Focus": 2, "Struct": 1, "Acad": 2, "Data": -1}},
    {"slug": "nurse", "name": "Медсестра", "section": "akinator-medicine", "profile": {"People": 2, "Living": 2, "Care": 2, "Emp": 1, "Motor": 1, "Focus": -1, "Struct": 1, "Pace": 1, "PhysSt": 1}},
    {"slug": "paramedic", "name": "Парамедик", "section": "akinator-medicine", "profile": {"People": 2, "Living": 2, "Phys": 1, "Care": 2, "Motor": 1, "Focus": -2, "Risk": 1, "Struct": 1, "Pace": 2, "Predict": 2, "PhysSt": 1}},
    {"slug": "dentist", "name": "Стоматолог", "section": "akinator-medicine", "profile": {"People": 1, "Living": 2, "Phys": 1, "Care": 2, "Motor": 2, "Exp": 2, "Focus": 2, "Struct": 1, "Acad": 2}},
    {"slug": "pharmacist", "name": "Фармацевт", "section": "akinator-medicine", "profile": {"People": 1, "Living": 1, "Data": 1, "Care": 1, "Exp": 2, "Focus": 1, "Struct": 2, "Predict": -1, "Acad": 1, "Math": 1}},

    # Помощь и психология
    {"slug": "psychologist", "name": "Психолог", "section": "akinator-psychology-help", "profile": {"People": 2, "Care": 2, "Emp": 2, "Exp": 2, "Focus": 2, "Motiv": -1, "Auto": 1, "Acad": 2, "Data": -1, "Ideas": 1}},
    {"slug": "coach", "name": "Коуч", "section": "akinator-psychology-help", "profile": {"People": 2, "Dev": 2, "Emp": 2, "Vis": 1, "Motiv": 1, "Risk": 1, "Auto": 1, "Predict": 1}},
    {"slug": "social-worker", "name": "Социальный работник", "section": "akinator-psychology-help", "profile": {"People": 2, "Care": 2, "Emp": 2, "Struct": 1, "Motiv": -1, "Pace": 1, "Predict": 1, "Acad": 1}},
    {"slug": "speech-therapist", "name": "Логопед", "section": "akinator-psychology-help", "profile": {"People": 2, "Care": 1, "Dev": 2, "Emp": 1, "Exp": 2, "Focus": 1, "Struct": 1, "Acad": 1}},

    # Животные и природа
    {"slug": "veterinarian", "name": "Ветеринар", "section": "akinator-animals-nature", "profile": {"People": 1, "Living": 2, "Phys": 1, "Care": 2, "Motor": 1, "Exp": 2, "Focus": 1, "Acad": 2, "PhysSt": 1, "Ideas": -1}},
    {"slug": "zoologist", "name": "Зоолог", "section": "akinator-animals-nature", "profile": {"Living": 2, "Data": 1, "Obj": -2, "Exp": 2, "Focus": 2, "Auto": 1, "Predict": 1, "Acad": 2, "People": -1, "PhysSt": 1}},
    {"slug": "agronomist", "name": "Агроном", "section": "akinator-animals-nature", "profile": {"Living": 2, "Phys": 1, "Data": 1, "Exp": 1, "Struct": 1, "Predict": -1, "PhysSt": 1}},
    {"slug": "cynologist", "name": "Кинолог", "section": "akinator-animals-nature", "profile": {"People": 1, "Living": 2, "Phys": 1, "Dev": 1, "Motor": 1, "Struct": 1, "PhysSt": 1, "Acad": -1}},
    {"slug": "ecologist", "name": "Эколог", "section": "akinator-animals-nature", "profile": {"Living": 2, "Data": 1, "Ideas": 1, "Obj": -2, "Exp": 1, "Auto": 1, "Predict": 1, "Acad": 1}},

    # IT и данные
    {"slug": "programmer", "name": "Программист", "section": "akinator-it-data", "profile": {"People": -1, "Living": -2, "Data": 2, "Ideas": 1, "Inv": 1, "Obj": 2, "Care": -2, "Dev": -2, "Exp": 2, "Focus": 2, "Motiv": 1, "Auto": 1, "Struct": 1, "Acad": 1, "PhysSt": -2, "Math": 2}},
    {"slug": "data-analyst", "name": "Аналитик данных", "section": "akinator-it-data", "profile": {"People": -1, "Living": -2, "Data": 2, "Obj": -2, "Care": -2, "Dev": -2, "Exp": 1, "Focus": 2, "Auto": 1, "Struct": 1, "Predict": -1, "Acad": 1, "PhysSt": -2, "Math": 2}},
    {"slug": "qa-tester", "name": "QA-тестировщик", "section": "akinator-it-data", "profile": {"Data": 2, "Obj": -1, "Exp": 1, "Focus": 1, "Struct": 2, "Predict": -1, "Motiv": -1, "PhysSt": -2, "Math": 1, "People": -1}},
    {"slug": "ux-designer", "name": "UX-дизайнер", "section": "akinator-it-data", "profile": {"People": 1, "Data": 1, "Ideas": 2, "Inv": 2, "Obj": 1, "Emp": 1, "Exp": 1, "PhysSt": -1}},
    {"slug": "sysadmin", "name": "Сисадмин", "section": "akinator-it-data", "profile": {"Phys": 1, "Data": 2, "Obj": 1, "Exp": 2, "Focus": -1, "Auto": 1, "Struct": 1, "Pace": 1, "Predict": 1, "PhysSt": -1, "Math": 1, "People": -1}},

    # Инженерия и техника
    {"slug": "mechanical-engineer", "name": "Инженер-механик", "section": "akinator-engineering-tech", "profile": {"Phys": 2, "Data": 1, "Ideas": 1, "Inv": 1, "Obj": 2, "Exp": 2, "Focus": 1, "Struct": 1, "Acad": 2, "Math": 2, "People": -1}},
    {"slug": "civil-engineer", "name": "Инженер-строитель", "section": "akinator-engineering-tech", "profile": {"Phys": 2, "Data": 1, "Obj": 2, "Lead": 1, "Exp": 2, "Focus": 1, "Struct": 2, "Risk": -1, "Acad": 2, "Math": 2}},
    {"slug": "electrician", "name": "Электрик", "section": "akinator-engineering-tech", "profile": {"Phys": 2, "Obj": 1, "Motor": 2, "Exp": 1, "Struct": 2, "Risk": 1, "Auto": 1, "PhysSt": 1, "Acad": -1}},
    {"slug": "auto-mechanic", "name": "Автомеханик", "section": "akinator-engineering-tech", "profile": {"Phys": 2, "Obj": 1, "Motor": 2, "Exp": 1, "Focus": 1, "Struct": 1, "PhysSt": 1, "Acad": -1, "People": -1}},
    {"slug": "pilot", "name": "Пилот", "section": "akinator-engineering-tech", "profile": {"Phys": 1, "Data": 1, "Lead": 1, "Exp": 2, "Focus": 2, "Risk": 1, "Struct": 2, "Pace": 1, "Acad": 1, "Math": 1}},

    # Строительство и руками
    {"slug": "carpenter", "name": "Столяр", "section": "akinator-construction-manual", "profile": {"Phys": 2, "Ideas": 1, "Inv": 1, "Motor": 2, "Exp": 1, "Focus": 1, "Auto": 1, "PhysSt": 2, "Acad": -2, "People": -1}},
    {"slug": "plumber", "name": "Сантехник", "section": "akinator-construction-manual", "profile": {"Phys": 2, "Obj": 1, "Motor": 2, "Exp": 1, "Auto": 1, "Predict": 1, "PhysSt": 2, "Acad": -2}},
    {"slug": "welder", "name": "Сварщик", "section": "akinator-construction-manual", "profile": {"Phys": 2, "Motor": 2, "Focus": 1, "Struct": 1, "Risk": 1, "PhysSt": 2, "Acad": -2, "Predict": -1, "People": -1}},
    {"slug": "construction-worker", "name": "Строитель", "section": "akinator-construction-manual", "profile": {"Phys": 2, "Motor": 1, "Lead": -1, "Struct": 1, "PhysSt": 2, "Pace": 1, "Acad": -2, "Auto": -1}},

    # Творчество и дизайн
    {"slug": "graphic-designer", "name": "Графический дизайнер", "section": "akinator-creative-design", "profile": {"Ideas": 2, "Inv": 2, "Obj": 1, "Exp": 1, "Auto": 1, "Struct": -1, "Math": -1, "PhysSt": -1}},
    {"slug": "illustrator", "name": "Иллюстратор", "section": "akinator-creative-design", "profile": {"Ideas": 2, "Inv": 2, "Motor": 1, "Auto": 2, "Struct": -2, "Vis": -1, "Math": -1, "PhysSt": -1, "People": -1, "Exp": 1}},
    {"slug": "architect", "name": "Архитектор", "section": "akinator-creative-design", "profile": {"People": 1, "Phys": 1, "Data": 1, "Ideas": 2, "Inv": 2, "Obj": 1, "Lead": 1, "Exp": 2, "Focus": 2, "Struct": 2, "Auto": 1, "Acad": 2, "Math": 1, "PhysSt": -1}},
    {"slug": "photographer", "name": "Фотограф", "section": "akinator-creative-design", "profile": {"People": 1, "Ideas": 2, "Inv": 1, "Motor": 1, "Vis": 1, "Auto": 2, "Struct": -1, "Risk": 1, "Predict": 1}},
    {"slug": "fashion-designer", "name": "Модельер", "section": "akinator-creative-design", "profile": {"Ideas": 2, "Inv": 2, "Phys": 1, "Motor": 1, "Vis": 1, "Exp": 1, "Auto": 1, "Struct": -1, "Risk": 1}},

    # Сцена и медиа
    {"slug": "actor", "name": "Актёр", "section": "akinator-stage-media", "profile": {"People": 1, "Ideas": 2, "Vis": 2, "Emp": 1, "Motor": 1, "Risk": 1, "Struct": -1, "Auto": -1, "Predict": 1, "PhysSt": 1, "Math": -1, "Data": -1}},
    {"slug": "musician", "name": "Музыкант", "section": "akinator-stage-media", "profile": {"Ideas": 2, "Vis": 1, "Motor": 2, "Exp": 2, "Focus": 2, "Auto": 1, "Risk": 1, "Struct": -1}},
    {"slug": "film-director", "name": "Режиссёр", "section": "akinator-stage-media", "profile": {"People": 1, "Ideas": 2, "Inv": 2, "Lead": 2, "Exp": 1, "Focus": 1, "Risk": 1, "Auto": 1, "Struct": -1}},
    {"slug": "blogger-host", "name": "Блогер/ведущий", "section": "akinator-stage-media", "profile": {"People": 2, "Ideas": 1, "Vis": 2, "Emp": 1, "Inv": 1, "Risk": 2, "Auto": 1, "Predict": 2, "Struct": -2, "Motiv": 1}},

    # Слово и коммуникация
    {"slug": "journalist", "name": "Журналист", "section": "akinator-words-communication", "profile": {"People": 1, "Ideas": 1, "Obj": -2, "Vis": 1, "Exp": 1, "Emp": 1, "Risk": 1, "Pace": 2, "Predict": 2, "Acad": 1, "Struct": -1}},
    {"slug": "copywriter", "name": "Копирайтер", "section": "akinator-words-communication", "profile": {"Ideas": 2, "Obj": -1, "Inv": 1, "Exp": 1, "Focus": 1, "Auto": 1, "People": -1}},
    {"slug": "translator", "name": "Переводчик", "section": "akinator-words-communication", "profile": {"Ideas": 1, "Obj": -1, "Exp": 2, "Focus": 2, "Auto": 2, "Struct": 1, "Predict": -1, "Acad": 1, "People": -1}},
    {"slug": "lawyer", "name": "Юрист", "section": "akinator-words-communication", "profile": {"People": 1, "Data": 1, "Obj": -1, "Lead": 1, "Vis": 1, "Exp": 2, "Focus": 2, "Struct": 2, "Acad": 2}},

    # Образование
    {"slug": "school-teacher", "name": "Учитель", "section": "akinator-education", "profile": {"People": 2, "Dev": 2, "Care": 1, "Lead": 1, "Vis": 1, "Exp": 1, "Emp": 1, "Focus": -1, "Struct": 1, "Acad": 1}},
    {"slug": "tutor", "name": "Репетитор", "section": "akinator-education", "profile": {"People": 1, "Dev": 2, "Exp": 2, "Emp": 1, "Focus": 1, "Auto": 2, "Acad": 1, "Vis": -1}},
    {"slug": "kindergarten-teacher", "name": "Воспитатель", "section": "akinator-education", "profile": {"People": 2, "Care": 2, "Dev": 1, "Emp": 2, "Focus": -1, "Struct": 1, "Pace": 1, "PhysSt": 1, "Acad": -1}},

    # Спорт и тело
    {"slug": "sports-coach", "name": "Спортивный тренер", "section": "akinator-sports-body", "profile": {"People": 1, "Living": 1, "Dev": 2, "Care": 1, "Lead": 1, "Motor": 1, "Emp": 1, "Motiv": 2, "Pace": 1, "PhysSt": 1, "Exp": 1}},
    {"slug": "fitness-instructor", "name": "Фитнес-инструктор", "section": "akinator-sports-body", "profile": {"People": 2, "Living": 1, "Dev": 1, "Vis": 1, "Motor": 1, "Emp": 1, "Pace": 1, "PhysSt": 2, "Predict": 1, "Acad": -1}},
    {"slug": "rehabilitation-therapist", "name": "Реабилитолог", "section": "akinator-sports-body", "profile": {"People": 1, "Living": 2, "Care": 2, "Dev": 1, "Motor": 1, "Exp": 2, "Emp": 1, "Focus": 1, "Struct": 1, "Acad": 1, "PhysSt": 1}},
    {"slug": "athlete", "name": "Спортсмен", "section": "akinator-sports-body", "profile": {"Living": 1, "Vis": 1, "Motor": 2, "Focus": 2, "Motiv": 2, "Risk": 1, "Struct": 1, "PhysSt": 2, "Acad": -2}},

    # Еда и гостеприимство
    {"slug": "chef", "name": "Повар", "section": "akinator-food-hospitality", "profile": {"Phys": 1, "Ideas": 1, "Inv": 1, "Obj": 1, "Motor": 2, "Lead": 1, "Focus": -1, "Struct": 1, "Pace": 2, "PhysSt": 2, "Acad": -1}},
    {"slug": "pastry-chef", "name": "Кондитер", "section": "akinator-food-hospitality", "profile": {"Phys": 1, "Ideas": 2, "Inv": 1, "Motor": 2, "Exp": 1, "Focus": 2, "Struct": 2, "PhysSt": 1, "Acad": -1, "Predict": -1}},
    {"slug": "barista", "name": "Бариста", "section": "akinator-food-hospitality", "profile": {"People": 2, "Phys": 1, "Motor": 1, "Vis": 1, "Emp": 1, "Pace": 2, "Predict": 1, "PhysSt": 1, "Acad": -1}},
    {"slug": "waiter", "name": "Официант", "section": "akinator-food-hospitality", "profile": {"People": 2, "Motor": 1, "Emp": 1, "Focus": -1, "Pace": 2, "Predict": 1, "PhysSt": 1, "Acad": -2}},

    # Бизнес и продажи
    {"slug": "sales-manager", "name": "Менеджер по продажам", "section": "akinator-business-sales", "profile": {"People": 2, "Emp": 2, "Vis": 1, "Motiv": 2, "Risk": 1, "Auto": 1, "Predict": 2, "Pace": 1, "Struct": -1}},
    {"slug": "entrepreneur", "name": "Предприниматель", "section": "akinator-business-sales", "profile": {"People": 1, "Ideas": 1, "Inv": 2, "Lead": 2, "Vis": 1, "Motiv": 2, "Risk": 2, "Auto": 2, "Struct": -2, "Predict": 2}},
    {"slug": "marketer", "name": "Маркетолог", "section": "akinator-business-sales", "profile": {"People": 1, "Data": 1, "Ideas": 1, "Inv": 1, "Obj": -1, "Vis": 1, "Emp": 1, "Motiv": 1, "Predict": 1, "Acad": 1}},
    {"slug": "accountant", "name": "Бухгалтер", "section": "akinator-business-sales", "profile": {"Data": 2, "Obj": -1, "Exp": 2, "Focus": 2, "Struct": 2, "Motiv": -1, "Auto": 1, "Predict": -2, "Pace": -1, "Acad": 1, "Math": 2, "People": -1}},

    # Красота и услуги
    {"slug": "hairdresser", "name": "Парикмахер", "section": "akinator-beauty-services", "profile": {"People": 2, "Phys": 1, "Ideas": 1, "Motor": 2, "Vis": 1, "Emp": 1, "Inv": 1, "Auto": 1, "Pace": 1, "PhysSt": 1, "Acad": -2}},
    {"slug": "makeup-artist", "name": "Визажист", "section": "akinator-beauty-services", "profile": {"People": 1, "Ideas": 2, "Motor": 2, "Vis": 1, "Inv": 2, "Emp": 1, "Auto": 1, "Risk": 1, "Acad": -1}},

    # Безопасность и спасение
    {"slug": "firefighter", "name": "Пожарный", "section": "akinator-safety-rescue", "profile": {"People": 1, "Phys": 1, "Care": 1, "Motor": 1, "Focus": -2, "Risk": 2, "Auto": -1, "Struct": 1, "Pace": 2, "Predict": 1, "PhysSt": 2, "Acad": -1}},
    {"slug": "police-officer", "name": "Полицейский", "section": "akinator-safety-rescue", "profile": {"People": 1, "Phys": 1, "Lead": 1, "Exp": 1, "Focus": -1, "Risk": 1, "Struct": 2, "Pace": 1, "Predict": 1, "PhysSt": 1}},
    {"slug": "rescuer", "name": "Спасатель", "section": "akinator-safety-rescue", "profile": {"People": 1, "Phys": 1, "Living": 1, "Care": 1, "Motor": 1, "Focus": -1, "Risk": 2, "Struct": 1, "Pace": 2, "Predict": 1, "PhysSt": 2, "Acad": -1}},

    # Логистика и сервис
    {"slug": "taxi-driver", "name": "Таксист", "section": "akinator-logistics-service", "profile": {"People": 1, "Phys": 1, "Motor": 1, "Auto": 2, "Focus": -1, "Predict": -1, "Acad": -2, "Exp": -2}},
    {"slug": "courier", "name": "Курьер", "section": "akinator-logistics-service", "profile": {"Phys": 1, "Motor": 1, "Auto": 1, "Pace": 2, "Struct": -1, "PhysSt": 2, "Acad": -2, "Exp": -2}},
    {"slug": "warehouse-worker", "name": "Складской работник", "section": "akinator-logistics-service", "profile": {"Phys": 2, "Motor": 1, "Auto": -2, "Struct": 2, "Pace": 1, "Predict": -2, "PhysSt": 2, "Acad": -2, "People": -1, "Exp": -2}},
    {"slug": "sales-consultant", "name": "Продавец-консультант", "section": "akinator-logistics-service", "profile": {"People": 2, "Emp": 1, "Motiv": 1, "Pace": 1, "Predict": 1, "PhysSt": 1, "Acad": -1, "Exp": -1}},
]

assert len(SECTIONS) == 16, f"expected 16 sections, got {len(SECTIONS)}"
assert len(PROFESSIONS) == 67, f"expected 67 professions, got {len(PROFESSIONS)}"

# ---------------------------------------------------------------------------
# 2. Questions q01-q41, from profi_questions_mvp.md (q01-q24) +
#    profi_questions_full_addon.md (q25-q41). `order` == q-number - 1.
#
# resolves_pair is left null for four "разводит" notes that name a branch or
# a generic bucket rather than a specific profession pair — not silently
# guessed: q28 ("vs инженер", unspecified which), q31 ("дизайн/иллюстрация
# vs сцена", branch-level), q37 ("vs исполнительские роли", generic), q38
# ("vs остальной бизнес", generic). Flagged for product review.
# ---------------------------------------------------------------------------

QUESTIONS: list[dict] = [
    {"order": 0, "kind": "direct", "depth": 0, "age_variant": "both",
     "text": "Что тебе интереснее всего?", "text_junior": None,
     "options": [
         {"text": "быть среди людей, общаться, помогать", "axis_weights": {"People": 2}},
         {"text": "разбираться, как устроены вещи и техника", "axis_weights": {"Phys": 1, "Data": 1}},
         {"text": "возиться с животными, растениями, природой", "axis_weights": {"Living": 2}},
         {"text": "придумывать, рисовать, создавать своё", "axis_weights": {"Ideas": 2}},
     ], "resolves_pair": None},
    {"order": 1, "kind": "direct", "depth": 0, "age_variant": "both",
     "text": "Что приятнее?", "text_junior": None,
     "options": [
         {"text": "делать что-то руками, чтобы вышел результат", "axis_weights": {"Phys": 1, "Motor": 1}},
         {"text": "думать и решать в голове или на бумаге", "axis_weights": {"Data": 1, "Focus": 1}},
         {"text": "и то и другое поровну", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 2, "kind": "direct", "depth": 1, "age_variant": "both",
     "text": "Какие предметы в школе тебе даются легче и нравятся?", "text_junior": None,
     "options": [
         {"text": "математика, физика", "axis_weights": {"Data": 1, "Math": 2}},
         {"text": "биология, природа", "axis_weights": {"Living": 2}},
         {"text": "языки, литература, история", "axis_weights": {"Ideas": 1, "Exp": 1, "Math": -1}},
         {"text": "физкультура, труд, руками", "axis_weights": {"Motor": 1, "PhysSt": 1, "Math": -1}},
     ], "resolves_pair": None},
    {"order": 3, "kind": "direct", "depth": 1, "age_variant": "both",
     "text": "Когда ты с другими людьми, что тебе ближе?", "text_junior": None,
     "options": [
         {"text": "помогать тем, кому трудно", "axis_weights": {"Care": 1, "Emp": 1}},
         {"text": "вести, организовывать, быть главным", "axis_weights": {"Lead": 2}},
         {"text": "выступать, быть в центре внимания", "axis_weights": {"Vis": 2}},
         {"text": "просто общаться на равных", "axis_weights": {"People": 1}},
     ], "resolves_pair": None},
    {"order": 4, "kind": "direct", "depth": 2, "age_variant": "both",
     "text": "Помогать людям — это для тебя скорее…",
     "text_junior": "Что приятнее: помочь другу, когда он расстроен, или объяснить другу то, что он не понимает?",
     "options": [
         {"text": "когда кому-то плохо: поддержать, вылечить", "axis_weights": {"Care": 2}},
         {"text": "научить, чтобы человек дальше смог сам", "axis_weights": {"Dev": 2}},
     ], "resolves_pair": None},
    {"order": 5, "kind": "direct", "depth": 2, "age_variant": "both",
     "text": "Если бы ты кого-то учил — через что интереснее?",
     "text_junior": "Что тебе больше нравится: показывать другу игру и движения, объяснять правила, или утешать и подбадривать?",
     "options": [
         {"text": "через спорт, движение, тело", "axis_weights": {"Motor": 2, "Living": 1}},
         {"text": "через знания, предмет", "axis_weights": {"Exp": 2}},
         {"text": "через понимание чувств, поддержку", "axis_weights": {"Emp": 2}},
     ], "resolves_pair": None},
    {"order": 6, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Ты почти доделал дело, всё работает. Замечаешь мелкую ошибку, которую вряд ли кто-то увидит. Времени в обрез.",
     "text_junior": "Ты почти достроил классную штуку из конструктора, но одна деталь встала криво, а уже пора спать.",
     "options": [
         {"text": "переделаю — меня это будет раздражать", "axis_weights": {"Focus": 1, "Struct": 1}},
         {"text": "оставлю как есть, работает же", "axis_weights": {"Motiv": -1}},
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 7, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Что тебе приятнее на целый день?",
     "text_junior": "Что в школе больше нравится: один большой проект надолго или много коротких разных заданий?",
     "options": [
         {"text": "одно большое дело — погрузиться надолго", "axis_weights": {"Focus": 2}},
         {"text": "много разных мелких задач, переключаться", "axis_weights": {"Focus": -2, "Pace": 1}},
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 8, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Что тебе ближе?",
     "text_junior": "В игре ты скорее идёшь проверенным путём, чтобы точно выиграть, или рискуешь ради большого выигрыша?",
     "options": [
         {"text": "надёжное и понятное, со стабильным результатом", "axis_weights": {"Risk": -2}},
         {"text": "рискованное, но может выстрелить по-крупному", "axis_weights": {"Risk": 2}},
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 9, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Работа мечты — это скорее…",
     "text_junior": "Тебе больше нравится делать что-то вместе с друзьями или самому, как ты хочешь?",
     "options": [
         {"text": "в команде, вместе с другими", "axis_weights": {"Auto": -2}},
         {"text": "самому, по-своему", "axis_weights": {"Auto": 2}},
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 10, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Что тебе комфортнее?",
     "text_junior": "Тебе больше нравятся игры с чёткими правилами или где можно придумывать свои?",
     "options": [
         {"text": "чёткие правила и понятный порядок", "axis_weights": {"Struct": 2}},
         {"text": "свобода делать по-своему, без рамок", "axis_weights": {"Struct": -2}},
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 11, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Какая работа ближе?",
     "text_junior": "Тебе больше нравится, когда день спокойный и понятный, или когда всё время что-то новое и быстрое?",
     "options": [
         {"text": "спокойная, размеренная, предсказуемая", "axis_weights": {"Pace": -1, "Predict": -1}},
         {"text": "быстрая, где каждый день по-разному", "axis_weights": {"Pace": 1, "Predict": 1}},
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 12, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Что тебя больше радует?",
     "text_junior": "Что приятнее: сама игра или момент, когда выиграл?",
     "options": [
         {"text": "сам процесс, когда занимаешься любимым делом", "axis_weights": {"Motiv": -2}},
         {"text": "результат: победа, когда добился цели", "axis_weights": {"Motiv": 2}},
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 13, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Тебе дали задачу. Что приятнее?",
     "text_junior": "Что интереснее: придумать свою игру или пройти готовую как можно лучше?",
     "options": [
         {"text": "придумать своё, с нуля", "axis_weights": {"Inv": 2}},
         {"text": "сделать хорошо по готовому образцу", "axis_weights": {"Inv": -2}},
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 14, "kind": "direct", "depth": 2, "age_variant": "both",
     "text": "Что интереснее?",
     "text_junior": "Что интереснее: собрать что-то работающее или разгадать загадку?",
     "options": [
         {"text": "строить, создавать работающую вещь", "axis_weights": {"Obj": 2}},
         {"text": "разбираться, докапываться до сути, находить ответ", "axis_weights": {"Obj": -2}},
     ], "resolves_pair": None},
    {"order": 15, "kind": "direct", "depth": 2, "age_variant": "both",
     "text": "Тебе комфортнее…", "text_junior": None,
     "options": [
         {"text": "быть на виду, выступать", "axis_weights": {"Vis": 2}},
         {"text": "делать своё дело незаметно, за кадром", "axis_weights": {"Vis": -2}},
     ], "resolves_pair": None},
    {"order": 16, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Идеальное место, где ты проводишь день?",
     "text_junior": "Где тебе лучше: на улице бегать и что-то делать руками, или дома спокойно за столом?",
     "options": [
         {"text": "на улице, в движении, руками", "axis_weights": {"PhysSt": 2, "Phys": 1}},
         {"text": "за столом, в тепле, спокойно", "axis_weights": {"PhysSt": -2}},
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 17, "kind": "direct", "depth": 2, "age_variant": "senior",
     "text": "Профессия мечты требует 5–6 лет учёбы. Как тебе?", "text_junior": None,
     "options": [
         {"text": "нормально, если это моё", "axis_weights": {"Acad": 2}},
         {"text": "хочу начать работать раньше", "axis_weights": {"Acad": -2}},
         {"text": "пока не думал", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 18, "kind": "direct", "depth": 2, "age_variant": "both",
     "text": "Математика для тебя — это…",
     "text_junior": "Математика тебе нравится, так себе, или не очень?",
     "options": [
         {"text": "моё, люблю считать и решать", "axis_weights": {"Math": 2}},
         {"text": "терпимо, если по делу", "axis_weights": {}},
         {"text": "не моё", "axis_weights": {"Math": -2}},
     ], "resolves_pair": None},
    {"order": 19, "kind": "situational", "depth": 3, "age_variant": "senior",
     "text": "Тебе ближе помогать человеку так, чтобы…", "text_junior": None,
     "options": [
         {"text": "поддержать его чувства, разобраться в переживаниях", "axis_weights": {"Emp": 2, "Care": 1}},
         {"text": "натренировать конкретный навык, речь, умение", "axis_weights": {"Dev": 2, "Exp": 1}},
     ], "resolves_pair": ["psychologist", "speech-therapist"]},
    {"order": 20, "kind": "situational", "depth": 3, "age_variant": "senior",
     "text": "С человеком, который восстанавливается, тебе интереснее…", "text_junior": None,
     "options": [
         {"text": "вернуть его к здоровью, вылечить", "axis_weights": {"Care": 2, "Living": 1}},
         {"text": "довести до результата, до новой цели, до победы", "axis_weights": {"Dev": 2, "Motiv": 2}},
     ], "resolves_pair": ["rehabilitation-therapist", "sports-coach"]},
    {"order": 21, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Что ближе в работе с продуктом?", "text_junior": None,
     "options": [
         {"text": "напрямую убеждать людей, продавать, добиваться сделки", "axis_weights": {"Emp": 2, "Motiv": 2}},
         {"text": "придумывать, как о продукте узнают, кампании, идеи", "axis_weights": {"Inv": 2, "Ideas": 1}},
     ], "resolves_pair": ["sales-manager", "marketer"]},
    {"order": 22, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Если работать руками — с чем приятнее?", "text_junior": None,
     "options": [
         {"text": "с деревом, мебелью", "axis_weights": {}},
         {"text": "с трубами, водой, сантехникой", "axis_weights": {}},
         {"text": "с металлом, сваркой", "axis_weights": {}},
     ], "resolves_pair": ["carpenter", "plumber", "welder"]},
    {"order": 23, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "В рисовании и дизайне тебе ближе…", "text_junior": None,
     "options": [
         {"text": "рисовать от руки, свой стиль", "axis_weights": {"Motor": 1, "Struct": -2}},
         {"text": "собирать аккуратно в программе, по сетке", "axis_weights": {"Struct": 1, "Obj": 1}},
     ], "resolves_pair": ["illustrator", "graphic-designer"]},
    {"order": 24, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Когда рядом кому-то плохо и нужна помощь, ты…",
     "text_junior": "Когда друг поранился: бросаешься помогать сразу или сначала спокойно смотришь, что случилось?",
     "options": [
         {"text": "действую сразу, быстро, на месте", "axis_weights": {"Pace": 2, "Focus": -2, "Risk": 1}},
         {"text": "хочу разобраться спокойно и точно поставить диагноз", "axis_weights": {"Focus": 2, "Exp": 1}},
     ], "resolves_pair": ["paramedic", "physician", "surgeon"]},
    {"order": 25, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "В медицине тебе ближе…", "text_junior": None,
     "options": [
         {"text": "работать руками: операции, процедуры", "axis_weights": {"Motor": 2, "Phys": 1}},
         {"text": "думать, разбирать сложные случаи, назначать лечение", "axis_weights": {"Focus": 2, "Data": 1}},
         {"text": "поддерживать и разговаривать с человеком", "axis_weights": {"Emp": 2, "Care": 1}},
     ], "resolves_pair": ["surgeon", "physician", "psychiatrist"]},
    {"order": 26, "kind": "direct", "depth": 2, "age_variant": "both",
     "text": "Про животных и природу — что ближе?",
     "text_junior": "С животными интереснее: лечить и заботиться, наблюдать и изучать, или ухаживать за растениями?",
     "options": [
         {"text": "лечить и заботиться о конкретных животных", "axis_weights": {"Care": 2, "Living": 2}},
         {"text": "изучать их, наблюдать, понимать, как всё устроено", "axis_weights": {"Obj": -2, "Exp": 2, "Focus": 2}},
         {"text": "работать на земле, выращивать", "axis_weights": {"Phys": 1, "PhysSt": 1}},
     ], "resolves_pair": ["veterinarian", "zoologist", "ecologist", "agronomist"]},
    {"order": 27, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Тебе дали технику. Что интереснее?",
     "text_junior": "Сломанную игрушку интереснее починить руками или придумать, как сделать её лучше?",
     "options": [
         {"text": "починить то, что сломалось, руками", "axis_weights": {"Motor": 2, "Phys": 2}},
         {"text": "спроектировать, рассчитать, как сделать лучше", "axis_weights": {"Data": 1, "Math": 2, "Focus": 2, "Obj": 2}},
     ], "resolves_pair": None},  # source says "vs инженер" without specifying which — flagged, see module docstring
    {"order": 28, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Если проектировать — что ближе?", "text_junior": None,
     "options": [
         {"text": "механизмы, машины, устройства", "axis_weights": {"Phys": 2}},
         {"text": "здания, мосты, конструкции", "axis_weights": {"Phys": 2, "Struct": 2, "Lead": 1}},
     ], "resolves_pair": ["mechanical-engineer", "civil-engineer"]},
    {"order": 29, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Работа руками — тебе как?",
     "text_junior": "Тебе нравится активная работа руками, где надо двигаться, или спокойнее?",
     "options": [
         {"text": "да, люблю физическую работу, на ногах, с материалами", "axis_weights": {"PhysSt": 2, "Motor": 1, "Phys": 2}},
         {"text": "лучше что-то поспокойнее, не тяжёлое физически", "axis_weights": {"PhysSt": -2}},
     ], "resolves_pair": None},
    {"order": 30, "kind": "direct", "depth": 2, "age_variant": "both",
     "text": "В творчестве что тебя тянет?",
     "text_junior": "Больше нравится рисовать и создавать красивое или выступать на сцене?",
     "options": [
         {"text": "создавать красивое: рисунок, дизайн, вещи", "axis_weights": {"Ideas": 2, "Inv": 2}},
         {"text": "выступать: сцена, музыка, камера", "axis_weights": {"Vis": 2, "Ideas": 1}},
     ], "resolves_pair": None},  # source says "дизайн/иллюстрация vs сцена" (branch-level) — flagged, see module docstring
    {"order": 31, "kind": "situational", "depth": 3, "age_variant": "senior",
     "text": "На сцене или перед камерой тебе ближе…", "text_junior": None,
     "options": [
         {"text": "вживаться в роль, играть, быть кем-то", "axis_weights": {"Emp": 1, "Ideas": 2}},
         {"text": "вести, зажигать зал, быть собой на публике", "axis_weights": {"Vis": 2, "People": 2, "Risk": 1, "Predict": 2}},
     ], "resolves_pair": ["actor", "blogger-host"]},
    {"order": 32, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Работа со словами и текстами — что ближе?",
     "text_junior": "Тебе интереснее быстро узнавать новости и рассказывать, или спокойно сочинять и писать?",
     "options": [
         {"text": "быстро реагировать на события, узнавать новое, писать про это", "axis_weights": {"Pace": 2, "Predict": 2, "Obj": -2}},
         {"text": "спокойно и вдумчиво работать над текстом самому", "axis_weights": {"Focus": 2, "Auto": 2}},
     ], "resolves_pair": ["journalist", "copywriter", "translator"]},
    {"order": 33, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "В спорте что ближе?", "text_junior": None,
     "options": [
         {"text": "самому добиваться результата, соревноваться", "axis_weights": {"Motiv": 2, "PhysSt": 2, "Vis": 1}},
         {"text": "тренировать других, растить их результат", "axis_weights": {"Dev": 2, "Lead": 1}},
         {"text": "помогать восстановиться после травм", "axis_weights": {"Care": 2, "Living": 2}},
     ], "resolves_pair": ["athlete", "sports-coach", "rehabilitation-therapist"]},
    {"order": 34, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "На кухне или в кафе тебе ближе…",
     "text_junior": "Что интереснее: самому готовить вкусное или встречать гостей и общаться?",
     "options": [
         {"text": "готовить, придумывать блюда, творить со вкусом", "axis_weights": {"Inv": 1, "Motor": 2, "Ideas": 1}},
         {"text": "общаться с гостями, обслуживать, создавать настроение", "axis_weights": {"People": 2, "Emp": 1, "Pace": 2}},
     ], "resolves_pair": ["chef", "pastry-chef", "barista", "waiter"]},
    {"order": 35, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Если готовить — что ближе?", "text_junior": None,
     "options": [
         {"text": "основные блюда, горячее, скорость кухни", "axis_weights": {"Pace": 2, "Lead": 1}},
         {"text": "десерты, выпечка, точность и красота", "axis_weights": {"Focus": 2, "Struct": 2, "Ideas": 2}},
     ], "resolves_pair": ["chef", "pastry-chef"]},
    {"order": 36, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Тебе дали цель и свободу. Ты…",
     "text_junior": "Тебе интереснее придумать своё дело и вести его самому или делать понятную работу спокойно?",
     "options": [
         {"text": "рискну, придумаю своё дело, буду сам за всё отвечать", "axis_weights": {"Risk": 2, "Auto": 2, "Inv": 2, "Lead": 2}},
         {"text": "лучше в понятной роли с стабильностью", "axis_weights": {"Risk": -2, "Struct": 1}},
     ], "resolves_pair": None},  # source says "предприниматель vs исполнительские роли" (generic) — flagged, see module docstring
    {"order": 37, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "С числами и деньгами тебе как?", "text_junior": None,
     "options": [
         {"text": "люблю точность, порядок, считать", "axis_weights": {"Data": 2, "Struct": 2, "Focus": 2, "Math": 2}},
         {"text": "скучно, мне интереснее люди и идеи", "axis_weights": {"Data": -1, "People": 1}},
     ], "resolves_pair": None},  # source says "бухгалтер vs остальной бизнес" (generic) — flagged, see module docstring
    {"order": 38, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "В опасной или острой ситуации ты…",
     "text_junior": "Тебе ближе спасать и действовать в опасности или следить за порядком, чтобы не случилось плохого?",
     "options": [
         {"text": "готов рисковать, спасать, действовать быстро", "axis_weights": {"Risk": 2, "Pace": 2, "PhysSt": 2, "Care": 1}},
         {"text": "лучше держать порядок, следить, предотвращать", "axis_weights": {"Struct": 2, "Focus": 1}},
     ], "resolves_pair": ["firefighter", "rescuer", "police-officer"]},
    {"order": 39, "kind": "direct", "depth": 2, "age_variant": "both",
     "text": "Делать людей красивее, работать над образом — тебе как?",
     "text_junior": "Тебе нравится придумывать причёски, образы, делать красиво?",
     "options": [
         {"text": "да, нравится: причёски, макияж, стиль", "axis_weights": {"People": 1, "Motor": 2, "Ideas": 1, "Vis": 1}},
         {"text": "не моё", "axis_weights": {}},
     ], "resolves_pair": None},
    {"order": 40, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Какая работа тебе ок, даже если она простая?", "text_junior": None,
     "options": [
         {"text": "на ходу, за рулём, доставлять, двигаться", "axis_weights": {"Auto": 2, "PhysSt": 1, "Predict": -1}},
         {"text": "на одном месте, по чёткому порядку", "axis_weights": {"Struct": 2, "Auto": -2, "Predict": -2}},
         {"text": "общаться с покупателями, помогать выбрать", "axis_weights": {"People": 2, "Emp": 1}},
     ], "resolves_pair": ["taxi-driver", "courier", "warehouse-worker", "sales-consultant"]},
]

assert len(QUESTIONS) == 41, f"expected 41 questions, got {len(QUESTIONS)}"


# ---------------------------------------------------------------------------
# 3. Idempotent upserts
# ---------------------------------------------------------------------------

async def seed_sections(db: AsyncSession) -> tuple[dict[str, uuid.UUID], int, int, int]:
    """Upsert the 16 branch Directions by slug. Returns (slug -> id, inserted, updated, skipped)."""
    ids: dict[str, uuid.UUID] = {}
    inserted = updated = skipped = 0

    for section in SECTIONS:
        result = await db.execute(select(Direction).where(Direction.slug == section["slug"]))
        existing = result.scalar_one_or_none()

        if existing is not None:
            changed = existing.name != section["name"] or existing.is_leaf is not False
            if existing.name != section["name"]:
                existing.name = section["name"]
            if existing.is_leaf is not False:
                existing.is_leaf = False
            ids[section["slug"]] = existing.id
            updated += 1 if changed else 0
            skipped += 0 if changed else 1
            continue

        direction = Direction(
            name=section["name"],
            slug=section["slug"],
            description=(
                f"Раздел каталога акинатора: {section['name']} "
                "(перенесено из akinatorLogic/profi_full_catalog.md, черновик Фазы 2)."
            ),
            required_scores={},
            bonus_scores={},
            is_leaf=False,
            profile={},
        )
        db.add(direction)
        await db.flush()
        ids[section["slug"]] = direction.id
        inserted += 1

    return ids, inserted, updated, skipped


async def seed_professions(
    db: AsyncSession, section_ids: dict[str, uuid.UUID]
) -> tuple[int, int, int]:
    """Upsert the 67 leaf Directions by slug. Returns (inserted, updated, skipped)."""
    inserted = updated = skipped = 0

    for prof in PROFESSIONS:
        parent_id = section_ids[prof["section"]]
        result = await db.execute(select(Direction).where(Direction.slug == prof["slug"]))
        existing = result.scalar_one_or_none()

        if existing is not None:
            changed = False
            if existing.name != prof["name"]:
                existing.name = prof["name"]
                changed = True
            if existing.profile != prof["profile"]:
                existing.profile = prof["profile"]
                changed = True
            if existing.parent_id != parent_id:
                existing.parent_id = parent_id
                changed = True
            if existing.is_leaf is not True:
                existing.is_leaf = True
                changed = True
            updated += 1 if changed else 0
            skipped += 0 if changed else 1
            continue

        direction = Direction(
            name=prof["name"],
            slug=prof["slug"],
            description=(
                f"Профессия «{prof['name']}» "
                "(перенесено из akinatorLogic/profi_full_catalog.md, черновик Фазы 2)."
            ),
            required_scores={},
            bonus_scores={},
            parent_id=parent_id,
            is_leaf=True,
            profile=prof["profile"],
        )
        db.add(direction)
        inserted += 1

    return inserted, updated, skipped


async def seed_questions(db: AsyncSession) -> tuple[int, int, int]:
    """Upsert the 41 AkinatorQuestion rows by `order` (this script owns 0-40).
    Returns (inserted, updated, skipped)."""
    inserted = updated = skipped = 0

    for q in QUESTIONS:
        result = await db.execute(
            select(AkinatorQuestion).where(AkinatorQuestion.order == q["order"])
        )
        existing = result.scalar_one_or_none()

        fields = {
            "kind": q["kind"],
            "depth": q["depth"],
            "age_variant": q["age_variant"],
            "text": q["text"],
            "text_junior": q["text_junior"],
            "options": q["options"],
            "resolves_pair": q["resolves_pair"],
        }

        if existing is not None:
            changed = False
            for field, value in fields.items():
                if getattr(existing, field) != value:
                    setattr(existing, field, value)
                    changed = True
            updated += 1 if changed else 0
            skipped += 0 if changed else 1
            continue

        db.add(AkinatorQuestion(order=q["order"], is_active=True, **fields))
        inserted += 1

    return inserted, updated, skipped


async def main() -> None:
    async with async_session() as db:
        section_ids, sec_ins, sec_upd, sec_skip = await seed_sections(db)
        prof_ins, prof_upd, prof_skip = await seed_professions(db, section_ids)
        q_ins, q_upd, q_skip = await seed_questions(db)
        await db.commit()

        print(
            f"Sections:    inserted {sec_ins}, updated {sec_upd}, skipped {sec_skip} "
            f"(total {len(SECTIONS)})"
        )
        print(
            f"Professions: inserted {prof_ins}, updated {prof_upd}, skipped {prof_skip} "
            f"(total {len(PROFESSIONS)})"
        )
        print(
            f"Questions:   inserted {q_ins}, updated {q_upd}, skipped {q_skip} "
            f"(total {len(QUESTIONS)})"
        )


if __name__ == "__main__":
    asyncio.run(main())
