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

Specialty pivot (2026-07-17): the leaf level of the tree is no longer 51 narrow
PROFESSIONS but ~38 SPECIALTIES matching real Kazakhstani bachelor's programs
(e.g. "Software Engineer" instead of "Программист"). Professions that share one
accredited program (e.g. surgeon+physician+emergency-physician+psychiatrist, all
"Лечебное дело" — sub-specialization happens later, in ординатура) merge into one
specialty; professions that are genuinely distinct accredited programs stay
separate. Each specialty leaf now populates `Direction.professions` (already
existed, previously only used inside the AI roadmap prompt) with the concrete
job titles it leads to — this is what the client now shows under the matched
specialty. `ux-designer` moves from akinator-it-data to akinator-creative-design
(its axis profile is closer to design than to programming). No belief-walk
engine changes were needed: it already operates generically over any
`is_leaf=True` Direction row via `profile`, independent of what the leaf
represents.

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
from SPECIALTY_AGE_GROUPS to SECTION_AGE_GROUPS — single-constant change.

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
    {"slug": "akinator-medicine", "name": "Медицина и здоровье",
     "description": "Профессии, которые лечат и заботятся о здоровье людей: от постановки диагноза до операций и восстановления после болезни."},
    {"slug": "akinator-psychology-help", "name": "Помощь и психология",
     "description": "Профессии, которые поддерживают людей в трудных ситуациях: помогают разобраться в себе, отношениях и жизненных сложностях."},
    {"slug": "akinator-animals-nature", "name": "Животные и природа",
     "description": "Профессии, связанные с животными, растениями и живой природой — от лечения питомцев до заботы об экосистемах."},
    {"slug": "akinator-it-data", "name": "IT и данные",
     "description": "Профессии, которые создают программы, анализируют данные и поддерживают работу компьютеров и сервисов."},
    {"slug": "akinator-engineering-tech", "name": "Инженерия и техника",
     "description": "Профессии, которые проектируют и строят технику, здания и инженерные системы."},
    {"slug": "akinator-creative-design", "name": "Творчество и дизайн",
     "description": "Профессии, которые создают визуальные образы, вещи и пространства — от иллюстраций до архитектуры."},
    {"slug": "akinator-stage-media", "name": "Сцена и медиа",
     "description": "Профессии, связанные с актёрским мастерством, музыкой, кино и публичными выступлениями."},
    {"slug": "akinator-words-communication", "name": "Слово и коммуникация",
     "description": "Профессии, которые работают с текстом, языком и убеждением: от журналистики до юриспруденции."},
    {"slug": "akinator-education", "name": "Образование",
     "description": "Профессии, которые учат и растят детей и подростков."},
    {"slug": "akinator-sports-body", "name": "Спорт и тело",
     "description": "Профессии, связанные с физической активностью, тренировками и восстановлением тела."},
    {"slug": "akinator-food-hospitality", "name": "Еда и гостеприимство",
     "description": "Профессии на кухне и в сфере гостеприимства — от приготовления блюд до управления рестораном."},
    {"slug": "akinator-business-sales", "name": "Бизнес и продажи",
     "description": "Профессии, связанные с продажами, управлением и предпринимательством."},
    {"slug": "akinator-safety-rescue", "name": "Безопасность и спасение",
     "description": "Профессии, которые обеспечивают безопасность людей и реагируют в чрезвычайных ситуациях."},
]

SPECIALTIES: list[dict] = [
    # Медицина и здоровье
    # Merge (specialty pivot): surgeon+physician+emergency-physician+psychiatrist
    # all grow from ONE accredited bachelor's — «Лечебное дело» / Общая медицина.
    # Sub-specialization happens later, in ординатура, not at enrollment — so
    # these no longer fork the akinator, they fork the residency choice.
    {"slug": "general-medicine", "name": "Лечебное дело", "label_junior": "Врач", "section": "akinator-medicine",
     "description": "Лечебное дело готовит врачей широкого профиля — терапевтов, хирургов, врачей скорой помощи и психиатров. Конкретная специализация выбирается позже, в ординатуре, а не при поступлении.",
     "profile": {"People": 2, "Living": 2, "Phys": 1, "Care": 2, "Motor": 1, "Exp": 2, "Focus": 1, "Risk": 1, "Struct": 1, "Pace": 1, "Acad": 2, "PhysSt": 1, "Emp": 1, "Predict": 1},
     "professions": ["Терапевт", "Хирург", "Врач скорой помощи", "Психиатр", "Кардиолог", "Педиатр"]},
    {"slug": "dentist", "name": "Стоматология", "label_junior": "Зубной врач", "section": "akinator-medicine",
     "description": "Стоматология лечит зубы и полость рта — точная, кропотливая работа руками, требующая аккуратности и внимания к деталям.",
     "profile": {"People": 1, "Living": 2, "Phys": 1, "Care": 2, "Motor": 2, "Exp": 2, "Focus": 2, "Struct": 1, "Acad": 2},
     "professions": ["Стоматолог-терапевт", "Стоматолог-хирург", "Ортодонт", "Детский стоматолог"]},
    {"slug": "pharmacist", "name": "Фармация", "label_junior": "Аптекарь", "section": "akinator-medicine",
     "description": "Фармация готовит специалистов, которые разбираются в лекарствах — помогают подобрать нужный препарат и объясняют, как его правильно принимать.",
     "profile": {"People": 1, "Living": 1, "Data": 1, "Care": 1, "Exp": 2, "Focus": 1, "Struct": 2, "Predict": -1, "Acad": 1, "Math": 1},
     "professions": ["Фармацевт", "Провизор", "Технолог фармацевтического производства"]},

    # Помощь и психология — три разных диплома, компрессии нет
    {"slug": "psychologist", "name": "Психология", "section": "akinator-psychology-help",
     "description": "Психология учит понимать мысли, чувства и отношения — работать с человеком через разговор, глубоко вникая в его историю.",
     # Auto:1, Ideas:1 removed (calibration playtest pass, 2026-07, round 6):
     # neither is central to being a psychologist, but both were incidental
     # overlap with unrelated ±2-weighted resolver options ("рискну, придумаю
     # своё дело" Auto:2; "создавать красивое" / "придумывать сообщение,
     # тексты" Ideas:2) that kept dragging traced sessions toward
     # film-director/makeup-artist-film/pr-specialist before this profile's
     # own dedicated resolvers (order 19, 42, 47) got a fair chance. The
     # profile's real signature (People/Care/Emp/Exp/Focus/Acad, all still
     # at magnitude 2) is untouched.
     "profile": {"People": 2, "Care": 2, "Emp": 2, "Exp": 2, "Focus": 2, "Motiv": -1, "Acad": 2, "Data": -1},
     "professions": ["Психолог", "Клинический психолог", "Коуч"]},
    {"slug": "speech-therapist", "name": "Логопедия и дефектология", "label_junior": "Логопед", "section": "akinator-psychology-help",
     "description": "Логопедия и дефектология учат помогать детям и взрослым с речевыми и развивающими нарушениями — через регулярные занятия и коррекционные методики.",
     "profile": {"People": 2, "Care": 1, "Dev": 2, "Emp": 1, "Exp": 2, "Focus": 1, "Struct": 1, "Acad": 1},
     "professions": ["Логопед", "Дефектолог", "Специалист по коррекционной педагогике"]},
    {"slug": "social-worker", "name": "Социальная работа", "section": "akinator-psychology-help",
     "description": "Социальная работа готовит специалистов, которые помогают семьям и людям в трудной жизненной ситуации — организуют поддержку и решают практические проблемы.",
     "profile": {"People": 2, "Care": 2, "Emp": 2, "Lead": 1, "Struct": 1, "Motiv": -1, "Pace": 1, "Predict": 1, "Acad": 1},
     "professions": ["Социальный работник", "Социальный педагог", "Специалист по соцзащите"]},

    # Животные и природа
    # Merge (specialty pivot): veterinarian+cynologist — KazATU runs both under
    # one faculty (ветеринарии и технологии животноводства).
    {"slug": "veterinary-zootechnics", "name": "Ветеринария и зоотехния", "label_junior": "Специалист по животным", "section": "akinator-animals-nature",
     "description": "Ветеринария и зоотехния объединяет лечение животных и уход за ними — от домашних питомцев до служебных собак и крупного скота.",
     "profile": {"People": 1, "Living": 2, "Phys": 1, "Care": 2, "Motor": 1, "Dev": 1, "Exp": 2, "Focus": 1, "Struct": 1, "Acad": 2, "PhysSt": 1},
     "professions": ["Ветеринар", "Зоотехник", "Кинолог"]},
    {"slug": "agronomist", "name": "Агрономия", "label_junior": "Специалист по растениям", "section": "akinator-animals-nature",
     "description": "Агрономия готовит специалистов по выращиванию растений — подбору условий, удобрений и ухода для здорового и обильного урожая.",
     "profile": {"Living": 2, "Phys": 1, "Data": 1, "Exp": 1, "Struct": 1, "Predict": -1, "PhysSt": 1},
     "professions": ["Агроном", "Агроинженер", "Специалист по растениеводству"]},
    {"slug": "zoologist", "name": "Биология и зоология", "label_junior": "Учёный по животным", "section": "akinator-animals-nature",
     "description": "Биология и зоология изучают животных и их поведение — наблюдение, исследование и описание жизни дикой природы.",
     "profile": {"Living": 2, "Data": 1, "Obj": -2, "Exp": 2, "Focus": 2, "Auto": 1, "Predict": 1, "Acad": 2, "People": -1, "PhysSt": 1},
     "professions": ["Зоолог", "Биолог-исследователь"]},
    {"slug": "ecologist", "name": "Экология и природопользование", "section": "akinator-animals-nature",
     "description": "Экология и природопользование изучают, как человек влияет на природу, и ищут способы защитить экосистемы и снизить вред окружающей среде.",
     "profile": {"Living": 2, "Data": 1, "Ideas": 1, "Obj": -2, "Exp": 1, "Auto": 1, "Predict": 1, "Acad": 1},
     "professions": ["Эколог", "Специалист по экомониторингу", "Специалист по устойчивому развитию"]},

    # IT и данные (ux-designer перенесён в «Творчество и дизайн» — по осям
    # профиля Ideas/Inv он ближе к дизайну, чем к программированию/данным)
    # Merge (specialty pivot): programmer+qa-tester — QA is a career track
    # within the same accredited "Программная инженерия" degree, not its own code.
    {"slug": "software-engineer", "name": "Software Engineer", "label_junior": "Разработчик программ", "section": "akinator-it-data",
     "description": "Software Engineer создаёт программы, сайты и приложения — от логики на сервере до интерфейса пользователя. Внутри специальности можно расти в разных направлениях: backend, frontend, мобильная разработка или тестирование.",
     # Focus 2->1 (calibration playtest pass, 2026-07, round 11): same fix
     # already applied to finance-accounting — after that trim, traced
     # data-science sessions showed software-engineer stepping into
     # finance-accounting's old role as the #1 rival, via the exact same
     # mechanism (order=48's Math/Focus/Struct option scores high for
     # software-engineer too, even though that resolver isn't its pair).
     # Its own resolver (order 51, Inv/Obj/Ideas) doesn't touch Focus, so
     # this doesn't weaken its genuine identification there.
     "profile": {"People": -1, "Living": -1, "Data": 2, "Ideas": 1, "Inv": 1, "Obj": 1, "Care": -1, "Dev": -1, "Exp": 2, "Focus": 1, "Auto": 1, "Struct": 2, "Acad": 1, "PhysSt": -2, "Math": 2, "Predict": -1},
     "professions": ["Backend-разработчик", "Frontend-разработчик", "Fullstack-разработчик", "Мобильный разработчик", "QA-инженер"]},
    {"slug": "data-science", "name": "Data Science", "label_junior": "Аналитик", "section": "akinator-it-data",
     "description": "Data Science находит закономерности в больших массивах данных и помогает бизнесу принимать решения — от аналитики до машинного обучения.",
     # Struct:1 removal reverted (calibration playtest pass, 2026-07, round 6
     # follow-up): tried removing it to cut overlap with finance-accounting,
     # but census got WORSE (27%->13%) — match_score divides by the
     # profile's own norm, so removing an axis SHRINKS the norm and makes
     # every remaining axis (including the bad Focus/Math overlap with
     # finance-accounting) score relatively *stronger*, not weaker. Restored.
     "profile": {"People": -1, "Living": -2, "Data": 2, "Obj": -2, "Care": -2, "Dev": -2, "Exp": 1, "Focus": 2, "Auto": 1, "Struct": 1, "Predict": -1, "Acad": 1, "PhysSt": -2, "Math": 2},
     "professions": ["Аналитик данных", "Data Scientist", "BI-аналитик", "ML-инженер"]},
    {"slug": "it-infrastructure-security", "name": "Кибербезопасность и IT-инфраструктура", "label_junior": "Компьютерный мастер", "section": "akinator-it-data",
     "description": "Кибербезопасность и IT-инфраструктура следят, чтобы компьютеры, сети и данные компании работали без сбоев и были защищены от угроз.",
     "profile": {"Phys": 1, "Data": 2, "Obj": 1, "Exp": 2, "Focus": -1, "Auto": 1, "Struct": 1, "Pace": 1, "Predict": 1, "PhysSt": -1, "Math": 1, "People": -1},
     "professions": ["Системный администратор", "Сетевой инженер", "Специалист по кибербезопасности"]},

    # Инженерия и техника
    {"slug": "mechanical-engineer", "name": "Машиностроение", "label_junior": "Инженер", "section": "akinator-engineering-tech",
     "description": "Машиностроение проектирует машины и механизмы — от отдельных деталей до целых устройств, — рассчитывая, как они будут работать.",
     "profile": {"Phys": 2, "Data": 1, "Ideas": 1, "Inv": 1, "Obj": 2, "Exp": 2, "Focus": 1, "Struct": 1, "Acad": 2, "Math": 2, "People": -1},
     "professions": ["Инженер-механик", "Инженер-конструктор", "Инженер по автоматизации"]},
    # Merge (specialty pivot): civil-engineer+building-systems-engineer — ТГВ
    # is a профиль within «Строительство», not a separate accredited code.
    {"slug": "civil-engineering", "name": "Строительство и инженерные системы", "label_junior": "Инженер", "section": "akinator-engineering-tech",
     "description": "Строительство и инженерные системы проектируют здания, сооружения и их инженерные системы — отопление, вентиляцию и водоснабжение, — рассчитывая прочность и надёжность.",
     "profile": {"Phys": 2, "Data": 1, "Obj": 2, "Lead": 1, "Exp": 2, "Focus": 2, "Struct": 2, "Risk": -1, "Acad": 2, "Math": 2, "Motor": 1, "Predict": -1, "People": -1},
     "professions": ["Инженер-строитель", "Инженер инженерных систем", "Инженер-проектировщик"]},
    {"slug": "pilot", "name": "Лётная эксплуатация", "section": "akinator-engineering-tech",
     "description": "Лётная эксплуатация готовит пилотов и специалистов управления воздушным движением — работа требует быстрой реакции, хладнокровия и точного следования процедурам.",
     # Inv:-1, Care:-1 added (calibration playtest pass, 2026-07, round 3):
     # 11 axes, all non-negative, meant no answer could ever count AGAINST
     # this profile — a census + traced-session pass found it winning far
     # outside its own domain (mechanical-engineer, data-science, lawyer,
     # speech-therapist, hospitality-manager sessions all ended up here).
     # Both additions are grounded in the profile's own description:
     # "точное следование процедурам" is the literal opposite of Inv
     # (inventing from scratch), and the job has no individual-care
     # component (Care) the way medicine/therapy professions do.
     "profile": {"Phys": 1, "Data": 1, "Lead": 1, "Motor": 1, "Exp": 2, "Focus": 2, "Risk": 1, "Struct": 2, "Pace": 1, "Acad": 1, "Math": 1, "Inv": -1, "Care": -1},
     "professions": ["Пилот", "Штурман", "Диспетчер УВД"]},

    # Творчество и дизайн
    # Merge (specialty pivot): graphic-designer+illustrator+fashion-designer+
    # furniture-designer+ux-designer — in KZ «Дизайн» is ONE accredited code
    # with профили (графика/мода/интерьер/UX) chosen after enrollment.
    # architect keeps its own accredited code, stays separate.
    {"slug": "design", "name": "Дизайн", "label_junior": "Дизайнер", "section": "akinator-creative-design",
     "description": "Дизайн создаёт визуальные образы, вещи и пространства — от логотипов и иллюстраций до одежды, мебели и цифровых интерфейсов.",
     # Vis:-1, People:-1 added (calibration playtest pass, 2026-07, round 5):
     # after film-director was reined in (round 4), belief that used to land
     # there started landing here instead — musician, actor, cinematographer,
     # pr-specialist sessions all drifted to design via shared Ideas/Inv.
     # Vis is the actual axis that separates "makes things" from "performs/
     # is seen" (see axes.py "Быть на виду, выступать") and design never
     # carried it either way; People:-1 reinforces that this profile works
     # on objects/visuals, not people directly.
     "profile": {"Ideas": 2, "Inv": 2, "Obj": 1, "Exp": 1, "Auto": 1, "Struct": -1, "PhysSt": -1, "Motor": 1, "Phys": 1, "Vis": -1, "People": -1},
     "professions": ["Графический дизайнер", "Иллюстратор", "UX/UI-дизайнер", "Модельер", "Дизайнер мебели"]},
    {"slug": "architect", "name": "Архитектура", "section": "akinator-creative-design",
     "description": "Архитектура проектирует здания и пространства, соединяя эстетику с инженерными расчётами.",
     # Care:-1 added (calibration playtest pass, 2026-07, round 9): already
     # the loudest profile in the catalog (6 axes at magnitude 2) with only
     # one negative — a repeat rival for translator/speech-therapist/
     # data-science in traced sessions via shared Focus/Struct/Exp/Acad.
     # Architecture works on buildings/spaces, not directly caring for
     # people — keeps it from picking up stray belief on generic
     # "помогать людям" style questions the way its Focus/Struct/Exp
     # overlap otherwise lets it.
     "profile": {"People": 1, "Phys": 1, "Data": 1, "Ideas": 2, "Inv": 2, "Obj": 1, "Lead": 1, "Exp": 2, "Focus": 2, "Struct": 2, "Auto": 1, "Acad": 2, "Math": 1, "PhysSt": -1, "Care": -1},
     "professions": ["Архитектор", "Ландшафтный архитектор", "Архитектор интерьеров"]},

    # Сцена и медиа — все аккредитованные программы творческих вузов различны,
    # компрессии нет даже при агрессивной группировке
    {"slug": "actor", "name": "Актёрское искусство", "section": "akinator-stage-media",
     "description": "Актёрское искусство готовит к работе на сцене, в кино и на телевидении — воплощению ролей, требующему эмоциональной открытости и умения держаться перед публикой.",
     "profile": {"People": 1, "Ideas": 2, "Vis": 2, "Emp": 1, "Motor": 1, "Risk": 1, "Struct": -1, "Auto": -1, "Predict": 1, "PhysSt": 1, "Math": -1, "Data": -1},
     "professions": ["Актёр театра", "Актёр кино", "Актёр озвучивания"]},
    {"slug": "musician", "name": "Музыкальное искусство", "section": "akinator-stage-media",
     "description": "Музыкальное искусство учит сочинять и исполнять музыку — на сцене, в студии или в составе оркестра.",
     "profile": {"Ideas": 2, "Vis": 1, "Motor": 2, "Exp": 2, "Focus": 2, "Auto": 1, "Risk": 1, "Struct": -1},
     "professions": ["Музыкант-исполнитель", "Композитор", "Звукорежиссёр"]},
    {"slug": "film-director", "name": "Режиссура", "section": "akinator-stage-media",
     "description": "Режиссура учит придумывать, как будет выглядеть фильм или спектакль, и руководить творческой командой.",
     # Data:-1, Motor:-1 added (calibration playtest pass, 2026-07, round 3):
     # Ideas/Inv/Lead alone made this the default landing spot for almost any
     # "creative or leadership" answer (design, marketing, journalist,
     # architect, police-officer sessions all drifted here). Not about
     # crunching numbers (Data — contrast finance-accounting/data-science),
     # and directing the shot vs personally operating camera/light is
     # exactly the split order=46 already draws against cinematographer
     # (Motor:2 there) — this profile just never carried the negative side
     # of that same fork.
     "profile": {"People": 1, "Ideas": 2, "Inv": 2, "Lead": 2, "Exp": 1, "Focus": 1, "Risk": 1, "Auto": 1, "Struct": -1, "Data": -1, "Motor": -1},
     "professions": ["Режиссёр кино", "Режиссёр театра", "Режиссёр монтажа"]},
    {"slug": "cinematographer", "name": "Операторское искусство", "label_junior": "Оператор кино", "section": "akinator-stage-media",
     "description": "Операторское искусство отвечает за то, как выглядит каждый кадр — свет, ракурс и движение камеры.",
     "profile": {"Phys": 1, "Ideas": 2, "Inv": 1, "Vis": -1, "Motor": 2, "Exp": 2, "Focus": 2, "Auto": 1, "Acad": 1, "PhysSt": 1},
     "professions": ["Кинооператор", "Фотограф", "Видеооператор"]},
    {"slug": "makeup-artist-film", "name": "Грим и художественный образ", "label_junior": "Гримёр", "section": "akinator-stage-media",
     "description": "Грим и художественный образ создают образы актёров с помощью грима, причёсок и костюмов — для кино, театра и телевидения.",
     "profile": {"People": 2, "Ideas": 2, "Inv": 2, "Motor": 2, "Emp": 1, "Exp": 1, "Vis": -1, "Auto": 1, "Acad": 1},
     "professions": ["Художник-гримёр", "Визажист кино и театра", "Художник по костюмам"]},

    # Слово и коммуникация — 4 разных аккредитованных программы, без изменений
    {"slug": "journalist", "name": "Журналистика", "section": "akinator-words-communication",
     "description": "Журналистика учит находить, проверять и рассказывать истории — держать людей в курсе того, что происходит в мире.",
     "profile": {"People": 1, "Ideas": 1, "Obj": -2, "Vis": 1, "Exp": 1, "Emp": 1, "Risk": 1, "Pace": 2, "Predict": 2, "Acad": 1, "Struct": -1},
     "professions": ["Журналист", "Репортёр", "Блогер-журналист"]},
    {"slug": "translator", "name": "Переводческое дело", "section": "akinator-words-communication",
     "description": "Переводческое дело учит передавать смысл текста или речи с одного языка на другой, сохраняя точность и стиль.",
     # Motor:-1 addition reverted (calibration playtest pass, 2026-07, round 7
     # follow-up): the direct match_score math checked out (should have cut
     # translator's score on cinematographer's own resolver option roughly in
     # half), but the actual census got worse (37-43%->17%), while
     # school-teacher — untouched this round — swung 60%->43% in the same
     # run. That's within the sampling-noise band already measured (two
     # identical-code reruns earlier landed 5-13pp apart on several
     # professions), so this single run isn't reliable evidence the edit
     # backfired; reverted pending a cleaner (multi-run) test rather than
     # keep an unverified change.
     #
     # Math:-1 added (calibration playtest pass, 2026-07, round 9): unlike
     # the reverted Motor edit, this targets translator's most fundamental
     # divide from data-science (its main rival after round 8) — translation
     # is not a numbers domain at all, while data-science's whole identity is
     # Math:2. No existing question or resolver relied on translator scoring
     # neutral (0) on Math, so this only ever pushes it further from
     # data-science/finance-accounting/software-engineer, never against its
     # own resolver (order 32, which doesn't touch Math).
     "profile": {"Ideas": 1, "Obj": -1, "Exp": 2, "Focus": 2, "Auto": 2, "Struct": 1, "Predict": -1, "Acad": 1, "People": -1, "Math": -1},
     "professions": ["Переводчик", "Устный переводчик", "Локализатор"]},
    {"slug": "lawyer", "name": "Юриспруденция", "section": "akinator-words-communication",
     "description": "Юриспруденция учит разбираться в законах и защищать интересы людей и компаний — в судах, договорах и переговорах.",
     # Math:-1, Inv:-1 added (calibration playtest pass, 2026-07, round 9):
     # missed in the earlier zero-negative-axis audit (round 4) — 9 axes, all
     # non-negative, a repeat rival for data-science and speech-therapist in
     # traced sessions. Not about advanced math (distinguishes from
     # data-science/finance-accounting/software-engineer) and not about
     # inventing new frameworks from scratch — law is applying existing
     # rules, not creating them (distinguishes from the design/IT cluster
     # that shares Inv:2).
     "profile": {"People": 1, "Data": 1, "Obj": -1, "Lead": 1, "Vis": 1, "Exp": 2, "Focus": 2, "Struct": 2, "Acad": 2, "Math": -1, "Inv": -1},
     "professions": ["Юрист", "Адвокат", "Юрисконсульт"]},
    {"slug": "pr-specialist", "name": "Реклама и связи с общественностью", "label_junior": "Специалист по рекламе", "section": "akinator-words-communication",
     "description": "Реклама и связи с общественностью учат рассказывать о компании или продукте так, чтобы это заметили и запомнили.",
     "profile": {"People": 1, "Ideas": 2, "Inv": 2, "Vis": 1, "Emp": 1, "Exp": 1, "Focus": 1, "Auto": 1, "Struct": -1, "Data": -1, "Math": -1, "Acad": 1},
     "professions": ["PR-специалист", "Копирайтер", "Бренд-менеджер"]},

    # Образование — уже на минимуме (2 листа), не сжимаем
    {"slug": "school-teacher", "name": "Педагогическое образование", "label_junior": "Учитель", "section": "akinator-education",
     "description": "Педагогическое образование готовит учителей, которые объясняют школьный материал и помогают ученикам разобраться в предмете.",
     "profile": {"People": 2, "Dev": 2, "Care": 1, "Lead": 1, "Vis": 1, "Exp": 1, "Emp": 1, "Focus": -1, "Struct": 1, "Acad": 1},
     "professions": ["Учитель-предметник", "Классный руководитель", "Методист"]},
    {"slug": "kindergarten-teacher", "name": "Дошкольное образование", "label_junior": "Воспитатель", "section": "akinator-education",
     "description": "Дошкольное образование готовит воспитателей, которые заботятся о детях дошкольного возраста — организуют игры, занятия и распорядок дня.",
     "profile": {"People": 2, "Care": 2, "Dev": 1, "Emp": 2, "Focus": -1, "Struct": 1, "Pace": 1, "PhysSt": 1},
     "professions": ["Воспитатель", "Педагог дошкольного образования"]},

    # Спорт и тело — уже на минимуме (2 листа), не сжимаем
    {"slug": "sports-coach", "name": "Физическая культура и спорт", "label_junior": "Тренер", "section": "akinator-sports-body",
     "description": "Физическая культура и спорт учат технике вида спорта и мотивации спортсменов на результат.",
     "profile": {"People": 1, "Living": 1, "Dev": 2, "Care": 1, "Lead": 1, "Motor": 1, "Emp": 1, "Motiv": 2, "Pace": 1, "PhysSt": 1, "Exp": 1},
     "professions": ["Спортивный тренер", "Инструктор фитнеса", "Тренер-преподаватель"]},
    {"slug": "rehabilitation-therapist", "name": "Реабилитология", "label_junior": "Врач по восстановлению", "section": "akinator-sports-body",
     "description": "Реабилитология помогает восстанавливать подвижность тела после травм и операций с помощью упражнений и процедур.",
     "profile": {"People": 1, "Living": 2, "Care": 2, "Dev": 1, "Motor": 1, "Exp": 2, "Emp": 1, "Focus": 1, "Struct": 1, "Acad": 1, "PhysSt": 1},
     "professions": ["Реабилитолог", "Специалист по адаптивной физкультуре", "Врач ЛФК"]},

    # Еда и гостеприимство
    # Merge (specialty pivot): head-chef+confectionery-technologist share one
    # accredited code — «Технология продукции общественного питания».
    {"slug": "food-production-tech", "name": "Технология продукции общественного питания", "label_junior": "Повар", "section": "akinator-food-hospitality",
     "description": "Технология продукции общественного питания учит придумывать блюда и десерты и управлять процессом их приготовления — от горячих блюд до выпечки.",
     # Math:-1, People:-1 added (calibration playtest pass, 2026-07, round 5):
     # already the broadest profile in the catalog (14 axes, only 1
     # negative) — after round 4 softened pilot/hospitality-manager/
     # management-entrepreneurship/film-director, belief that used to land
     # there started landing here instead (mechanical-engineer, actor,
     # translator, it-infrastructure-security sessions all drifted to this
     # profile via shared Ideas/Inv/Motor/Struct). Not about advanced math
     # (Math — separates it from the mechanical-engineer/finance-accounting/
     # data-science cluster it was absorbing), and the dish/product is the
     # focus, not the guest directly (People — that's hospitality-manager's
     # side of the existing order=34 fork, this profile just never carried
     # the negative half of it).
     "profile": {"Phys": 1, "Data": 1, "Ideas": 2, "Inv": 2, "Obj": 1, "Motor": 2, "Lead": 1, "Focus": 1, "Struct": 2, "Pace": 1, "PhysSt": 1, "Acad": 1, "Exp": 1, "Predict": -1, "Math": -1, "People": -1},
     "professions": ["Шеф-повар", "Кондитер-технолог", "Технолог пищевого производства"]},
    {"slug": "hospitality-manager", "name": "Ресторанное и гостиничное дело", "label_junior": "Управляющий кафе", "section": "akinator-food-hospitality",
     "description": "Ресторанное и гостиничное дело организует работу кафе, ресторана или отеля — от персонала до атмосферы для гостей.",
     # Exp:-1, Focus:-1 added (calibration playtest pass, 2026-07, round 3):
     # 11 axes, all non-negative — a generalist coordinator profile that no
     # answer could ever count against, and a repeat winner for unrelated
     # sessions (school-teacher, fire-safety-engineer, police-officer,
     # kindergarten-teacher all drifted here). Not a narrow deep specialist
     # (Exp — the job is breadth across staff/guests/operations, not depth
     # in one thing) and not built around long solo focus (Focus — it's
     # event-paced, constantly interrupted by guests/staff, the opposite of
     # e.g. finance-accounting's Focus:2).
     "profile": {"People": 2, "Data": 1, "Lead": 2, "Emp": 1, "Motiv": 1, "Risk": 1, "Struct": 1, "Pace": 2, "Predict": 1, "PhysSt": 1, "Acad": 1, "Exp": -1, "Focus": -1},
     "professions": ["Менеджер ресторанного дела", "Менеджер отеля", "Ивент-менеджер"]},

    # Бизнес и продажи
    # Merge (specialty pivot): sales-manager+entrepreneur+logistician share one
    # broad accredited code — «Менеджмент». marketer/accountant stay separate
    # (Маркетинг / Учёт и аудит-Финансы are distinct codes).
    {"slug": "management-entrepreneurship", "name": "Менеджмент и предпринимательство", "label_junior": "Бизнесмен", "section": "akinator-business-sales",
     "description": "Менеджмент и предпринимательство готовят к управлению людьми, продажами, логистикой и собственным делом.",
     # Exp:-1, Struct:-1 added (calibration playtest pass, 2026-07, round 3):
     # 11 axes, all non-negative — another repeat winner outside its own
     # domain (marketing, school-teacher, fire-safety-engineer, social-worker
     # sessions all drifted here). Not a narrow deep specialist (Exp — this
     # is breadth across a business, not depth in one field), and running
     # your own thing means working in ambiguity, not rigid procedure
     # (Struct — the literal opposite end from e.g. finance-accounting's
     # Struct:2 or civil-engineering's Struct:2).
     "profile": {"People": 1, "Emp": 1, "Vis": 1, "Motiv": 1, "Risk": 1, "Auto": 1, "Predict": 1, "Pace": 1, "Inv": 1, "Lead": 1, "Data": 1, "Exp": -1, "Struct": -1},
     "professions": ["Менеджер по продажам", "Предприниматель", "Логист", "Менеджер проектов"]},
    {"slug": "marketing", "name": "Маркетинг", "label_junior": "Специалист по рекламе", "section": "akinator-business-sales",
     "description": "Маркетинг учит продумывать, как рассказать о продукте так, чтобы его захотели купить — анализировать рынок и запускать рекламные кампании.",
     # Ideas 1->2, Vis 1->2 (calibration playtest pass, 2026-07, round 6): this
     # was the only profile in the whole catalog with zero axes at magnitude
     # 2 — every trait capped at ±1, so it could never win a contested
     # question against ANY resolver written for a different pair (those
     # always carry at least one ±2 weight). Ideas/Vis (creative promotion,
     # being seen/heard) are marketing's actual core identity, not incidental
     # — sharpening them to match the strength convention used everywhere
     # else in the catalog.
     "profile": {"People": 1, "Data": 1, "Ideas": 2, "Inv": 1, "Obj": -1, "Vis": 2, "Emp": 1, "Motiv": 1, "Predict": 1, "Acad": 1},
     "professions": ["Маркетолог", "Digital-маркетолог", "Бренд-менеджер"]},
    {"slug": "finance-accounting", "name": "Финансы и учёт", "section": "akinator-business-sales",
     "description": "Финансы и учёт готовят специалистов, которые ведут финансовый учёт компании — следят, чтобы деньги, налоги и отчётность были в порядке.",
     # Focus 2->1 (calibration playtest pass, 2026-07, round 8): traced 5
     # data-science sessions — all 5 lost to finance-accounting, all 5 driven
     # mainly by order=48 (finance's own, legitimate resolver), whose option
     # matches finance's Math/Focus/Struct/Predict almost exactly — but
     # data-science shares 3 of those same 4 axes, so it got dragged along
     # every time. Order=51 (the dedicated data-science/software-engineer/
     # finance-accounting/it-security resolver) already correctly favors
     # data-science on its own turf and didn't need touching; boosting it
     # further to out-score order=48 only created new ties with
     # software-engineer/finance's own options on order=51 (checked
     # numerically, rejected). Trimming finance's Focus is the minimal
     # change: finance still wins order=48 outright on Math+Struct+Predict
     # alone (score drops only 2.92->2.70), while data-science's accidental
     # pull toward that option drops more meaningfully (1.95->1.62).
     "profile": {"Data": 2, "Obj": -1, "Exp": 2, "Focus": 1, "Struct": 2, "Motiv": -1, "Auto": 1, "Predict": -2, "Pace": -1, "Acad": 1, "Math": 2, "People": -1},
     "professions": ["Бухгалтер", "Финансовый аналитик", "Аудитор"]},

    # Безопасность и спасение — уже на минимуме (2 листа), не сжимаем
    {"slug": "fire-safety-engineer", "name": "Техносферная безопасность", "label_junior": "Пожарный", "section": "akinator-safety-rescue",
     "description": "Техносферная безопасность проектирует системы защиты от пожаров и обеспечивает безопасность зданий и людей.",
     "profile": {"People": 1, "Phys": 1, "Data": 1, "Care": 1, "Obj": 1, "Lead": 1, "Exp": 2, "Focus": 1, "Risk": 2, "Struct": 2, "Pace": 1, "Predict": 1, "PhysSt": 1, "Acad": 1, "Math": 1},
     "professions": ["Инженер пожарной безопасности", "Специалист по охране труда", "Инспектор пожарной безопасности"]},
    {"slug": "police-officer", "name": "Правоохранительная деятельность", "section": "akinator-safety-rescue",
     "description": "Правоохранительная деятельность следит за порядком и безопасностью людей, реагирует на происшествия и расследует правонарушения.",
     "profile": {"People": 1, "Phys": 1, "Lead": 1, "Exp": 1, "Focus": -1, "Risk": 1, "Struct": 2, "Pace": 1, "Predict": 1, "PhysSt": 1},
     "professions": ["Полицейский", "Следователь", "Инспектор"]},
]

assert len(SECTIONS) == 13, f"expected 13 sections, got {len(SECTIONS)}"
assert len(SPECIALTIES) == 38, f"expected 38 specialties, got {len(SPECIALTIES)}"

_SECTION_SLUGS = {s["slug"] for s in SECTIONS}
for _p in SPECIALTIES:
    assert _p["section"] in _SECTION_SLUGS, f"{_p['slug']}: unknown section {_p['section']}"
assert len({p["slug"] for p in SPECIALTIES}) == len(SPECIALTIES), "duplicate specialty slug"

# Every section must keep at least 2 leaves — a branch with one leaf forks
# nothing and just wastes a tree level.
_leaf_counts: dict[str, int] = {}
for _p in SPECIALTIES:
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
SPECIALTY_AGE_GROUPS = ["middle", "senior"]


def compute_section_profiles() -> dict[str, dict[str, float]]:
    """Section profile = centroid (mean) of its leaves' profiles.

    Junior converges to sections, so sections need a profile or junior's belief
    can never move — that was the actual defect behind the earlier "open every
    profession to every age" patch. Near-zero axes are dropped to keep the
    vector sparse and readable; |mean| < 0.34 means the leaves disagree so much
    that the axis carries no branch-level signal.
    """
    by_section: dict[str, list[dict]] = {}
    for spec in SPECIALTIES:
        by_section.setdefault(spec["section"], []).append(spec["profile"])

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
         # Bumped Ideas 1->2 and added Vis:1 (calibration playtest pass, 2026-07):
         # marketing's own profile (Emp:1,Motiv:1 alongside Ideas:1,Inv:1,Vis:1)
         # scored HIGHER on the "sales" option than on this, its own option —
         # the old {"Inv":2,"Ideas":1} was too thin to beat option 0's Emp+Motiv
         # magnitude. See akinator_engine.match_score census notes.
         {"text": "придумывать, как о продукте узнают, кампании, идеи", "axis_weights": {"Inv": 2, "Ideas": 2, "Vis": 1}},
     ], "resolves_pair": ["management-entrepreneurship", "marketing"]},
    {"order": 24, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Когда рядом кому-то плохо и нужна помощь, ты…",
     "text_junior": "Когда друг поранился: бросаешься помогать сразу или сначала спокойно смотришь, что случилось?",
     "options": [
         {"text": "действую сразу, быстро, на месте", "axis_weights": {"Pace": 2, "Focus": -2, "Risk": 1}},
         {"text": "хочу разобраться спокойно и точно поставить диагноз", "axis_weights": {"Focus": 2, "Exp": 1}},
         # Neutral option added (calibration playtest pass, 2026-07): this
         # question has no resolves_pair, so it isn't covered by the
         # select_next_question relevance filter and keeps getting served to
         # sessions with no real Pace/Risk/Focus signal either way — without
         # an escape hatch they were forced into a non-answer that nudged
         # belief toward whichever side had ANY overlap (e.g. dragging
         # school-teacher/marketing personas toward hospitality-manager).
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},  # specialty pivot: emergency-physician/physician/surgeon all merged into general-medicine — no longer a specialty-level fork, kept as general belief-shaping signal
    {"order": 26, "kind": "direct", "depth": 2, "age_variant": "both",
     "text": "Про животных и природу — что ближе?",
     "text_junior": "С животными интереснее: лечить и заботиться, наблюдать и изучать, или ухаживать за растениями?",
     "options": [
         {"text": "лечить и заботиться о конкретных животных", "axis_weights": {"Care": 2, "Living": 2}},
         {"text": "изучать их, наблюдать, понимать, как всё устроено", "axis_weights": {"Obj": -2, "Exp": 2, "Focus": 2}},
         # Added Living:2 (calibration playtest pass, 2026-07): agronomist's own
         # profile has no Care axis at all, so it used to score higher on the
         # "care for animals" option than on this, its own — Living is exactly
         # as much about plants/soil as about animals (see axes.py), this
         # option just never carried any. Checked against the other 3 leaves
         # in this resolver — none of their rankings flip.
         {"text": "работать на земле, выращивать", "axis_weights": {"Phys": 1, "PhysSt": 1, "Living": 2}},
         {"text": "тренировать животных, работать с ними в паре", "axis_weights": {"Dev": 2, "Motor": 1, "People": 1}},
     ], "resolves_pair": ["veterinary-zootechnics", "zoologist", "ecologist", "agronomist"]},
    # Third option added (replacement pass) so building-systems-engineer, the
    # plumber replacement, has a fork that reaches it.
    {"order": 28, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Если проектировать — что ближе?", "text_junior": None,
     "options": [
         # Added Obj:1, Inv:1 (calibration playtest pass, 2026-07): this option
         # only carried Phys:2, one axis, while the competing "buildings"
         # option below carries three (Phys+Struct+Lead) — a textbook
         # mechanical-engineer profile (which also has Obj:2, Inv:1) scored
         # HIGHER on "buildings" than on its own option. Checked: civil-
         # engineering still clearly prefers its own option after this change.
         {"text": "механизмы, машины, устройства", "axis_weights": {"Phys": 2, "Obj": 1, "Inv": 1}},
         {"text": "здания, мосты, конструкции", "axis_weights": {"Phys": 2, "Struct": 2, "Lead": 1}},
         {"text": "инженерные системы зданий: вода, тепло, вентиляция", "axis_weights": {"Motor": 1, "Focus": 2, "Predict": -1}},
     ], "resolves_pair": ["mechanical-engineer", "civil-engineering"]},
    {"order": 29, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Работа руками — тебе как?",
     "text_junior": "Тебе нравится активная работа руками, где надо двигаться, или спокойнее?",
     "options": [
         {"text": "да, люблю физическую работу, на ногах, с материалами", "axis_weights": {"PhysSt": 2, "Motor": 1, "Phys": 2}},
         {"text": "лучше что-то поспокойнее, не тяжёлое физически", "axis_weights": {"PhysSt": -2}},
         # Neutral option added (calibration playtest pass, 2026-07) — see order 24.
         {"text": "не знаю", "axis_weights": {}},
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
     ], "resolves_pair": ["food-production-tech", "hospitality-manager"]},
    {"order": 36, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "Тебе дали цель и свободу. Ты…",
     "text_junior": "Тебе интереснее придумать своё дело и вести его самому или делать понятную работу спокойно?",
     "options": [
         {"text": "рискну, придумаю своё дело, буду сам за всё отвечать", "axis_weights": {"Risk": 2, "Auto": 2, "Inv": 2, "Lead": 2}},
         {"text": "лучше в понятной роли с стабильностью", "axis_weights": {"Risk": -2, "Struct": 1}},
         # Neutral option added (calibration playtest pass, 2026-07) — see order 24.
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": None},  # source says "предприниматель vs исполнительские роли" (generic) — flagged, see module docstring
    {"order": 37, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "С числами и деньгами тебе как?", "text_junior": None,
     "options": [
         # Halved 2->1 on every axis (calibration playtest pass, 2026-07,
         # round 2): at full strength this option's weights were nearly an
         # exact copy of finance-accounting's own profile
         # (Data:2,Struct:2,Focus:2,Math:2) — every "precise, structured"
         # answer (data-science, software-engineer, any STEM-leaning
         # session included) read as strong accountant evidence even though
         # resolves_pair=None means it was never covered by the resolver-
         # weight audit or any pair-specific counterbalance. It doubled up
         # with order=48 (the real finance-accounting resolver) and fired in
         # 5/5 traced data-science sessions, usually before order=51 (the
         # dedicated data-science/software-engineer/finance-accounting/
         # it-infrastructure-security resolver) got a chance to counter it —
         # by the time order=51 fired, finance-accounting's lead was already
         # too big to close. Kept non-zero (still a useful generic
         # precise-vs-people-and-ideas signal), just no longer resolver-
         # strength for a question that isn't declared as one.
         {"text": "люблю точность, порядок, считать", "axis_weights": {"Data": 1, "Struct": 1, "Focus": 1, "Math": 1}},
         {"text": "скучно, мне интереснее люди и идеи", "axis_weights": {"Data": -1, "People": 1}},
     ], "resolves_pair": None},  # source says "бухгалтер vs остальной бизнес" (generic) — flagged, see module docstring
    {"order": 38, "kind": "situational", "depth": 2, "age_variant": "both",
     "text": "В опасной или острой ситуации ты…",
     "text_junior": "Тебе ближе спасать и действовать в опасности или следить за порядком, чтобы не случилось плохого?",
     "options": [
         {"text": "готов рисковать, спасать, действовать быстро", "axis_weights": {"Risk": 2, "Pace": 2, "PhysSt": 2, "Care": 1}},
         {"text": "лучше держать порядок, следить, предотвращать", "axis_weights": {"Struct": 2, "Focus": 1}},
     ], "resolves_pair": ["fire-safety-engineer", "police-officer", "general-medicine"]},
    # Revived (replacement pass): makeup-artist-film now exists, so this
    # question's weights reach a leaf again. Before the replacement it was a
    # dead question — hairdresser/makeup-artist had been retired and the
    # People/Motor/Ideas weights just leaked into fashion-designer and actor.
    {"order": 39, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Работать над внешним образом человека — тебе как?",
     "text_junior": None,
     "options": [
         {"text": "да: лицо, грим, образ — превращать человека в персонажа", "axis_weights": {"People": 2, "Motor": 2, "Emp": 1}},
         # Added Ideas:1 (calibration playtest pass, 2026-07): design's own
         # profile (Ideas:2, Inv:2) scored higher on the "makeup" option than
         # on this, its own — Phys+Vis alone was too thin. makeup-artist-film
         # still wins its own option by a wide margin either way.
         {"text": "ближе создавать вещи и одежду, а не работать с лицом", "axis_weights": {"Phys": 1, "Vis": 1, "Ideas": 1}},
     ], "resolves_pair": ["makeup-artist-film", "design"]},
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
     ], "resolves_pair": ["dentist", "general-medicine", "veterinary-zootechnics", "rehabilitation-therapist"]},
    {"order": 42, "kind": "direct", "depth": 2, "age_variant": "senior",
     "text": "Работать с психикой человека тебе ближе как?", "text_junior": None,
     "options": [
         {"text": "изучать биологию, работать как врач, при необходимости — лечить лекарствами",
          "axis_weights": {"Living": 2, "Care": 1}},
         {"text": "разговаривать, слушать и помогать разобраться в себе без медицинских препаратов",
          "axis_weights": {"Emp": 2, "Auto": 1}},
     ], "resolves_pair": ["general-medicine", "psychologist"]},
    # --- Replacement pass additions (orders 45-49): every new profession needs
    # at least one fork that separates it from its nearest neighbour, otherwise
    # it is unreachable (the belief can never single it out).
    {"order": 45, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Продвигать компанию или товар — что тебе ближе?", "text_junior": None,
     "options": [
         {"text": "придумывать сообщение, тексты, образ бренда",
          "axis_weights": {"Ideas": 2, "Inv": 2, "Data": -1}},
         # Added Predict:1 (calibration playtest pass, 2026-07): marketing's
         # own profile tied exactly 0.95/0.95 between the two options here —
         # both are shared "creative" axes with pr-specialist, so neither
         # discriminated for marketing specifically. Predict:1 matches
         # marketing's own profile without helping pr-specialist (which
         # carries no Predict axis at all), breaking the tie in marketing's
         # favor without weakening pr-specialist's already-clear win on option 0.
         {"text": "считать, какая кампания сработала, разбирать цифры и аудиторию",
          "axis_weights": {"Data": 2, "Math": 1, "Obj": -1, "Predict": 1}},
     ], "resolves_pair": ["pr-specialist", "marketing"]},
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
     ], "resolves_pair": ["management-entrepreneurship", "finance-accounting"]},
    {"order": 49, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Что хочется создавать?", "text_junior": None,
     "options": [
         {"text": "вещи, которые можно потрогать: мебель, предметы",
          "axis_weights": {"Phys": 2, "Motor": 1}},
         {"text": "картинки, экраны, айдентику — то, что живёт на плоскости",
          "axis_weights": {"Ideas": 2, "PhysSt": -1}},
         {"text": "здания и пространства, где ходят люди",
          "axis_weights": {"Phys": 1, "Struct": 2, "Lead": 1, "Acad": 1}},
     ], "resolves_pair": ["design", "architect"]},
    # Added (calibration playtest pass, 2026-07): the "Помощь и психология"
    # section has 3 leaves (psychologist, speech-therapist, social-worker)
    # but only orders 19 and 47 fork psychologist away from the other two —
    # nothing ever separated speech-therapist from social-worker directly, so
    # the pair relied entirely on generic cross-section signal. Verified
    # against all 3 leaf profiles: speech-therapist and social-worker each
    # clearly prefer their own option; psychologist scores low on both.
    {"order": 50, "kind": "situational", "depth": 3, "age_variant": "senior",
     "text": "Кому-то нужна регулярная помощь. Тебе ближе…", "text_junior": None,
     "options": [
         {"text": "долго и по чуть-чуть тренировать один конкретный навык на регулярных встречах",
          "axis_weights": {"Dev": 2, "Focus": 1, "Struct": 1}},
         {"text": "разобраться, что у человека не так в жизни, и организовать нужную помощь: жильё, документы, службы",
          "axis_weights": {"Lead": 1, "Struct": 1, "Predict": 1, "Pace": 1}},
     ], "resolves_pair": ["speech-therapist", "social-worker"]},
    # Added (calibration playtest pass, 2026-07, round 2): the "IT и данные"
    # section (data-science, software-engineer, it-infrastructure-security)
    # plus finance-accounting had NO resolver at all separating them, despite
    # sharing most of their axis vocabulary (Data/Focus/Struct/Math) — census
    # showed data-science losing to finance-accounting 25-27/30 trials.
    # order=37 ("С числами и деньгами тебе как?") drives much of that: it's
    # an undeclared de-facto finance-accounting question (resolves_pair=None,
    # so untouched by the earlier resolver-weight audit) whose weights read
    # as "precise, structured, likes numbers" — true of data-science and
    # software-engineer too, so it boosts finance-accounting on every session
    # regardless of which of the four this really is. Verified against all
    # four leaf profiles: each clearly prefers its own option (data-science
    # 0.97 vs 0.49 next-best; software-engineer 0.86 vs 0.69; finance-
    # accounting 1.10 vs 0.73; it-infrastructure-security 0.71 vs 0.47).
    {"order": 51, "kind": "direct", "depth": 3, "age_variant": "senior",
     "text": "Работа с числами и данными — что тебе конкретно нравится?", "text_junior": None,
     "options": [
         {"text": "искать закономерности и смысл в больших массивах данных",
          "axis_weights": {"Obj": -2, "Data": 1, "Ideas": 1}},
         {"text": "писать код, создавать программы и системы",
          "axis_weights": {"Inv": 2, "Obj": 2, "Ideas": 1}},
         {"text": "следить, чтобы цифры и документы точно сходились, без сюрпризов",
          "axis_weights": {"Predict": -2, "Struct": 1}},
         {"text": "следить, чтобы всё работало и было защищено, реагировать на нештатные ситуации",
          "axis_weights": {"Predict": 1, "Pace": 1, "Focus": -1}},
         # Neutral option added (calibration playtest pass, 2026-07, round 10):
         # this question has no resolves_pair-relevance gate (that approach
         # was tried and reverted, see akinator_engine.select_next_question),
         # so it still gets served to sessions with no stake in any of the 4
         # IT/finance options. Without an escape, a persona scoring exactly 0
         # on all 4 (e.g. psychologist) got deterministically routed to
         # option 1 ("писать код") every time, since pick_option / the
         # engine's tie-break picks the first max-scoring option — traced
         # psychologist sessions confirmed this dragging it toward
         # software-engineer/pr-specialist/makeup-artist-film with zero
         # genuine signal behind it.
         {"text": "не знаю", "axis_weights": {}},
     ], "resolves_pair": ["data-science", "software-engineer", "finance-accounting", "it-infrastructure-security"]},
    # Added (calibration playtest pass, 2026-07, round 6): school-teacher and
    # speech-therapist share both their top axes (People:2, Dev:2) and had no
    # question anywhere separating them directly — order 19 forks
    # speech-therapist away from psychologist, order 50 away from
    # social-worker, but nothing forks it from school-teacher, so traced
    # sessions kept landing in a cluster of the two. Verified against both
    # profiles: school-teacher clearly prefers its own option (0.75 vs 0.25),
    # speech-therapist clearly prefers its own (1.21 vs 0).
    {"order": 52, "kind": "situational", "depth": 3, "age_variant": "senior",
     "text": "Как ты хочешь помогать разбираться в чём-то?", "text_junior": None,
     "options": [
         {"text": "объяснять предмет целому классу, увлекать и держать внимание",
          "axis_weights": {"Vis": 2, "Lead": 1}},
         {"text": "работать один на один, регулярно, над конкретной проблемой человека",
          "axis_weights": {"Exp": 2, "Focus": 1}},
     ], "resolves_pair": ["school-teacher", "speech-therapist"]},
]

assert len(QUESTIONS) == 43, f"expected 43 questions, got {len(QUESTIONS)}"
assert len({q["order"] for q in QUESTIONS}) == len(QUESTIONS), "duplicate question order"

# Every slug named in a resolves_pair must actually exist as a leaf — this is
# what would have caught the dead order-39 question in the retirement pass.
_ALL_SPECIALTY_SLUGS = {p["slug"] for p in SPECIALTIES}
for _q in QUESTIONS:
    for _slug in _q["resolves_pair"] or []:
        assert _slug in _ALL_SPECIALTY_SLUGS, f"q order {_q['order']}: unknown slug {_slug!r} in resolves_pair"


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
    # Specialty pivot (2026-07-17): these 51 profession leaves are replaced by
    # 38 SPECIALTIES above — merged into a broader specialty (see the "Merge"
    # comments in SPECIALTIES) or renamed 1:1 to a new slug. Either way the old
    # slug must be retired so cleanup_retired_content nulls any
    # Assessment.selected_direction_slug still pointing at it.
    "surgeon", "physician", "emergency-physician", "psychiatrist",  # -> general-medicine
    "veterinarian", "cynologist",  # -> veterinary-zootechnics
    "programmer", "qa-tester",  # -> software-engineer
    "data-analyst",  # -> data-science (renamed)
    "sysadmin",  # -> it-infrastructure-security (renamed)
    "civil-engineer", "building-systems-engineer",  # -> civil-engineering
    "graphic-designer", "illustrator", "fashion-designer", "furniture-designer", "ux-designer",  # -> design
    "head-chef", "confectionery-technologist",  # -> food-production-tech
    "sales-manager", "entrepreneur", "logistician",  # -> management-entrepreneurship
    "marketer",  # -> marketing (renamed)
    "accountant",  # -> finance-accounting (renamed)
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
# 23: illustrator/graphic-designer merged into one `design` specialty (specialty
#     pivot) — pair no longer distinguishes anything.
# 25: surgeon/physician/psychiatrist merged into `general-medicine` — same reasoning.
# 35: head-chef/confectionery-technologist merged into `food-production-tech`.
# 43: physician/emergency-physician merged into `general-medicine`.
RETIRED_QUESTION_ORDERS: list[int] = [22, 23, 25, 27, 31, 33, 35, 40, 43, 44]

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
    known = {s["slug"] for s in SECTIONS} | {p["slug"] for p in SPECIALTIES}
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
            if existing.description != section["description"]:
                existing.description = section["description"]
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
            description=section["description"],
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


async def seed_specialties(
    db: AsyncSession, section_ids: dict[str, uuid.UUID]
) -> tuple[int, int, int]:
    """Upsert the 38 leaf Directions (specialties) by slug. Returns (inserted, updated, skipped)."""
    inserted = updated = skipped = 0

    for spec in SPECIALTIES:
        parent_id = section_ids[spec["section"]]
        label_junior = spec.get("label_junior")
        result = await db.execute(select(Direction).where(Direction.slug == spec["slug"]))
        existing = result.scalar_one_or_none()

        if existing is not None:
            changed = False
            if existing.name != spec["name"]:
                existing.name = spec["name"]
                changed = True
            if existing.description != spec["description"]:
                existing.description = spec["description"]
                changed = True
            if existing.profile != spec["profile"]:
                existing.profile = spec["profile"]
                changed = True
            if existing.professions != spec["professions"]:
                existing.professions = spec["professions"]
                changed = True
            if existing.parent_id != parent_id:
                existing.parent_id = parent_id
                changed = True
            if existing.is_leaf is not True:
                existing.is_leaf = True
                changed = True
            if existing.age_groups != SPECIALTY_AGE_GROUPS:
                existing.age_groups = SPECIALTY_AGE_GROUPS
                changed = True
            if existing.label_junior != label_junior:
                existing.label_junior = label_junior
                changed = True
            updated += 1 if changed else 0
            skipped += 0 if changed else 1
            continue

        direction = Direction(
            name=spec["name"],
            slug=spec["slug"],
            description=spec["description"],
            required_scores={},
            parent_id=parent_id,
            is_leaf=True,
            profile=spec["profile"],
            professions=spec["professions"],
            age_groups=SPECIALTY_AGE_GROUPS,
            label_junior=label_junior,
        )
        db.add(direction)
        inserted += 1

    return inserted, updated, skipped


async def seed_questions(db: AsyncSession) -> tuple[int, int, int]:
    """Upsert the 41 AkinatorQuestion rows by `order` (this script owns 0-50,
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
        spec_ins, spec_upd, spec_skip = await seed_specialties(db, section_ids)
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
            f"Specialties: inserted {spec_ins}, updated {spec_upd}, skipped {spec_skip} "
            f"(total {len(SPECIALTIES)}, age_groups={SPECIALTY_AGE_GROUPS})"
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
