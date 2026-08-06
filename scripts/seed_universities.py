"""
Seed script: populate universities and programs tables.
Run inside Docker: docker-compose exec api python scripts/seed_universities.py
Idempotent: upserts by university name; upserts programs by (university_id, name).
Coverage: Kazakhstan only — 12 universities, 16 programs, each tagged directly
with the profession slug(s) it prepares someone for (Program.profession_slugs,
see scripts/specialty_profession_map.py) rather than a category.

This is a hand-picked highlight set with curated per-program admissions
detail; scripts/seed_kz_universities.py separately seeds the much larger
university-data/*.py scrape (55 KZ universities) and reconciles overlaps
with this file's entries by name (see its LEGACY_NAME_BY_SLUG map) rather
than creating duplicates.
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university import University


def slugify(name: str) -> str:
    slug = name.lower()
    slug = slug.replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

UNIVERSITIES: list[dict] = [
    # --- Казахстан ---
    {
        "name": "Nazarbayev University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://nu.edu.kz",
        "ranking": 301,
        "description": (
            "Ведущий исследовательский университет Казахстана, предлагающий программы "
            "на английском языке в партнёрстве с ведущими мировыми университетами."
        ),
    },
    {
        "name": "KIMEP University",
        "country": "Казахстан",
        "city": "Алматы",
        "website": "https://kimep.kz",
        "ranking": None,
        "description": (
            "Ведущий казахстанский университет в области бизнеса и социальных наук, "
            "полностью аккредитованный AACSB и AMBA."
        ),
    },
    {
        "name": "Al-Farabi Kazakh National University",
        "country": "Казахстан",
        "city": "Алматы",
        "website": "https://kaznu.kz",
        "ranking": 181,
        "description": (
            "Крупнейший классический университет Казахстана, предлагающий широкий спектр "
            "программ в области естественных наук, инженерии и гуманитарных дисциплин."
        ),
    },
    # --- Казахстан (продолжение: покрытие остальных направлений) ---
    # Данные ниже собраны веб-рисёрчем 2026-07-03 из открытых источников (официальные сайты
    # вузов, univision.kz, studenthub.kz, kaznpu.kz, admission.mnu.kz и т.д.).
    # Стоимость обучения и проходные баллы по гранту меняются год к году — там, где точные
    # цифры на 2025/2026 не найдены, использована ближайшая известная цифра с пометкой
    # "ориентировочно" в requirements/grants соответствующей программы.
    {
        "name": "Astana IT University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://astanait.edu.kz",
        "ranking": None,
        "description": (
            "Специализированный технологический университет Казахстана, созданный при "
            "поддержке Nazarbayev University и индустриальных партнёров, с фокусом на IT, "
            "большие данные и искусственный интеллект."
        ),
    },
    {
        "name": "Kazakh National Academy of Arts named after T. Zhurgenov",
        "country": "Казахстан",
        "city": "Алматы",
        "website": "https://zhurgenov.kz",
        "ranking": None,
        "description": (
            "Ведущий творческий вуз Казахстана в области искусств и дизайна, готовящий "
            "художников, дизайнеров и деятелей культуры с 1988 года."
        ),
    },
    {
        "name": "Satbayev University",
        "country": "Казахстан",
        "city": "Алматы",
        "website": "https://satbayev.university",
        "ranking": None,
        "description": (
            "Старейший технический университет Казахстана (Казахский национальный "
            "исследовательский технический университет имени К.И. Сатпаева), ведущий центр "
            "подготовки инженеров и архитекторов."
        ),
    },
    {
        "name": "L.N. Gumilyov Eurasian National University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://enu.kz",
        "ranking": None,
        "description": (
            "Один из крупнейших классических университетов Казахстана в Астане с сильными "
            "программами в области естественных наук, экологии и международных отношений."
        ),
    },
    {
        "name": "Abai Kazakh National Pedagogical University",
        "country": "Казахстан",
        "city": "Алматы",
        "website": "https://kaznpu.kz",
        "ranking": None,
        "description": (
            "Старейший и крупнейший педагогический университет Казахстана, ведущий центр "
            "подготовки психологов и педагогов."
        ),
    },
    {
        "name": "M. Narikbayev KAZGUU University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://mnu.kz",
        "ranking": None,
        "description": (
            "Ведущий университет Казахстана в области права и государственного управления, "
            "готовящий юристов и госслужащих в партнёрстве с зарубежными школами права."
        ),
    },
    {
        "name": "Kazakh Ablai Khan University of International Relations and World Languages",
        "country": "Казахстан",
        "city": "Алматы",
        "website": "https://ablaikhan.kz",
        "ranking": None,
        "description": (
            "Ведущий лингвистический университет Казахстана, специализирующийся на "
            "международных отношениях, журналистике и иностранных языках."
        ),
    },
    {
        "name": "Almaty Management University",
        "country": "Казахстан",
        "city": "Алматы",
        "website": "https://almau.edu.kz",
        "ranking": None,
        "description": (
            "Частный университет Казахстана, специализирующийся на бизнес-образовании, "
            "маркетинге и менеджменте, с англоязычными треками обучения."
        ),
    },
    {
        "name": "Narxoz University",
        "country": "Казахстан",
        "city": "Алматы",
        "website": "https://narxoz.edu.kz",
        "ranking": None,
        "description": (
            "Ведущий экономический университет Казахстана, готовящий специалистов "
            "в области менеджмента, финансов и бизнес-аналитики."
        ),
    },
]

# Programs keyed by university name → list of program dicts
PROGRAMS_BY_UNIVERSITY: dict[str, list[dict]] = {
    "Nazarbayev University": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "profession_slugs": ["razrabotchik-programmnogo-obespecheniya"],
            "language": "Английский",
            "cost_per_year": 3000,
            "description": (
                "Четырёхлетняя программа бакалавриата, охватывающая алгоритмы, системное "
                "программирование, разработку ПО и ИИ, полностью на английском языке."
            ),
            "who_its_for": (
                "Высокоуспевающие выпускники школ, увлечённые разработкой ПО и исследованиями, "
                "стремящиеся к карьере в IT или продолжению учёбы за рубежом."
            ),
            "career_options": [
                "Инженер-программист", "Бэкенд-разработчик", "Инженер-исследователь",
                "Системный архитектор", "Технический лидер",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["SAT", "IELTS", "ЕНТ"],
                "min_ielts": 6.5,
                "min_sat": 1200,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по математике/информатике", "Соревнования по программированию"],
            },
            "deadlines": {
                "application_open": "2025-11-01",
                "application_close": "2026-02-28",
                "exam_deadline": "2026-02-01",
                "decision_date": "2026-04-15",
            },
            "grants": [
                {
                    "name": "Президентская стипендия",
                    "amount": "Полная оплата обучения + стипендия",
                    "conditions": "Высокий балл ЕНТ, конкурсный отбор",
                },
                {
                    "name": "Премия NU за заслуги",
                    "amount": "50% оплаты обучения",
                    "conditions": "SAT 1350+ или эквивалент",
                },
            ],
        },
        {
            "name": "Наука о данных (бакалавр)",
            "profession_slugs": ["analitik-dannyh"],
            "language": "Английский",
            "cost_per_year": 3000,
            "description": (
                "Междисциплинарная программа, сочетающая статистику, машинное обучение "
                "и инженерию данных для подготовки специалистов к работе в экономике данных."
            ),
            "who_its_for": (
                "Студенты с сильной подготовкой по математике и статистике, желающие строить "
                "прогностические модели и извлекать знания из больших массивов данных."
            ),
            "career_options": [
                "Специалист по данным", "ML-инженер", "Аналитик данных",
                "BI-разработчик", "Аналитик-исследователь",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["SAT", "IELTS", "ЕНТ"],
                "min_ielts": 6.5,
                "min_sat": 1200,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Математические олимпиады", "Проекты по статистике или программированию"],
            },
            "deadlines": {
                "application_open": "2025-11-01",
                "application_close": "2026-02-28",
                "exam_deadline": "2026-02-01",
                "decision_date": "2026-04-15",
            },
            "grants": [
                {
                    "name": "Президентская стипендия",
                    "amount": "Полная оплата обучения + стипендия",
                    "conditions": "Высокий балл ЕНТ, конкурсный отбор",
                },
            ],
        },
    ],
    "KIMEP University": [
        {
            "name": "Управление бизнесом (BBA)",
            "profession_slugs": ["predprinimatel"],
            "language": "Английский",
            "cost_per_year": 4500,
            "description": (
                "Четырёхлетняя программа BBA с аккредитацией AACSB, охватывающая менеджмент, "
                "маркетинг, финансы и предпринимательство с сильным практическим уклоном."
            ),
            "who_its_for": (
                "Амбициозные студенты, желающие открыть собственное дело или построить карьеру "
                "в менеджменте, консалтинге или корпоративном руководстве."
            ),
            "career_options": [
                "Бизнес-аналитик", "Продакт-менеджер", "Предприниматель",
                "Консультант по управлению", "Операционный менеджер",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["IELTS", "TOEFL", "ЕНТ"],
                "min_ielts": 6.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Студенческое самоуправление", "Соревнования по бизнес-кейсам"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-03-31",
                "exam_deadline": "2026-03-01",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Стипендия KIMEP за отличие",
                    "amount": "До 100% оплаты обучения",
                    "conditions": "Высокий балл ЕНТ + собеседование",
                },
            ],
        },
        {
            "name": "Финансы (бакалавр)",
            "profession_slugs": ["finansovyy-konsultant"],
            "language": "Английский",
            "cost_per_year": 4500,
            "description": (
                "Строгая программа по финансам, охватывающая корпоративные финансы, "
                "инвестиционный анализ, финансовое моделирование и рынки капитала."
            ),
            "who_its_for": (
                "Студенты, увлечённые финансовыми рынками, инвестиционным банкингом "
                "или карьерой в финтехе и корпоративных финансах."
            ),
            "career_options": [
                "Финансовый аналитик", "Инвестиционный банкир", "Риск-менеджер",
                "Аудитор", "Финтех-специалист",
            ],
            "requirements": {
                "min_gpa": 3.2,
                "exams": ["IELTS", "TOEFL", "ЕНТ"],
                "min_ielts": 6.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по экономике", "Финансовые клубы"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-03-31",
                "exam_deadline": "2026-03-01",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Стипендия KIMEP за заслуги",
                    "amount": "25–75% оплаты обучения",
                    "conditions": "GPA 3.5+ и IELTS 7.0+",
                },
            ],
        },
    ],
    "Al-Farabi Kazakh National University": [
        {
            "name": "Разработка программного обеспечения (бакалавр)",
            "profession_slugs": ["razrabotchik-programmnogo-obespecheniya"],
            "language": "Казахский / Русский",
            "cost_per_year": 900,
            "description": (
                "Пятилетняя инженерная степень, охватывающая проектирование ПО, алгоритмы, "
                "базы данных и системное программирование. Есть места по государственному гранту."
            ),
            "who_its_for": (
                "Выпускники, стремящиеся получить доступную и качественную инженерную степень "
                "в крупнейшем классическом университете Казахстана."
            ),
            "career_options": [
                "Разработчик ПО", "Системный аналитик", "Администратор баз данных",
                "QA-инженер", "IT-консультант",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["ЕНТ"],
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Соревнования по программированию", "Научные ярмарки"],
            },
            "deadlines": {
                "application_open": "2026-06-01",
                "application_close": "2026-07-25",
                "exam_deadline": "2026-06-20",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Высокий балл ЕНТ, конкурсный отбор по специальности",
                },
            ],
        },
        {
            "name": "Биология (бакалавр)",
            "profession_slugs": ["biolog"],
            "language": "Казахский / Русский",
            "cost_per_year": 800,
            "description": (
                "Классическая программа по биологии, охватывающая клеточную биологию, генетику, "
                "экологию и биохимию с лабораторной практикой."
            ),
            "who_its_for": (
                "Студенты, увлечённые живыми организмами и экологией, стремящиеся к карьере "
                "в биотехнологиях, медицине или науке."
            ),
            "career_options": [
                "Биолог", "Биохимик", "Научный сотрудник лаборатории",
                "Эколог", "Медицинский учёный",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["ЕНТ"],
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по биологии", "Волонтёрство в сфере экологии"],
            },
            "deadlines": {
                "application_open": "2026-06-01",
                "application_close": "2026-07-25",
                "exam_deadline": "2026-06-20",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Высокий балл ЕНТ по химии/биологии",
                },
            ],
        },
        # Источник: welcome.kaznu.kz/ru/education_programs/bachelor/speciality/1436,
        # univision.kz/univ/50-kazahskiy-natsionalnyy-universitet-imeni-al-farabi/price.
        # Проверено: 2026-07-03. Стоимость — ориентировочно (усреднено по кластеру
        # физико-математических программ 6B053xx, официальная цена по конкретной
        # специальности на welcome.kaznu.kz не была доступна для парсинга).
        {
            "name": "Физика (бакалавр)",
            "profession_slugs": ["matematik"],
            "language": "Казахский / Русский",
            "cost_per_year": 2075,
            "description": (
                "Классическая программа по физике, охватывающая теоретическую и "
                "экспериментальную физику, с возможностью специализации в медицинской, "
                "ядерной или вычислительной физике."
            ),
            "who_its_for": (
                "Студенты, увлечённые фундаментальной наукой и математическим "
                "моделированием, стремящиеся к научной или исследовательской карьере."
            ),
            "career_options": [
                "Учёный-исследователь", "Преподаватель физики", "Инженер-физик",
                "Специалист по вычислительному моделированию", "Медицинский физик",
            ],
            "requirements": {
                "min_gpa": 3.2,
                "exams": ["ЕНТ"],
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по физике/математике", "Научные проекты"],
            },
            "deadlines": {
                "application_open": "2026-06-20",
                "application_close": "2026-08-25",
                "exam_deadline": "2026-07-10",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": (
                        "Естественные науки — приоритетное направление госзаказа; точный "
                        "проходной балл по специальности не подтверждён (ориентировочно)"
                    ),
                },
            ],
        },
    ],
    "Astana IT University": [
        # Источник: astanait.edu.kz/ru/BigDataAnalysis-bachelor, astanait.edu.kz/ru/how-to-apply,
        # astanait.edu.kz/2024/06/25/information-technology-porog/, univision.kz/univ/119-astana-it-university/price.
        # Проверено: 2026-07-03. Стоимость 2 500 000 тг/год ≈ $4 717 (курс ~530 тг/$) —
        # ориентировочно: встречается конфликтующая оценка ($15 000) на агрегаторах.
        {
            "name": "Анализ больших данных (бакалавр)",
            "profession_slugs": ["analitik-dannyh"],
            "language": "Казахский / Русский",
            "cost_per_year": 4717,
            "description": (
                "Программа 6B06103 «Анализ больших данных» готовит специалистов по обработке "
                "и анализу больших массивов данных, машинному обучению и ИИ-системам. При "
                "поступлении помимо ЕНТ учитывается внутренний тест AITU (AET)."
            ),
            "who_its_for": (
                "Абитуриенты с сильной подготовкой по математике и информатике, желающие "
                "работать с большими данными, аналитикой и системами искусственного интеллекта."
            ),
            "career_options": [
                "Аналитик данных", "Big Data инженер", "ML-инженер",
                "Специалист по ИИ", "Разработчик ПО",
            ],
            "requirements": {
                "min_gpa": 3.2,
                "exams": ["ЕНТ", "AET (внутренний тест AITU)"],
                "min_ent": 100,
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по информатике/математике", "Проекты по анализу данных"],
            },
            "deadlines": {
                "application_open": "2026-06-20",
                "application_close": "2026-08-24",
                "exam_deadline": "2026-07-10",
                "decision_date": "2026-08-25",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Пороговый балл гранта ~100/140 по группе IT-специальностей (данные 2024/2025, ориентировочно)",
                },
            ],
        },
    ],
    "Kazakh National Academy of Arts named after T. Zhurgenov": [
        # Источник: idandme.kz (постатейный разбор поступления в академию Жургенова),
        # univision.kz/edu-program/group/B031-moda-dizayn.html, fin100.kz (обзор цен по вузам РК).
        # Проверено: 2026-07-03. Стоимость — ориентировочно (официальная цена по программе
        # "Дизайн" на сайте академии не была доступна для парсинга; оценка по соседним
        # программам факультета ~1 000 000 тг/год).
        {
            "name": "Дизайн (бакалавр)",
            "profession_slugs": ["graficheskiy-dizayner"],
            "language": "Казахский / Русский",
            "cost_per_year": 1887,
            "description": (
                "Программа 6B02190 «Дизайн» со специализациями в графическом, интерьерном "
                "и промышленном дизайне. Приём включает обязательный творческий экзамен: "
                "рисунок, живопись и композиция."
            ),
            "who_its_for": (
                "Абитуриенты с художественной подготовкой и портфолио работ, стремящиеся "
                "к карьере в графическом, интерьерном или промышленном дизайне."
            ),
            "career_options": [
                "Графический дизайнер", "Дизайнер интерьера", "Промышленный дизайнер",
                "Арт-директор", "Бренд-дизайнер",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["ЕНТ", "Творческий экзамен (рисунок, живопись, композиция)"],
                "min_ent": 65,
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": True,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Портфолио из 15–20 работ", "Художественная школа", "Конкурсы по дизайну"],
            },
            "deadlines": {
                "application_open": "2026-06-20",
                "application_close": "2026-07-07",
                "exam_deadline": "2026-07-13",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Конкурсный отбор по общей квоте; число грантов на «Дизайн» не подтверждено (ориентировочно)",
                },
            ],
        },
    ],
    "Satbayev University": [
        # Источник: satbayev.university/ru/specialties/arkhitektura,
        # official.satbayev.university/ru/dlya-studentov/stoimost-obucheniya/stoimost-obucheniya-2025-2026,
        # satbayev.university (пороговые баллы по группам ОП бакалавриата 2025). Проверено: 2026-07-03.
        {
            "name": "Архитектура (бакалавр)",
            "profession_slugs": ["arhitektor"],
            "language": "Казахский / Русский",
            "cost_per_year": 2151,
            "description": (
                "Программа группы В073 «Архитектура» — старейшая архитектурная школа "
                "Казахстана, сочетающая проектирование, черчение и градостроительство. "
                "Приём включает творческий экзамен по рисунку и черчению."
            ),
            "who_its_for": (
                "Абитуриенты с развитым пространственным мышлением и навыками черчения, "
                "стремящиеся проектировать здания и городскую среду."
            ),
            "career_options": [
                "Архитектор", "Урбанист", "Архитектурный дизайнер",
                "Руководитель строительных проектов", "BIM-специалист",
            ],
            "requirements": {
                "min_gpa": 3.2,
                "exams": ["ЕНТ", "Творческий экзамен (рисунок, черчение)"],
                "min_ent": 80,
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": True,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Черчение и 3D-моделирование", "Архитектурные кружки"],
            },
            "deadlines": {
                "application_open": "2026-06-20",
                "application_close": "2026-07-13",
                "exam_deadline": "2026-07-13",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Институциональный порог ~80/140; конкурсный отбор (ориентировочно)",
                },
            ],
        },
    ],
    "L.N. Gumilyov Eurasian National University": [
        # Источник: univision.kz/edu-program/64348.html, enu.kz/ru/page/applicants/tuition-fees,
        # lada.kz (обзор цен на обучение в вузах РК на 2025/2026). Проверено: 2026-07-03.
        # Стоимость — ориентировочно (усреднена по диапазону цен ЕНУ на бакалавриат).
        {
            "name": "Экология и природопользование (бакалавр)",
            "profession_slugs": ["inzhener-ekolog"],
            "language": "Казахский / Русский / Английский",
            "cost_per_year": 2547,
            "description": (
                "Программа 6B05208 «Экология и природопользование» готовит специалистов "
                "по мониторингу окружающей среды, охране природы и рациональному "
                "природопользованию. Единственная в списке программа, преподаваемая "
                "на трёх языках, включая английский."
            ),
            "who_its_for": (
                "Студенты, увлечённые природой и экологией, стремящиеся к карьере "
                "в экологическом мониторинге, охране природы или экогосударственных органах."
            ),
            "career_options": [
                "Геоэколог", "Специалист по экологическому мониторингу", "Гидрометеоролог",
                "Специалист по природопользованию", "Инспектор по охране окружающей среды",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["ЕНТ"],
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Экологическое волонтёрство", "Олимпиады по биологии/географии"],
            },
            "deadlines": {
                "application_open": "2026-06-20",
                "application_close": "2026-08-25",
                "exam_deadline": "2026-07-10",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Экология — приоритетное направление госзаказа; точный проходной балл не подтверждён (ориентировочно)",
                },
            ],
        },
    ],
    "Abai Kazakh National Pedagogical University": [
        # Источник: kaznpu.kz/ru/6963/notice (стоимость 2024/2025),
        # univision.kz/edu-program/group/B041-psihologiya.html (порог группы В041),
        # abiturients.kz. Проверено: 2026-07-03. Стоимость подтверждена на 2024/2025 год;
        # цена на 2025/2026 официально ещё не опубликована на момент проверки — ориентировочно.
        {
            "name": "Психология (бакалавр, практический психолог)",
            "profession_slugs": ["psiholog-konsultant"],
            "language": "Казахский / Русский",
            "cost_per_year": 1792,
            "description": (
                "Программа 6B03111 «Подготовка практического психолога» готовит психологов "
                "для работы в школах, консультировании и корпоративной среде."
            ),
            "who_its_for": (
                "Студенты с интересом к психологии человека, эмпатией и желанием помогать "
                "людям, стремящиеся к карьере школьного, клинического или корпоративного психолога."
            ),
            "career_options": [
                "Школьный психолог", "Клинический психолог", "HR-специалист",
                "Психолог-консультант", "Научный сотрудник",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["ЕНТ"],
                "min_ent": 97,
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Волонтёрство", "Психологические кружки/клубы"],
            },
            "deadlines": {
                "application_open": "2026-06-20",
                "application_close": "2026-08-25",
                "exam_deadline": "2026-07-10",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Проходной балл по группе В041 «Психология» ~97/140 (данные 2025 года, ориентировочно)",
                },
            ],
        },
    ],
    "M. Narikbayev KAZGUU University": [
        # Источник: studenthub.kz/university/maqsut_narikbayev_university,
        # studenthub.kz/education_programs/yurisprudentsiya, admission.mnu.kz. Проверено: 2026-07-03.
        # Стоимость — ориентировочно: встречается конфликтующая цифра (9 000 000 тг), вероятно
        # относящаяся к другой/магистерской программе; использована более распространённая
        # оценка 2 500 000 тг/год.
        {
            "name": "Юриспруденция (бакалавр)",
            "profession_slugs": ["yurist-advokat"],
            "language": "Казахский / Русский",
            "cost_per_year": 4717,
            "description": (
                "Программа 6B04201 «Юриспруденция» в ведущем юридическом университете "
                "Казахстана, готовящая юристов и будущих госслужащих в партнёрстве "
                "с зарубежными школами права."
            ),
            "who_its_for": (
                "Абитуриенты с сильными навыками аргументации и работы с текстами, "
                "стремящиеся к карьере юриста, прокурора или государственного служащего."
            ),
            "career_options": [
                "Юрист", "Адвокат", "Юрисконсульт компании",
                "Нотариус", "Специалист по комплаенсу",
            ],
            "requirements": {
                "min_gpa": 3.3,
                "exams": ["ЕНТ"],
                "min_ent": 108,
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Дебаты / модель ООН", "Юридические олимпиады"],
            },
            "deadlines": {
                "application_open": "2026-06-01",
                "application_close": "2026-08-25",
                "exam_deadline": "2026-07-10",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Институциональный порог MNU по специальности ~108/140 (данные 2025 года, ориентировочно)",
                },
            ],
        },
    ],
    "Kazakh Ablai Khan University of International Relations and World Languages": [
        # Источник: ablaikhan.kz (страница программы «Журналистика»),
        # univision.kz/edu-program/52720.html, studenthub.kz/education_programs/zhurnalistika.
        # Проверено: 2026-07-03. Стоимость и проходной балл — ориентировочно (официальный PDF
        # с ценами не был доступен для парсинга).
        {
            "name": "Журналистика (бакалавр)",
            "profession_slugs": ["zhurnalist"],
            "language": "Казахский / Русский / Английский",
            "cost_per_year": 1792,
            "description": (
                "Программа 6B03201 «Журналистика» в ведущем лингвистическом университете "
                "Казахстана. Приём включает творческие испытания — сочинение и собеседование, "
                "помимо результатов ЕНТ."
            ),
            "who_its_for": (
                "Абитуриенты с грамотной письменной и устной речью, интересом к медиа "
                "и обществу, стремящиеся к карьере в журналистике или медиаиндустрии."
            ),
            "career_options": [
                "Журналист", "SMM/контент-менеджер", "PR-специалист",
                "Видеопродюсер", "Пресс-секретарь",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["ЕНТ", "Сочинение", "Собеседование"],
                "min_ent": 50,
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": True,
                "extracurriculars": ["Школьная газета/блог", "Дебаты", "Медиапроекты"],
            },
            "deadlines": {
                "application_open": "2026-06-20",
                "application_close": "2026-08-25",
                "exam_deadline": "2026-07-10",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Проходной балл ~50/140 по данным агрегаторов — вероятно занижен, требует уточнения (ориентировочно)",
                },
            ],
        },
    ],
    "Almaty Management University": [
        # Источник: univision.kz/edu-program/67110.html, er10.kz (обзор цен вузов Алматы),
        # almau.edu.kz/ru/usloviya-postupleniya. Проверено: 2026-07-03. Стоимость — ориентировочно
        # (официальный прайс-лист almau.edu.kz не был доступен для парсинга; встречается
        # альтернативная цифра 2 700 000 тг для смежного трека).
        {
            "name": "Маркетинг (бакалавр)",
            "profession_slugs": ["direktor-po-marketingu"],
            "language": "Казахский / Русский / Английский",
            "cost_per_year": 5472,
            "description": (
                "Программа 6B04104 «Маркетинг» в частном бизнес-университете с сильными "
                "связями с индустрией. При выборе англоязычного трека требуется языковой "
                "сертификат (IELTS 5.5 / TOEFL iBT 87 или внутренний экзамен по языку)."
            ),
            "who_its_for": (
                "Абитуриенты с креативным и аналитическим складом ума, интересом "
                "к брендам и потребительскому поведению, стремящиеся строить карьеру в маркетинге."
            ),
            "career_options": [
                "Маркетолог", "Бренд-менеджер", "Digital/SMM-маркетолог",
                "Аналитик рынка", "Продакт-менеджер",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["ЕНТ"],
                "min_ent": 87,
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Бизнес-кейсы", "SMM/блогинг", "Школьные проекты по маркетингу"],
            },
            "deadlines": {
                "application_open": "2026-06-18",
                "application_close": "2026-08-25",
                "exam_deadline": "2026-07-10",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Проходной балл по группе В047 «Маркетинг и реклама» ~87/140, 9 грантов по РК в 2025 году (ориентировочно)",
                },
            ],
        },
    ],
    "Narxoz University": [
        # Источник: narxoz-promo.kz/ru/management,
        # univision.kz/edu-program/group/B044-menedzhment-i-upravlenie.html,
        # studenthub.kz/university/universitet_narhoz. Проверено: 2026-07-03. Стоимость —
        # ориентировочно (общий диапазон Narxoz 1.3–1.86 млн тг в зависимости от кредитной
        # нагрузки; для трека BBA in Management использована более специфичная цифра 2 322 000 тг).
        {
            "name": "Менеджмент — трек «Управление проектами» (бакалавр, BBA)",
            "profession_slugs": ["predprinimatel"],
            "language": "Английский / Русский / Казахский",
            "cost_per_year": 4381,
            "description": (
                "Программа 6B04101 «Менеджмент» (Школа экономики и менеджмента Narxoz) "
                "с треком «Управление проектами»: планирование проектов, Agile-инструменты, "
                "управление рисками и командой. Не отдельная специальность, а специализация "
                "внутри общей программы менеджмента."
            ),
            "who_its_for": (
                "Абитуриенты со склонностью к планированию и организации, стремящиеся "
                "к карьере проектного или операционного менеджера."
            ),
            "career_options": [
                "Проектный менеджер", "Операционный менеджер", "Бизнес-аналитик",
                "Продакт/программный менеджер", "Менеджер-стажёр в корпорации или стартапе",
            ],
            "requirements": {
                "min_gpa": 3.0,
                "exams": ["ЕНТ"],
                "min_ent": 83,
                "min_ielts": None,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Организация школьных мероприятий", "Бизнес-кейсы", "Стартап-проекты"],
            },
            "deadlines": {
                "application_open": "2026-06-20",
                "application_close": "2026-08-25",
                "exam_deadline": "2026-07-10",
                "decision_date": "2026-08-10",
            },
            "grants": [
                {
                    "name": "Государственный образовательный грант",
                    "amount": "Полная оплата обучения",
                    "conditions": "Проходной балл по группе В044 «Менеджмент и управление» ~83/140, 56 грантов по РК в 2025 году (ориентировочно)",
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------

async def main() -> None:
    async with async_session() as db:
        uni_inserted = uni_updated = uni_skipped = 0
        prog_inserted = prog_updated = prog_skipped = 0

        for uni_data in UNIVERSITIES:
            result = await db.execute(
                select(University).where(University.name == uni_data["name"])
            )
            existing_uni = result.scalar_one_or_none()

            if existing_uni is None:
                existing_uni = University(slug=slugify(uni_data["name"]), **uni_data)
                db.add(existing_uni)
                await db.flush()
                uni_inserted += 1
            else:
                changed = False
                if not existing_uni.slug:
                    existing_uni.slug = slugify(uni_data["name"])
                    changed = True
                for field in ("country", "city", "website", "ranking", "description"):
                    if getattr(existing_uni, field) != uni_data.get(field):
                        setattr(existing_uni, field, uni_data[field])
                        changed = True
                if changed:
                    uni_updated += 1
                else:
                    uni_skipped += 1

            programs = PROGRAMS_BY_UNIVERSITY.get(uni_data["name"], [])
            for prog_data in programs:
                result = await db.execute(
                    select(Program).where(
                        Program.university_id == existing_uni.id,
                        Program.name == prog_data["name"],
                    )
                )
                existing_prog = result.scalar_one_or_none()

                if existing_prog is None:
                    prog = Program(university_id=existing_uni.id, **prog_data)
                    db.add(prog)
                    prog_inserted += 1
                else:
                    changed = False
                    for field in (
                        "profession_slugs", "language", "cost_per_year", "description",
                        "who_its_for", "career_options", "requirements", "deadlines", "grants",
                    ):
                        if getattr(existing_prog, field) != prog_data.get(field):
                            setattr(existing_prog, field, prog_data[field])
                            changed = True
                    if changed:
                        prog_updated += 1
                    else:
                        prog_skipped += 1

        await db.commit()

    total_unis = len(UNIVERSITIES)
    total_progs = sum(len(v) for v in PROGRAMS_BY_UNIVERSITY.values())
    print(
        f"Universities — inserted: {uni_inserted}, updated: {uni_updated}, "
        f"skipped: {uni_skipped}. Total in bank: {total_unis}"
    )
    print(
        f"Programs — inserted: {prog_inserted}, updated: {prog_updated}, "
        f"skipped: {prog_skipped}. Total in bank: {total_progs}"
    )


if __name__ == "__main__":
    asyncio.run(main())
