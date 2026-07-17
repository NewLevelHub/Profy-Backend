"""
Seed script: transfer the manually-reviewed AKN-009 draft content into the DB
via the AKN-002 (Direction tree columns) / AKN-003 (AkinatorQuestion) models.

Source of truth (transcribed as-is, NOT regenerated through the AKN-006/007/008
LLM draft generators):
  - akinatorLogic/profi_full_catalog.md  -> sections (branches) + professions (leaves)
  - akinatorLogic/profi_questions_mvp.md + profi_questions_full_addon.md -> q01-q41

Idempotent: Direction rows are upserted by `slug`. AkinatorQuestion rows are
upserted by `order` — this script owns orders 0-49; don't reuse that range for
other seeded/generated question batches.

Calibration pass (2026-07): orders 41-44 add resolves_pair disambiguators for
profession pairs found to have high profile-similarity but zero coverage in
the original q01-q41 set (dentist, psychiatrist/psychologist, nurse/paramedic,
electrician/auto-mechanic) — see the AKN calibration ticket.

Retirement pass (2026-07): cut 16 low-fit professions that have no university
track (the product generates university-admission roadmaps).

Replacement pass (2026-07): the retirement pass left orphaned questions whose
options pointed at nothing (order 39 "образ/причёски" had zero targets after
hairdresser+makeup-artist were cut; order 34 option 2 "общаться с гостями" had
zero targets after barista+waiter were cut). Rather than retiring those
questions, this pass adds the university-track equivalents the retired
professions were proxying for, which revives the questions:
    carpenter          -> furniture-designer      (Дизайнер мебели)
    plumber            -> building-systems-engineer (Инженер инженерных систем)
    photographer       -> cinematographer         (Кинооператор)
    copywriter         -> pr-specialist           (Реклама и PR)
    barista/waiter     -> hospitality-manager     (Менеджер ресторанного дела)
    hairdresser/makeup -> makeup-artist-film      (Художник-гримёр)
    taxi/courier/whse  -> logistician             (Логист)
    blogger-host       -> merged into journalist (already present)
    tutor              -> merged into school-teacher (already present)
    sales-consultant   -> merged into sales-manager (already present)
    coach              -> dropped entirely (no university track, low signal)
    social-worker      -> RESTORED (Социальная работа is a real bachelor track;
                          it was cut together with coach by mistake)
Sections akinator-beauty-services / akinator-logistics-service stay retired —
their replacements live under stage-media / business-sales respectively, so a
one-leaf branch (which forks nothing) is avoided.

Age-group pass (2026-07): professions are NO LONGER offered to `junior`.
Product rule: junior converges to a broad DIRECTION (a section), middle/senior
converge to a concrete PROFESSION (a leaf). Consequently sections now carry
centroid profiles (mean of their leaves) — without them junior's belief could
not move at all, which was the real bug the previous all-ages patch was working
around. `label_junior` stays as the friendlier display name shown to `middle`
(e.g. surgeon -> "Врач"), since middle does get leaves.

NOTE for product review: `Profile.compute_age_group` maps junior<=9,
middle 10-13, senior 14+. The product targets 10-17, so `junior` is nearly
empty in practice and the "soft direction" audience is effectively `middle`.
If directions (not professions) should go to 10-13 year olds, move "middle"
from PROFESSION_AGE_GROUPS to SECTION_AGE_GROUPS — single-constant change.

Run inside Docker:
    docker-compose exec api python scripts/seed_akinator_content.py
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.akinator_question import AkinatorQuestion
from app.models.assessment import Assessment
from app.models.direction import Direction

# ---------------------------------------------------------------------------
# 1. Taxonomy — 14 sections (branches) + 59 professions (leaves)
# ---------------------------------------------------------------------------

SECTIONS: list[dict] = [
    {"slug": "akinator-medicine", "name": "Медицина и здоровье"},
    {"slug": "akinator-psychology-help", "name": "Помощь и психология"},
    {"slug": "akinator-animals-nature", "name": "Животные и природа"},
    {"slug": "akinator-it-data", "name": "IT и данные"},
    {"slug": "akinator-engineering-tech", "name": "Инженерия и техника"},
    {"slug": "akinator-creative-design", "name": "Творчество и дизайн"},
    {"slug": "akinator-stage-media", "name": "Сцена и медиа"},
    {"slug": "akinator-words-communication", "name": "Слово и коммуникация"},
    {"slug": "akinator-education", "name": "Образование"},
    {"slug": "akinator-sports-body", "name": "Спорт и тело"},
    {"slug": "akinator-food-hospitality", "name": "Еда и гостеприимство"},
    {"slug": "akinator-business-sales", "name": "Бизнес и продажи"},
    {"slug": "akinator-safety-rescue", "name": "Безопасность и спасение"},
]

PROFESSIONS: list[dict] = [
    # Медицина и здоровье
    {"slug": "surgeon", "name": "Хирург", "label_junior": "Врач", "section": "akinator-medicine", "profile": {"People": 1, "Living": 2, "Phys": 2, "Care": 2, "Dev": -1, "Motor": 2, "Exp": 2, "Focus": 2, "Risk": 1, "Struct": 2, "Pace": 1, "Acad": 2, "PhysSt": 1}},
    {"slug": "physician", "name": "Терапевт", "label_junior": "Врач", "section": "akinator-medicine", "profile": {"People": 2, "Living": 2, "Care": 2, "Exp": 2, "Emp": 1, "Focus": 1, "Struct": 1, "Predict": 1, "Acad": 2}},
    {"slug": "psychiatrist", "name": "Психиатр", "label_junior": "Врач", "section": "akinator-medicine", "profile": {"People": 2, "Living": 1, "Care": 2, "Exp": 2, "Emp": 2, "Focus": 2, "Struct": 1, "Acad": 2, "Data": -1}},
    # University pass: `paramedic` was a calque — the RU equivalent (фельдшер) is
    # СПО. Its university-level growth is emergency medicine (Лечебное дело +
    # ординатура «Скорая медицинская помощь»), which had no leaf, so the leaf is
    # replaced rather than dropped. Acad -> +2 (med school), Risk -> +2.
    {"slug": "emergency-physician", "name": "Врач скорой помощи", "section": "akinator-medicine", "profile": {"People": 2, "Living": 2, "Phys": 1, "Care": 2, "Motor": 1, "Exp": 2, "Focus": -2, "Risk": 2, "Struct": 1, "Pace": 2, "Predict": 2, "PhysSt": 1, "Acad": 2}},
    {"slug": "dentist", "name": "Стоматолог", "label_junior": "Зубной врач", "section": "akinator-medicine", "profile": {"People": 1, "Living": 2, "Phys": 1, "Care": 2, "Motor": 2, "Exp": 2, "Focus": 2, "Struct": 1, "Acad": 2}},
    {"slug": "pharmacist", "name": "Фармацевт", "label_junior": "Аптекарь", "section": "akinator-medicine", "profile": {"People": 1, "Living": 1, "Data": 1, "Care": 1, "Exp": 2, "Focus": 1, "Struct": 2, "Predict": -1, "Acad": 1, "Math": 1}},

    # Помощь и психология
    {"slug": "psychologist", "name": "Психолог", "section": "akinator-psychology-help", "profile": {"People": 2, "Care": 2, "Emp": 2, "Exp": 2, "Focus": 2, "Motiv": -1, "Auto": 1, "Acad": 2, "Data": -1, "Ideas": 1}},
    {"slug": "speech-therapist", "name": "Логопед", "section": "akinator-psychology-help", "profile": {"People": 2, "Care": 1, "Dev": 2, "Emp": 1, "Exp": 2, "Focus": 1, "Struct": 1, "Acad": 1}},
    # Restored (replacement pass): cut together with `coach`, but Социальная
    # работа is a real bachelor programme. Separated from psychologist by
    # Exp/Focus (practical case-work vs deep individual study) — see order 47.
    {"slug": "social-worker", "name": "Социальный работник", "section": "akinator-psychology-help", "profile": {"People": 2, "Care": 2, "Emp": 2, "Lead": 1, "Struct": 1, "Motiv": -1, "Pace": 1, "Predict": 1, "Acad": 1}},

    # Животные и природа
    {"slug": "veterinarian", "name": "Ветеринар", "section": "akinator-animals-nature", "profile": {"People": 1, "Living": 2, "Phys": 1, "Care": 2, "Motor": 1, "Exp": 2, "Focus": 1, "Acad": 2, "PhysSt": 1, "Ideas": -1}},
    {"slug": "zoologist", "name": "Зоолог", "label_junior": "Учёный по животным", "section": "akinator-animals-nature", "profile": {"Living": 2, "Data": 1, "Obj": -2, "Exp": 2, "Focus": 2, "Auto": 1, "Predict": 1, "Acad": 2, "People": -1, "PhysSt": 1}},
    {"slug": "agronomist", "name": "Агроном", "label_junior": "Специалист по растениям", "section": "akinator-animals-nature", "profile": {"Living": 2, "Phys": 1, "Data": 1, "Exp": 1, "Struct": 1, "Predict": -1, "PhysSt": 1}},
    # University pass: kept — 36.03.02 «Зоотехния», профиль «Кинология» (плюс
    # ведомственные вузы, служебная кинология). Acad -1 -> +1 accordingly.
    {"slug": "cynologist", "name": "Кинолог", "label_junior": "Специалист по собакам", "section": "akinator-animals-nature", "profile": {"People": 1, "Living": 2, "Phys": 1, "Dev": 2, "Care": 1, "Motor": 1, "Exp": 1, "Struct": 1, "PhysSt": 1, "Acad": 1}},
    {"slug": "ecologist", "name": "Эколог", "section": "akinator-animals-nature", "profile": {"Living": 2, "Data": 1, "Ideas": 1, "Obj": -2, "Exp": 1, "Auto": 1, "Predict": 1, "Acad": 1}},

    # IT и данные
    {"slug": "programmer", "name": "Программист", "section": "akinator-it-data", "profile": {"People": -1, "Living": -2, "Data": 2, "Ideas": 1, "Inv": 1, "Obj": 2, "Care": -2, "Dev": -2, "Exp": 2, "Focus": 2, "Motiv": 1, "Auto": 1, "Struct": 1, "Acad": 1, "PhysSt": -2, "Math": 2}},
    {"slug": "data-analyst", "name": "Аналитик данных", "label_junior": "Аналитик", "section": "akinator-it-data", "profile": {"People": -1, "Living": -2, "Data": 2, "Obj": -2, "Care": -2, "Dev": -2, "Exp": 1, "Focus": 2, "Auto": 1, "Struct": 1, "Predict": -1, "Acad": 1, "PhysSt": -2, "Math": 2}},
    {"slug": "qa-tester", "name": "QA-тестировщик", "label_junior": "Тестировщик программ", "section": "akinator-it-data", "profile": {"Data": 2, "Obj": -1, "Exp": 1, "Focus": 1, "Struct": 2, "Predict": -1, "Motiv": -1, "PhysSt": -2, "Math": 1, "People": -1}},
    {"slug": "ux-designer", "name": "UX-дизайнер", "label_junior": "Дизайнер приложений", "section": "akinator-it-data", "profile": {"People": 1, "Data": 1, "Ideas": 2, "Inv": 2, "Obj": 1, "Emp": 1, "Exp": 1, "PhysSt": -1}},
    {"slug": "sysadmin", "name": "Сисадмин", "label_junior": "Компьютерный мастер", "section": "akinator-it-data", "profile": {"Phys": 1, "Data": 2, "Obj": 1, "Exp": 2, "Focus": -1, "Auto": 1, "Struct": 1, "Pace": 1, "Predict": 1, "PhysSt": -1, "Math": 1, "People": -1}},

    # Инженерия и техника
    {"slug": "mechanical-engineer", "name": "Инженер-механик", "label_junior": "Инженер", "section": "akinator-engineering-tech", "profile": {"Phys": 2, "Data": 1, "Ideas": 1, "Inv": 1, "Obj": 2, "Exp": 2, "Focus": 1, "Struct": 1, "Acad": 2, "Math": 2, "People": -1}},
    {"slug": "civil-engineer", "name": "Инженер-строитель", "section": "akinator-engineering-tech", "profile": {"Phys": 2, "Data": 1, "Obj": 2, "Lead": 1, "Exp": 2, "Focus": 1, "Struct": 2, "Risk": -1, "Acad": 2, "Math": 2}},
    # Replacement for `plumber` (replacement pass). Water/HVAC systems design.
    # Separated from civil-engineer by Motor/Predict/Lead (hands-on
    # commissioning, routine networks, no crew leadership) — see order 28.
    {"slug": "building-systems-engineer", "name": "Инженер инженерных систем", "label_junior": "Инженер", "section": "akinator-engineering-tech", "profile": {"Phys": 2, "Data": 1, "Obj": 2, "Motor": 1, "Exp": 2, "Focus": 2, "Struct": 2, "Predict": -1, "Acad": 1, "Math": 2, "People": -1}},
    # Motor:1 added (calibration pass): piloting is a hands-on motor/instrument-
    # coordination skill, missing entirely before — the profile was otherwise
    # near-indistinguishable from lawyer (cosine similarity 0.80) purely on
    # shared Data/Lead/Exp/Focus/Struct/Acad "serious professional" traits.
    {"slug": "pilot", "name": "Пилот", "section": "akinator-engineering-tech", "profile": {"Phys": 1, "Data": 1, "Lead": 1, "Motor": 1, "Exp": 2, "Focus": 2, "Risk": 1, "Struct": 2, "Pace": 1, "Acad": 1, "Math": 1}},

    # Строительство и руками
    # NOTE for product review: welder/construction-worker carry Acad -2, i.e.
    # explicitly "no university". The product generates university-admission
    # roadmaps, so these two are inconsistent with the retirement pass criterion
    # (carpenter/plumber were cut for exactly this reason). Kept as-is pending a
    # product decision — see the "Открытый вопрос" note at the bottom of this file.

    # Творчество и дизайн
    {"slug": "graphic-designer", "name": "Графический дизайнер", "label_junior": "Дизайнер", "section": "akinator-creative-design", "profile": {"Ideas": 2, "Inv": 2, "Obj": 1, "Exp": 1, "Auto": 1, "Struct": -1, "Math": -1, "PhysSt": -1}},
    {"slug": "illustrator", "name": "Иллюстратор", "label_junior": "Художник", "section": "akinator-creative-design", "profile": {"Ideas": 2, "Inv": 2, "Motor": 1, "Auto": 2, "Struct": -2, "Vis": -1, "Math": -1, "PhysSt": -1, "People": -1, "Exp": 1}},
    {"slug": "architect", "name": "Архитектор", "section": "akinator-creative-design", "profile": {"People": 1, "Phys": 1, "Data": 1, "Ideas": 2, "Inv": 2, "Obj": 1, "Lead": 1, "Exp": 2, "Focus": 2, "Struct": 2, "Auto": 1, "Acad": 2, "Math": 1, "PhysSt": -1}},
    {"slug": "fashion-designer", "name": "Модельер", "section": "akinator-creative-design", "profile": {"Ideas": 2, "Inv": 2, "Phys": 1, "Motor": 1, "Vis": 1, "Exp": 1, "Auto": 1, "Struct": -1, "Risk": 1}},
    # Replacement for `carpenter` (replacement pass). Keeps the Ideas+Motor
    # "make a tangible beautiful thing" pull but on a university track.
    # Separated from graphic-designer by Phys+2 (tangible vs screen) and from
    # architect by Lead/Struct/Acad — see order 49.
    {"slug": "furniture-designer", "name": "Дизайнер мебели", "label_junior": "Дизайнер вещей", "section": "akinator-creative-design", "profile": {"Phys": 2, "Ideas": 2, "Inv": 2, "Obj": 1, "Motor": 1, "Exp": 1, "Focus": 1, "Auto": 1, "Acad": 1, "Math": 1}},

    # Сцена и медиа
    {"slug": "actor", "name": "Актёр", "section": "akinator-stage-media", "profile": {"People": 1, "Ideas": 2, "Vis": 2, "Emp": 1, "Motor": 1, "Risk": 1, "Struct": -1, "Auto": -1, "Predict": 1, "PhysSt": 1, "Math": -1, "Data": -1}},
    {"slug": "musician", "name": "Музыкант", "section": "akinator-stage-media", "profile": {"Ideas": 2, "Vis": 1, "Motor": 2, "Exp": 2, "Focus": 2, "Auto": 1, "Risk": 1, "Struct": -1}},
    {"slug": "film-director", "name": "Режиссёр", "section": "akinator-stage-media", "profile": {"People": 1, "Ideas": 2, "Inv": 2, "Lead": 2, "Exp": 1, "Focus": 1, "Risk": 1, "Auto": 1, "Struct": -1}},
    # Replacement for `photographer` (replacement pass). Separated from
    # film-director by Lead 0 vs +2, Motor +2 vs 0, Vis -1 vs 0 — see order 46.
    {"slug": "cinematographer", "name": "Кинооператор", "label_junior": "Оператор кино", "section": "akinator-stage-media", "profile": {"Phys": 1, "Ideas": 2, "Inv": 1, "Vis": -1, "Motor": 2, "Exp": 2, "Focus": 2, "Auto": 1, "Acad": 1, "PhysSt": 1}},
    # Replacement for `hairdresser` + `makeup-artist` (replacement pass).
    # This is what revives question order 39 — without it that question's
    # weights pointed at no leaf at all. Separated from fashion-designer by
    # People +2 vs 0 (works on a human face, not on cloth) and Vis -1 vs +1.
    {"slug": "makeup-artist-film", "name": "Художник-гримёр", "label_junior": "Гримёр", "section": "akinator-stage-media", "profile": {"People": 2, "Ideas": 2, "Inv": 2, "Motor": 2, "Emp": 1, "Exp": 1, "Vis": -1, "Auto": 1, "Acad": 1}},

    # Слово и коммуникация
    {"slug": "journalist", "name": "Журналист", "section": "akinator-words-communication", "profile": {"People": 1, "Ideas": 1, "Obj": -2, "Vis": 1, "Exp": 1, "Emp": 1, "Risk": 1, "Pace": 2, "Predict": 2, "Acad": 1, "Struct": -1}},
    {"slug": "translator", "name": "Переводчик", "section": "akinator-words-communication", "profile": {"Ideas": 1, "Obj": -1, "Exp": 2, "Focus": 2, "Auto": 2, "Struct": 1, "Predict": -1, "Acad": 1, "People": -1}},
    {"slug": "lawyer", "name": "Юрист", "section": "akinator-words-communication", "profile": {"People": 1, "Data": 1, "Obj": -1, "Lead": 1, "Vis": 1, "Exp": 2, "Focus": 2, "Struct": 2, "Acad": 2}},
    # Replacement for `copywriter` (replacement pass). "Реклама и связи с
    # общественностью" is a real bachelor track. Separated from marketer by
    # Data -1 vs +1 and Math -1 vs 0 (message craft vs campaign analytics) —
    # see order 45.
    {"slug": "pr-specialist", "name": "Специалист по рекламе и PR", "label_junior": "Специалист по рекламе", "section": "akinator-words-communication", "profile": {"People": 1, "Ideas": 2, "Inv": 2, "Vis": 1, "Emp": 1, "Exp": 1, "Focus": 1, "Auto": 1, "Struct": -1, "Data": -1, "Math": -1, "Acad": 1}},

    # Образование
    {"slug": "school-teacher", "name": "Учитель", "section": "akinator-education", "profile": {"People": 2, "Dev": 2, "Care": 1, "Lead": 1, "Vis": 1, "Exp": 1, "Emp": 1, "Focus": -1, "Struct": 1, "Acad": 1}},
    {"slug": "kindergarten-teacher", "name": "Воспитатель", "section": "akinator-education", "profile": {"People": 2, "Care": 2, "Dev": 1, "Emp": 2, "Focus": -1, "Struct": 1, "Pace": 1, "PhysSt": 1}},

    # Спорт и тело
    {"slug": "sports-coach", "name": "Спортивный тренер", "section": "akinator-sports-body", "profile": {"People": 1, "Living": 1, "Dev": 2, "Care": 1, "Lead": 1, "Motor": 1, "Emp": 1, "Motiv": 2, "Pace": 1, "PhysSt": 1, "Exp": 1}},
    {"slug": "rehabilitation-therapist", "name": "Реабилитолог", "label_junior": "Врач по восстановлению", "section": "akinator-sports-body", "profile": {"People": 1, "Living": 2, "Care": 2, "Dev": 1, "Motor": 1, "Exp": 2, "Emp": 1, "Focus": 1, "Struct": 1, "Acad": 1, "PhysSt": 1}},

    # Еда и гостеприимство
    # University pass: `chef` (повар) is СПО. Growth = шеф-повар via 19.03.04
    # «Технология продукции и организация общественного питания» — no leaf existed,
    # so replaced. Keeps the Motor/Pace/Inv pull; Acad -1 -> +1, Data +1 (technology).
    {"slug": "head-chef", "name": "Шеф-повар", "section": "akinator-food-hospitality", "profile": {"Phys": 1, "Data": 1, "Ideas": 1, "Inv": 2, "Obj": 1, "Motor": 2, "Lead": 1, "Focus": -1, "Struct": 1, "Pace": 2, "PhysSt": 1, "Acad": 1}},
    # University pass: growth = 19.03.02 «Продукты питания из растительного сырья»,
    # профиль «Технология хлеба, кондитерских и макаронных изделий». Acad -1 -> +1.
    {"slug": "confectionery-technologist", "name": "Кондитер-технолог", "label_junior": "Кондитер", "section": "akinator-food-hospitality", "profile": {"Phys": 1, "Data": 1, "Ideas": 2, "Inv": 1, "Motor": 2, "Exp": 2, "Focus": 2, "Struct": 2, "PhysSt": 1, "Acad": 1, "Predict": -1}},
    # Replacement for `barista` + `waiter` (replacement pass). This is what
    # revives option 2 of question order 34 ("общаться с гостями") — without it
    # that option's weights pointed at no leaf. Separated from chef by
    # People +2 vs 0, Lead +2 vs +1, Motor 0 vs +2, Acad +1 vs -1.
    {"slug": "hospitality-manager", "name": "Менеджер ресторанного дела", "label_junior": "Управляющий кафе", "section": "akinator-food-hospitality", "profile": {"People": 2, "Data": 1, "Lead": 2, "Emp": 1, "Motiv": 1, "Risk": 1, "Struct": 1, "Pace": 2, "Predict": 1, "PhysSt": 1, "Acad": 1}},

    # Бизнес и продажи
    {"slug": "sales-manager", "name": "Менеджер по продажам", "label_junior": "Специалист по продажам", "section": "akinator-business-sales", "profile": {"People": 2, "Emp": 2, "Vis": 1, "Motiv": 2, "Risk": 1, "Auto": 1, "Predict": 2, "Pace": 1, "Struct": -1}},
    {"slug": "entrepreneur", "name": "Предприниматель", "label_junior": "Бизнесмен", "section": "akinator-business-sales", "profile": {"People": 1, "Ideas": 1, "Inv": 2, "Lead": 2, "Vis": 1, "Motiv": 2, "Risk": 2, "Auto": 2, "Struct": -2, "Predict": 2}},
    {"slug": "marketer", "name": "Маркетолог", "label_junior": "Специалист по рекламе", "section": "akinator-business-sales", "profile": {"People": 1, "Data": 1, "Ideas": 1, "Inv": 1, "Obj": -1, "Vis": 1, "Emp": 1, "Motiv": 1, "Predict": 1, "Acad": 1}},
    {"slug": "accountant", "name": "Бухгалтер", "section": "akinator-business-sales", "profile": {"Data": 2, "Obj": -1, "Exp": 2, "Focus": 2, "Struct": 2, "Motiv": -1, "Auto": 1, "Predict": -2, "Pace": -1, "Acad": 1, "Math": 2, "People": -1}},
    # Replacement for `taxi-driver` + `courier` + `warehouse-worker`
    # (replacement pass). Lives under business-sales rather than reviving the
    # one-leaf akinator-logistics-service section (a branch that forks nothing
    # is useless to the tree). Separated from accountant by Obj +1 vs -1,
    # Lead +1 vs 0, Pace +1 vs -1 — see order 48.
    {"slug": "logistician", "name": "Логист", "section": "akinator-business-sales", "profile": {"Data": 2, "Obj": 1, "Lead": 1, "Exp": 1, "Focus": 1, "Struct": 2, "Pace": 1, "Predict": -1, "Acad": 1, "Math": 1}},

    # Безопасность и спасение
    # University pass: рядовой пожарный/спасатель = СПО. Growth = Академия ГПС МЧС,
    # 20.03.01 «Техносферная безопасность» -> инженер пожарной безопасности. This
    # one leaf absorbs both retired `firefighter` and `rescuer` (they were a 0.94
    # cosine cluster anyway and share the same university track).
    {"slug": "fire-safety-engineer", "name": "Инженер пожарной безопасности", "label_junior": "Пожарный", "section": "akinator-safety-rescue", "profile": {"People": 1, "Phys": 1, "Data": 1, "Care": 1, "Obj": 1, "Lead": 1, "Exp": 2, "Focus": 1, "Risk": 2, "Struct": 2, "Pace": 1, "Predict": 1, "PhysSt": 1, "Acad": 1, "Math": 1}},
    {"slug": "police-officer", "name": "Полицейский", "section": "akinator-safety-rescue", "profile": {"People": 1, "Phys": 1, "Lead": 1, "Exp": 1, "Focus": -1, "Risk": 1, "Struct": 2, "Pace": 1, "Predict": 1, "PhysSt": 1}},
]

assert len(SECTIONS) == 13, f"expected 14 sections, got {len(SECTIONS)}"
assert len(PROFESSIONS) == 51, f"expected 59 professions, got {len(PROFESSIONS)}"

_SECTION_SLUGS = {s["slug"] for s in SECTIONS}
for _p in PROFESSIONS:
    assert _p["section"] in _SECTION_SLUGS, f"{_p['slug']}: unknown section {_p['section']}"
assert len({p["slug"] for p in PROFESSIONS}) == len(PROFESSIONS), "duplicate profession slug"

# Every section must keep at least 2 leaves — a branch with one leaf forks
# nothing and just wastes a tree level.
_leaf_counts: dict[str, int] = {}
for _p in PROFESSIONS:
    _leaf_counts[_p["section"]] = _leaf_counts.get(_p["section"], 0) + 1
for _s in SECTIONS:
    assert _leaf_counts.get(_s["slug"], 0) >= 2, f"{_s['slug']}: needs >=2 leaves, has {_leaf_counts.get(_s['slug'], 0)}"


# ---------------------------------------------------------------------------
# 2. Age-group policy
#    junior  -> hypothesis space is SECTIONS (broad direction, soft wording)
#    middle  -> leaves, displayed via label_junior where set
#    senior  -> leaves, real names
#    `age_groups` filters what may be RETURNED as a result; the tree structure
#    itself is parent_id and is unaffected by this.
# ---------------------------------------------------------------------------

SECTION_AGE_GROUPS = ["junior"]
PROFESSION_AGE_GROUPS = ["middle", "senior"]


def compute_section_profiles() -> dict[str, dict[str, float]]:
    """Section profile = centroid (mean) of its leaves' profiles.

    Junior converges to sections, so sections need a profile or junior's belief
    can never move — that was the actual defect behind the earlier "open every
    profession to every age" patch. Near-zero axes are dropped to keep the
    vector sparse and readable; |mean| < 0.34 means the leaves disagree so much
    that the axis carries no branch-level signal.
    """
    by_section: dict[str, list[dict]] = {}
    for prof in PROFESSIONS:
        by_section.setdefault(prof["section"], []).append(prof["profile"])

    profiles: dict[str, dict[str, float]] = {}
    for slug, leaf_profiles in by_section.items():
        axes: set[str] = set()
        for leaf in leaf_profiles:
            axes |= leaf.keys()
        centroid = {
            axis: round(sum(leaf.get(axis, 0) for leaf in leaf_profiles) / len(leaf_profiles), 2)
            for axis in sorted(axes)
        }
        profiles[slug] = {a: v for a, v in centroid.items() if abs(v) >= 0.34}
    return profiles


# ---------------------------------------------------------------------------
# 3. Questions. `order` == q-number - 1 for the q01-q41 batch.
#
# resolves_pair is left null for three "разводит" notes that name a branch or
# a generic bucket rather than a specific profession pair — not silently
# guessed: q31 ("дизайн/иллюстрация vs сцена", branch-level), q37
# ("vs исполнительские роли", generic), q38 ("vs остальной бизнес", generic).
# Flagged for product review.
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
     ], "resolves_pair": ["emergency-physician", "physician", "surgeon"]},
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
         {"text": "тренировать животных, работать с ними в паре", "axis_weights": {"Dev": 2, "Motor": 1, "People": 1}},
     ], "resolves_pair": ["veterinarian", "zoologist", "ecologist", "agronomist", "cynologist"]},
    # Third option added (replacement pass) so building-systems-engineer, the
    # plumber replacement, has a fork that reaches it.
    {"order": 28, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Если проектировать — что ближе?", "text_junior": None,
     "options": [
         {"text": "механизмы, машины, устройства", "axis_weights": {"Phys": 2}},
         {"text": "здания, мосты, конструкции", "axis_weights": {"Phys": 2, "Struct": 2, "Lead": 1}},
         {"text": "инженерные системы зданий: вода, тепло, вентиляция", "axis_weights": {"Motor": 1, "Focus": 2, "Predict": -1}},
     ], "resolves_pair": ["mechanical-engineer", "civil-engineer", "building-systems-engineer"]},
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
    {"order": 32, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Работа со словами и текстами — что ближе?",
     "text_junior": "Тебе интереснее быстро узнавать новости и рассказывать, или спокойно сочинять и писать?",
     "options": [
         {"text": "быстро реагировать на события, узнавать новое, писать про это", "axis_weights": {"Pace": 2, "Predict": 2, "Obj": -2}},
         {"text": "спокойно и вдумчиво работать над текстом самому", "axis_weights": {"Focus": 2, "Auto": 2}},
     ], "resolves_pair": ["journalist", "translator"]},
    # Option 2 revived (replacement pass): hospitality-manager now exists, so
    # "общаться с гостями" reaches a leaf. Lead+2 added to aim at the manager
    # rather than at the retired waiter/barista.
    {"order": 34, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "На кухне или в кафе тебе ближе…",
     "text_junior": "Что интереснее: самому готовить вкусное или встречать гостей и управлять залом?",
     "options": [
         {"text": "готовить, придумывать блюда, творить со вкусом", "axis_weights": {"Inv": 1, "Motor": 2, "Ideas": 1}},
         {"text": "общаться с гостями, вести зал, отвечать за всё заведение", "axis_weights": {"People": 2, "Lead": 2, "Emp": 1, "Pace": 2}},
     ], "resolves_pair": ["head-chef", "confectionery-technologist", "hospitality-manager"]},
    {"order": 35, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Если готовить — что ближе?", "text_junior": None,
     "options": [
         {"text": "основные блюда, горячее, скорость кухни", "axis_weights": {"Pace": 2, "Lead": 1}},
         {"text": "десерты, выпечка, точность и красота", "axis_weights": {"Focus": 2, "Struct": 2, "Ideas": 2}},
     ], "resolves_pair": ["head-chef", "confectionery-technologist"]},
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
     ], "resolves_pair": ["fire-safety-engineer", "police-officer", "emergency-physician"]},
    # Revived (replacement pass): makeup-artist-film now exists, so this
    # question's weights reach a leaf again. Before the replacement it was a
    # dead question — hairdresser/makeup-artist had been retired and the
    # People/Motor/Ideas weights just leaked into fashion-designer and actor.
    {"order": 39, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Работать над внешним образом человека — тебе как?",
     "text_junior": None,
     "options": [
         {"text": "да: лицо, грим, образ — превращать человека в персонажа", "axis_weights": {"People": 2, "Motor": 2, "Emp": 1}},
         {"text": "ближе создавать вещи и одежду, а не работать с лицом", "axis_weights": {"Phys": 1, "Vis": 1}},
     ], "resolves_pair": ["makeup-artist-film", "fashion-designer"]},
    # --- Calibration pass additions (orders 41-44): resolves_pair gaps found
    # by auditing profile cosine-similarity — see module docstring.
    {"order": 41, "kind": "situational", "depth": 2, "age_variant": "senior",
     "text": "Если бы ты работал(а) в медицине каждый день, что подошло бы больше?",
     "text_junior": None,
     "options": [
         {"text": "точная, спокойная, повторяющаяся работа руками с одним и тем же типом процедур",
          "axis_weights": {"Motor": 2, "Struct": 2, "Risk": -1, "Pace": -1}},
         {"text": "непредсказуемые сложные случаи и высокие ставки",
          "axis_weights": {"Risk": 2, "Pace": 1, "PhysSt": 1}},
         {"text": "долгие беседы и наблюдение за развитием болезни у разных пациентов",
          "axis_weights": {"Focus": 1, "Predict": 1, "Emp": 1}},
         {"text": "лечить животных, а не только людей",
          "axis_weights": {"Living": 2, "Ideas": -1}},
         {"text": "постепенно восстанавливать подвижность и функции после травмы или болезни",
          "axis_weights": {"Dev": 2, "Motor": 1, "Acad": -1}},
     ], "resolves_pair": ["dentist", "surgeon", "physician", "veterinarian", "rehabilitation-therapist"]},
    {"order": 42, "kind": "direct", "depth": 2, "age_variant": "senior",
     "text": "Работать с психикой человека тебе ближе как?", "text_junior": None,
     "options": [
         {"text": "изучать биологию, работать как врач, при необходимости — лечить лекарствами",
          "axis_weights": {"Living": 2, "Care": 1}},
         {"text": "разговаривать, слушать и помогать разобраться в себе без медицинских препаратов",
          "axis_weights": {"Emp": 2, "Auto": 1}},
     ], "resolves_pair": ["psychiatrist", "psychologist"]},
    {"order": 43, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Работа врача тебе ближе как?",
     "text_junior": "Лечить людей интереснее спокойно и постоянно, или в срочных случаях?",
     "options": [
         {"text": "стабильно, в одном отделении, длительно наблюдать за одними и теми же пациентами",
          "axis_weights": {"Struct": 1, "Predict": -1}},
         {"text": "экстренные вызовы, непредсказуемая обстановка, скорая помощь",
          "axis_weights": {"Predict": 2, "Pace": 2, "Risk": 1}},
     ], "resolves_pair": ["physician", "emergency-physician"]},
    # --- Replacement pass additions (orders 45-49): every new profession needs
    # at least one fork that separates it from its nearest neighbour, otherwise
    # it is unreachable (the belief can never single it out).
    {"order": 45, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Продвигать компанию или товар — что тебе ближе?", "text_junior": None,
     "options": [
         {"text": "придумывать сообщение, тексты, образ бренда",
          "axis_weights": {"Ideas": 2, "Inv": 2, "Data": -1}},
         {"text": "считать, какая кампания сработала, разбирать цифры и аудиторию",
          "axis_weights": {"Data": 2, "Math": 1, "Obj": -1}},
     ], "resolves_pair": ["pr-specialist", "marketer"]},
    {"order": 46, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "На съёмочной площадке тебе ближе…", "text_junior": None,
     "options": [
         {"text": "решать, каким будет фильм целиком, и вести всю команду",
          "axis_weights": {"Lead": 2, "Inv": 2}},
         {"text": "работать с камерой и светом, строить кадр своими руками",
          "axis_weights": {"Motor": 2, "Exp": 2, "Vis": -1}},
     ], "resolves_pair": ["film-director", "cinematographer"]},
    {"order": 47, "kind": "situational", "depth": 3, "age_variant": "senior",
     "text": "Человек в трудной жизненной ситуации. Чем ты хочешь помочь?",
     "text_junior": None,
     "options": [
         {"text": "разобраться в его внутреннем мире — долго, глубоко, один на один",
          "axis_weights": {"Exp": 2, "Focus": 2, "Auto": 1}},
         {"text": "решить конкретные проблемы: жильё, документы, семья, куда обратиться",
          "axis_weights": {"Lead": 1, "Pace": 1, "Predict": 1, "Struct": 1}},
     ], "resolves_pair": ["psychologist", "social-worker"]},
    {"order": 48, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Работа с цифрами — что ближе?", "text_junior": None,
     "options": [
         {"text": "планировать движение товаров: маршруты, склады, поставки",
          "axis_weights": {"Obj": 1, "Lead": 1, "Pace": 1}},
         {"text": "точный учёт, отчётность, документы, чтобы всё сходилось",
          "axis_weights": {"Focus": 2, "Struct": 2, "Predict": -2, "Math": 2}},
     ], "resolves_pair": ["logistician", "accountant"]},
    {"order": 49, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Что хочется создавать?", "text_junior": None,
     "options": [
         {"text": "вещи, которые можно потрогать: мебель, предметы",
          "axis_weights": {"Phys": 2, "Motor": 1}},
         {"text": "картинки, экраны, айдентику — то, что живёт на плоскости",
          "axis_weights": {"Ideas": 2, "PhysSt": -1}},
         {"text": "здания и пространства, где ходят люди",
          "axis_weights": {"Phys": 1, "Struct": 2, "Lead": 1, "Acad": 1}},
     ], "resolves_pair": ["furniture-designer", "graphic-designer", "architect"]},
]

assert len(QUESTIONS) == 44, f"expected 47 questions, got {len(QUESTIONS)}"
assert len({q["order"] for q in QUESTIONS}) == len(QUESTIONS), "duplicate question order"

# Every slug named in a resolves_pair must actually exist as a leaf — this is
# what would have caught the dead order-39 question in the retirement pass.
_ALL_PROF_SLUGS = {p["slug"] for p in PROFESSIONS}
for _q in QUESTIONS:
    for _slug in _q["resolves_pair"] or []:
        assert _slug in _ALL_PROF_SLUGS, f"q order {_q['order']}: unknown slug {_slug!r} in resolves_pair"


# ---------------------------------------------------------------------------
# 4. Retired content — hard-deleted, not just dropped from the lists above,
#    so a re-run also cleans up rows a previous run already inserted.
# ---------------------------------------------------------------------------

RETIRED_DIRECTION_SLUGS: list[str] = [
    # professions with no university track (see "Retirement pass" above)
    "coach", "carpenter", "plumber", "photographer",
    "blogger-host", "copywriter", "tutor", "barista", "waiter",
    "hairdresser", "makeup-artist", "taxi-driver", "courier",
    "warehouse-worker", "sales-consultant",
    # University pass: СПО-tier professions whose university-level growth target
    # ALREADY exists as a leaf, so the lower tier is dropped rather than replaced:
    #   nurse               -> physician / surgeon
    #   auto-mechanic       -> mechanical-engineer
    #   construction-worker -> civil-engineer
    #   welder              -> mechanical-engineer (сварочное производство is a
    #                          профиль of Машиностроение)
    #   electrician         -> building-systems-engineer
    #   rescuer             -> fire-safety-engineer (same МЧС track as firefighter)
    #   athlete             -> sports-coach (a kid cannot enrol in "being an athlete";
    #                          the degree is Физическая культура -> тренер)
    #   fitness-instructor  -> sports-coach
    "nurse", "auto-mechanic", "construction-worker", "welder", "electrician",
    "rescuer", "athlete", "fitness-instructor",
    # replaced in place by their university-tier equivalent (new slug)
    "paramedic", "chef", "pastry-chef", "firefighter",
    # sections left with zero leaves once the professions above were cut
    "akinator-beauty-services", "akinator-logistics-service",
    "akinator-construction-manual",
]

# 22: disambiguated barista/waiter (both retired)
# 27: "починить руками vs спроектировать" — the hands-on tier it routed to
#     (auto-mechanic, electrician) is gone; Motor+2/Phys+2 would now leak into
#     surgeon/dentist/cinematographer, i.e. actively mis-route.
# 31: disambiguated photographer/blogger (both retired)
# 33: option 1 ("самому добиваться результата") pointed at athlete, now retired;
#     the remaining coach-vs-rehab fork is already covered by order 20.
# 40: disambiguated taxi/courier/warehouse (all retired)
# 44: disambiguated electrician/auto-mechanic (both retired)
RETIRED_QUESTION_ORDERS: list[int] = [22, 27, 31, 33, 40, 44]

# Nothing retired may still be referenced by a live question.
for _q in QUESTIONS:
    assert _q["order"] not in RETIRED_QUESTION_ORDERS, f"q order {_q['order']} is both live and retired"
    for _slug in _q["resolves_pair"] or []:
        assert _slug not in RETIRED_DIRECTION_SLUGS, f"q order {_q['order']} references retired {_slug!r}"


async def cleanup_retired_content(db: AsyncSession) -> tuple[int, int, int]:
    """Hard-delete retired Directions/questions and null out any assessment that
    had already selected a retired profession. Safe to re-run — a no-op once
    already clean. Returns (directions_deleted, questions_deleted, selections_cleared)."""
    # Clear dangling FK-by-slug references FIRST: a child who already got
    # "Фотограф" as their result would otherwise keep a slug pointing at a
    # deleted row, and the direction-roadmap would 500 on them.
    selections_cleared = (
        await db.execute(
            update(Assessment)
            .where(Assessment.selected_direction_slug.in_(RETIRED_DIRECTION_SLUGS))
            .values(selected_direction_slug=None)
        )
    ).rowcount or 0

    result = await db.execute(
        select(Direction).where(Direction.slug.in_(RETIRED_DIRECTION_SLUGS))
    )
    directions_deleted = 0
    for direction in result.scalars():
        await db.delete(direction)
        directions_deleted += 1

    result = await db.execute(
        select(AkinatorQuestion).where(AkinatorQuestion.order.in_(RETIRED_QUESTION_ORDERS))
    )
    questions_deleted = 0
    for question in result.scalars():
        await db.delete(question)
        questions_deleted += 1

    await db.flush()
    return directions_deleted, questions_deleted, selections_cleared


async def audit_unmanaged_leaves(db: AsyncSession) -> list[str]:
    """Report (do NOT delete) leaf Directions this script doesn't own that have
    an empty profile — e.g. the legacy `explore-*` placeholders. Belief can
    never move for them, so they sit in the hypothesis space as dead weight.
    Deleting them is a separate product/data decision, not a seed-script call."""
    known = {s["slug"] for s in SECTIONS} | {p["slug"] for p in PROFESSIONS}
    result = await db.execute(select(Direction).where(Direction.is_leaf.is_(True)))
    return sorted(
        d.slug for d in result.scalars() if d.slug not in known and not d.profile
    )


# ---------------------------------------------------------------------------
# 5. Idempotent upserts
# ---------------------------------------------------------------------------

async def seed_sections(db: AsyncSession) -> tuple[dict[str, uuid.UUID], int, int, int]:
    """Upsert the 13 branch Directions by slug. Returns (slug -> id, inserted, updated, skipped)."""
    section_profiles = compute_section_profiles()
    ids: dict[str, uuid.UUID] = {}
    inserted = updated = skipped = 0

    for section in SECTIONS:
        profile = section_profiles[section["slug"]]
        result = await db.execute(select(Direction).where(Direction.slug == section["slug"]))
        existing = result.scalar_one_or_none()

        if existing is not None:
            changed = False
            if existing.name != section["name"]:
                existing.name = section["name"]
                changed = True
            if existing.is_leaf is not False:
                existing.is_leaf = False
                changed = True
            if existing.profile != profile:
                existing.profile = profile
                changed = True
            if existing.age_groups != SECTION_AGE_GROUPS:
                existing.age_groups = SECTION_AGE_GROUPS
                changed = True
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
            is_leaf=False,
            profile=profile,
            age_groups=SECTION_AGE_GROUPS,
        )
        db.add(direction)
        await db.flush()
        ids[section["slug"]] = direction.id
        inserted += 1

    return ids, inserted, updated, skipped


async def seed_professions(
    db: AsyncSession, section_ids: dict[str, uuid.UUID]
) -> tuple[int, int, int]:
    """Upsert the 51 leaf Directions by slug. Returns (inserted, updated, skipped)."""
    inserted = updated = skipped = 0

    for prof in PROFESSIONS:
        parent_id = section_ids[prof["section"]]
        label_junior = prof.get("label_junior")
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
            if existing.age_groups != PROFESSION_AGE_GROUPS:
                existing.age_groups = PROFESSION_AGE_GROUPS
                changed = True
            if existing.label_junior != label_junior:
                existing.label_junior = label_junior
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
            parent_id=parent_id,
            is_leaf=True,
            profile=prof["profile"],
            age_groups=PROFESSION_AGE_GROUPS,
            label_junior=label_junior,
        )
        db.add(direction)
        inserted += 1

    return inserted, updated, skipped


async def seed_questions(db: AsyncSession) -> tuple[int, int, int]:
    """Upsert the 44 AkinatorQuestion rows by `order` (this script owns 0-49,
    minus the retired orders — see RETIRED_QUESTION_ORDERS).
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
        dirs_deleted, qs_deleted, sel_cleared = await cleanup_retired_content(db)
        section_ids, sec_ins, sec_upd, sec_skip = await seed_sections(db)
        prof_ins, prof_upd, prof_skip = await seed_professions(db, section_ids)
        q_ins, q_upd, q_skip = await seed_questions(db)
        orphans = await audit_unmanaged_leaves(db)
        await db.commit()

        print(
            f"Retired:     {dirs_deleted} direction(s), {qs_deleted} question(s) deleted, "
            f"{sel_cleared} assessment selection(s) cleared"
        )
        print(
            f"Sections:    inserted {sec_ins}, updated {sec_upd}, skipped {sec_skip} "
            f"(total {len(SECTIONS)}, age_groups={SECTION_AGE_GROUPS})"
        )
        print(
            f"Professions: inserted {prof_ins}, updated {prof_upd}, skipped {prof_skip} "
            f"(total {len(PROFESSIONS)}, age_groups={PROFESSION_AGE_GROUPS})"
        )
        print(
            f"Questions:   inserted {q_ins}, updated {q_upd}, skipped {q_skip} "
            f"(total {len(QUESTIONS)})"
        )
        if orphans:
            print(
                f"\nWARNING: {len(orphans)} unmanaged leaf Direction(s) with an empty "
                f"profile are still in the hypothesis space — belief can never move "
                f"for them. Not deleted by this script; decide and clean separately:"
            )
            for slug in orphans:
                print(f"  - {slug}")


if __name__ == "__main__":
    asyncio.run(main())
