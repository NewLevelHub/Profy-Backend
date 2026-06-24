"""
Seed script: populate universities and programs tables.
Run inside Docker: docker-compose exec api python scripts/seed_universities.py
Idempotent: upserts by university name; upserts programs by (university_id, name).
Coverage: KZ, USA, UK, Europe, Canada, Asia — 20 universities, 40+ programs.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university import University

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
    # --- США ---
    {
        "name": "Massachusetts Institute of Technology",
        "country": "США",
        "city": "Кембридж",
        "website": "https://mit.edu",
        "ranking": 1,
        "description": (
            "Всемирно известный исследовательский университет, стабильно занимающий 1-е место в мире, "
            "известный в области инженерии, вычислительных технологий и науки."
        ),
    },
    {
        "name": "Stanford University",
        "country": "США",
        "city": "Стэнфорд",
        "website": "https://stanford.edu",
        "ranking": 3,
        "description": (
            "Элитный частный исследовательский университет в Кремниевой долине — "
            "центр предпринимательства, технологий и инноваций."
        ),
    },
    {
        "name": "University of California, Berkeley",
        "country": "США",
        "city": "Беркли",
        "website": "https://berkeley.edu",
        "ranking": 10,
        "description": (
            "Ведущий государственный исследовательский университет США с выдающимися программами "
            "в области информатики, инженерии и науки о данных."
        ),
    },
    {
        "name": "New York University",
        "country": "США",
        "city": "Нью-Йорк",
        "website": "https://nyu.edu",
        "ranking": 55,
        "description": (
            "Глобальный частный университет в сердце Нью-Йорка, предлагающий "
            "программы мирового класса в области технологий, бизнеса и искусства."
        ),
    },
    # --- Великобритания ---
    {
        "name": "University College London",
        "country": "Великобритания",
        "city": "Лондон",
        "website": "https://ucl.ac.uk",
        "ranking": 9,
        "description": (
            "Ведущий многопрофильный университет Лондона, входящий в мировую топ-10, "
            "с сильными направлениями в науке, инженерии и социальных науках."
        ),
    },
    {
        "name": "University of Edinburgh",
        "country": "Великобритания",
        "city": "Эдинбург",
        "website": "https://ed.ac.uk",
        "ranking": 22,
        "description": (
            "Один из ведущих мировых университетов, основанный в 1583 году, "
            "с особенно сильными программами в области информатики и ИИ."
        ),
    },
    {
        "name": "University of Manchester",
        "country": "Великобритания",
        "city": "Манчестер",
        "website": "https://manchester.ac.uk",
        "ranking": 32,
        "description": (
            "Исследовательский университет группы Russell с сильными традициями "
            "в области информатики, науки о данных и инженерии."
        ),
    },
    # --- Европа ---
    {
        "name": "Delft University of Technology",
        "country": "Нидерланды",
        "city": "Делфт",
        "website": "https://tudelft.nl",
        "ranking": 57,
        "description": (
            "Ведущий технический университет Нидерландов и Европы, "
            "известный в области инженерии, дизайна и прикладных наук."
        ),
    },
    {
        "name": "Ludwig Maximilian University of Munich",
        "country": "Германия",
        "city": "Мюнхен",
        "website": "https://lmu.de",
        "ranking": 38,
        "description": (
            "Один из старейших и наиболее престижных университетов Германии, "
            "предлагающий бесплатное обучение по программам информатики."
        ),
    },
    {
        "name": "ETH Zurich",
        "country": "Швейцария",
        "city": "Цюрих",
        "website": "https://ethz.ch",
        "ranking": 7,
        "description": (
            "Ведущий швейцарский университет науки и технологий, стабильно "
            "входящий в мировую топ-10 в области инженерии и вычислений."
        ),
    },
    {
        "name": "EPFL",
        "country": "Швейцария",
        "city": "Лозанна",
        "website": "https://epfl.ch",
        "ranking": 19,
        "description": (
            "École Polytechnique Fédérale de Lausanne — один из наиболее инновационных "
            "технических университетов Европы, известный в области информатики и науки о данных."
        ),
    },
    # --- Канада ---
    {
        "name": "University of Toronto",
        "country": "Канада",
        "city": "Торонто",
        "website": "https://utoronto.ca",
        "ranking": 21,
        "description": (
            "Лучший университет Канады с отделением информатики мирового уровня, "
            "ставшим пионером в исследованиях глубокого обучения."
        ),
    },
    {
        "name": "University of British Columbia",
        "country": "Канада",
        "city": "Ванкувер",
        "website": "https://ubc.ca",
        "ranking": 34,
        "description": (
            "Ведущий канадский исследовательский университет с сильными программами "
            "в области информатики, науки о данных и инженерии."
        ),
    },
    # --- Азия ---
    {
        "name": "National University of Singapore",
        "country": "Сингапур",
        "city": "Сингапур",
        "website": "https://nus.edu.sg",
        "ranking": 8,
        "description": (
            "Лучший университет Азии, стабильно входящий в мировую топ-10, "
            "с выдающимися программами в области вычислений и бизнеса."
        ),
    },
    {
        "name": "KAIST",
        "country": "Южная Корея",
        "city": "Тэджон",
        "website": "https://kaist.ac.kr",
        "ranking": 42,
        "description": (
            "Корейский передовой институт науки и технологий — ведущий STEM-университет "
            "Азии, предлагающий программы полностью на английском языке."
        ),
    },
    {
        "name": "Imperial College London",
        "country": "Великобритания",
        "city": "Лондон",
        "website": "https://imperial.ac.uk",
        "ranking": 6,
        "description": (
            "Университет мирового уровня в области науки, инженерии, медицины и бизнеса "
            "в центре Лондона, входящий в мировую топ-10."
        ),
    },
    {
        "name": "Seoul National University",
        "country": "Южная Корея",
        "city": "Сеул",
        "website": "https://snu.ac.kr",
        "ranking": 31,
        "description": (
            "Самый престижный университет Южной Кореи с сильными программами "
            "в области инженерии, вычислений и естественных наук."
        ),
    },
]

# Programs keyed by university name → list of program dicts
PROGRAMS_BY_UNIVERSITY: dict[str, list[dict]] = {
    "Nazarbayev University": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
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
            "direction_slug": "data-science",
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
            "direction_slug": "business-entrepreneurship",
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
            "direction_slug": "finance-economics",
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
            "direction_slug": "it-development",
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
            "direction_slug": "medicine-biology",
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
    ],
    "Massachusetts Institute of Technology": [
        {
            "name": "Информатика и инженерия (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 59750,
            "description": (
                "Флагманская программа бакалавриата MIT (Курс 6), охватывающая алгоритмы, "
                "системы, ИИ и разработку ПО под руководством ведущих мировых преподавателей."
            ),
            "who_its_for": (
                "Исключительно талантливые студенты с доказанной страстью к инженерии "
                "и решению задач, стремящиеся формировать будущее технологий."
            ),
            "career_options": [
                "Инженер-программист", "Учёный-исследователь", "Предприниматель",
                "Системный архитектор", "Инженер по ИИ/МО",
            ],
            "requirements": {
                "min_gpa": 3.9,
                "exams": ["SAT", "ACT", "AP"],
                "min_ielts": 7.0,
                "min_sat": 1570,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": [
                    "USACO / международная олимпиада по программированию",
                    "Исследовательские проекты или публикации",
                    "Олимпиада по науке / математические соревнования",
                ],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2026-01-01",
                "exam_deadline": "2025-12-01",
                "decision_date": "2026-03-14",
            },
            "grants": [
                {
                    "name": "Финансовая помощь MIT на основе нуждаемости",
                    "amount": "До полной стоимости обучения",
                    "conditions": "На основе дохода семьи; семьи с доходом менее $140 тыс. не платят ничего",
                },
            ],
        },
        {
            "name": "Электроинженерия и информатика (магистр инженерии)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 62000,
            "description": (
                "Совмещённая программа BS/MEng MIT, позволяющая бакалаврам получить "
                "степень магистра за 5 лет, охватывая передовые вычисления и электросистемы."
            ),
            "who_its_for": (
                "Студенты MIT, стремящиеся к углублённой технической подготовке в области "
                "аппаратного обеспечения, ПО и систем перед выходом на рынок или поступлением в докторантуру."
            ),
            "career_options": [
                "Инженер по аппаратному обеспечению", "Разработчик микросхем", "Системный инженер",
                "Учёный-исследователь", "Технический директор",
            ],
            "requirements": {
                "min_gpa": 4.0,
                "exams": ["GRE"],
                "min_ielts": 7.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Исследовательская программа MIT (UROP)", "Опубликованные работы"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-02-01",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-01",
            },
            "grants": [
                {
                    "name": "Ассистентство MIT (преподавание/исследования)",
                    "amount": "Оплата обучения + стипендия ~$40 тыс./год",
                    "conditions": "Конкурсный отбор; присуждается кафедрой",
                },
            ],
        },
    ],
    "Stanford University": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 62484,
            "description": (
                "Программа CS Стэнфорда даёт уникальный доступ к индустрии Кремниевой долины "
                "и передовым исследованиям в области систем, ИИ и HCI."
            ),
            "who_its_for": (
                "Лучшие студенты с сильной академической подготовкой и предпринимательским духом, "
                "желающие создавать продукты или проводить исследования на переднем крае вычислений."
            ),
            "career_options": [
                "Инженер-программист", "Продакт-менеджер", "Основатель стартапа",
                "Исследователь ИИ", "Технический лидер",
            ],
            "requirements": {
                "min_gpa": 3.9,
                "exams": ["SAT", "ACT"],
                "min_ielts": 7.0,
                "min_sat": 1550,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": [
                    "Соревновательное программирование (ICPC, IOI)",
                    "Побочные проекты или стартапы",
                    "Исследовательские стажировки",
                ],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2026-01-02",
                "exam_deadline": "2025-12-06",
                "decision_date": "2026-03-30",
            },
            "grants": [
                {
                    "name": "Финансовая помощь Stanford на основе нуждаемости",
                    "amount": "До полной стоимости обучения",
                    "conditions": "Семьи с доходом менее $150 тыс. не платят ничего",
                },
            ],
        },
        {
            "name": "Искусственный интеллект (магистр)",
            "direction_slug": "artificial-intelligence",
            "language": "Английский",
            "cost_per_year": 63450,
            "description": (
                "Магистерская программа по ИИ Стэнфорда охватывает машинное обучение, глубокое "
                "обучение, NLP, компьютерное зрение и робототехнику с доступом к лабораториям мирового класса."
            ),
            "who_its_for": (
                "Выпускники по CS, желающие углубить экспертизу в исследованиях ИИ или "
                "войти в ИИ-индустрию в компаниях Google, OpenAI или ведущих стартапах."
            ),
            "career_options": [
                "ML-инженер", "Исследователь ИИ", "NLP-инженер",
                "Инженер по компьютерному зрению", "ИИ-продакт-менеджер",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["GRE", "TOEFL", "IELTS"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": [
                    "Публикации или препринты по исследованиям МО",
                    "Высокие позиции на Kaggle",
                    "Вклад в открытый ИИ",
                ],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2025-12-04",
                "exam_deadline": "2025-11-30",
                "decision_date": "2026-03-15",
            },
            "grants": [
                {
                    "name": "Стипендия Stanford",
                    "amount": "Полная оплата обучения + стипендия $45 тыс.",
                    "conditions": "Конкурсный отбор; лучшие соискатели получают финансирование",
                },
            ],
        },
    ],
    "University of California, Berkeley": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 44066,
            "description": (
                "Программа EECS/CS Беркли — одна из лучших в мире, обеспечивающая "
                "строгую теоретическую подготовку и тесные связи с индустрией Залива."
            ),
            "who_its_for": (
                "Целеустремлённые студенты, ищущие образование CS мирового класса в государственном "
                "исследовательском университете с близкими связями с компаниями Кремниевой долины."
            ),
            "career_options": [
                "Инженер-программист", "Full-stack разработчик", "Системный инженер",
                "Продакт-менеджер", "Инженер-исследователь",
            ],
            "requirements": {
                "min_gpa": 3.8,
                "exams": ["SAT", "ACT"],
                "min_ielts": 6.5,
                "min_sat": 1500,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": [
                    "USACO или соревновательное программирование",
                    "Вклад в open-source",
                    "Победы на хакатонах",
                ],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2025-11-30",
                "exam_deadline": "2025-11-30",
                "decision_date": "2026-03-31",
            },
            "grants": [
                {
                    "name": "Грант Cal",
                    "amount": "До $15 000/год",
                    "conditions": "Для жителей Калифорнии по финансовой нуждаемости",
                },
                {
                    "name": "Глобальная премия Berkeley",
                    "amount": "$10 000/год",
                    "conditions": "Иностранные абитуриенты с выдающейся успеваемостью",
                },
            ],
        },
        {
            "name": "Наука о данных (бакалавр)",
            "direction_slug": "data-science",
            "language": "Английский",
            "cost_per_year": 44066,
            "description": (
                "Междисциплинарная программа Data Science Беркли сочетает статистику, "
                "вычисления и предметные знания для подготовки специалистов по данным."
            ),
            "who_its_for": (
                "Студенты, которые любят работать с данными, статистикой и программированием "
                "и хотят решать реальные задачи в различных отраслях."
            ),
            "career_options": [
                "Специалист по данным", "Аналитик данных", "ML-инженер",
                "Аналитик-исследователь", "Инженер данных",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["SAT", "ACT"],
                "min_ielts": 6.5,
                "min_sat": 1480,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Соревнования на Kaggle", "Статистические проекты", "Дата-хакатоны"],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2025-11-30",
                "exam_deadline": "2025-11-30",
                "decision_date": "2026-03-31",
            },
            "grants": [
                {
                    "name": "Грант Cal",
                    "amount": "До $15 000/год",
                    "conditions": "Для жителей Калифорнии по финансовой нуждаемости",
                },
            ],
        },
    ],
    "New York University": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 58168,
            "description": (
                "Программа CS NYU Tandon в сердце Нью-Йорка с сильными связями "
                "с индустрией и возможностями для исследований."
            ),
            "who_its_for": (
                "Студенты, желающие изучать CS в глобальном городе с доступом "
                "к процветающей технологической сцене, стартапам и финансовой индустрии NYC."
            ),
            "career_options": [
                "Разработчик ПО", "Full-stack инженер", "DevOps-инженер",
                "Инженер данных", "Аналитик по кибербезопасности",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["SAT", "ACT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1400,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Хакатоны", "Программистские клубы", "Исследовательские проекты"],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2026-01-01",
                "exam_deadline": "2025-12-15",
                "decision_date": "2026-03-20",
            },
            "grants": [
                {
                    "name": "Стипендия NYU",
                    "amount": "До $25 000/год",
                    "conditions": "По заслугам, конкурсный отбор",
                },
            ],
        },
        {
            "name": "Бизнес (BBA — Школа Стерна)",
            "direction_slug": "business-entrepreneurship",
            "language": "Английский",
            "cost_per_year": 58168,
            "description": (
                "Программа бакалавриата по бизнесу NYU Stern — одна из наиболее престижных "
                "в мире, расположенная в финансовом квартале Нью-Йорка."
            ),
            "who_its_for": (
                "Будущие бизнес-лидеры, предприниматели и финансовые специалисты, "
                "стремящиеся к доступу к Уолл-стрит и глобальным деловым сетям."
            ),
            "career_options": [
                "Инвестиционный банкир", "Консультант по управлению", "Предприниматель",
                "Продакт-менеджер", "Директор по маркетингу",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["SAT", "ACT", "IELTS", "TOEFL"],
                "min_ielts": 7.0,
                "min_sat": 1500,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": [
                    "Соревнования по бизнес-кейсам",
                    "Предпринимательские клубы",
                    "Инвестиционные клубы",
                ],
            },
            "deadlines": {
                "application_open": "2025-08-01",
                "application_close": "2026-01-01",
                "exam_deadline": "2025-12-15",
                "decision_date": "2026-03-20",
            },
            "grants": [
                {
                    "name": "Стипендия Stern за лидерство",
                    "amount": "$20 000/год",
                    "conditions": "Лучшие абитуриенты, заслуги и лидерство",
                },
            ],
        },
    ],
    "University College London": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 35000,
            "description": (
                "Программа CS UCL в центре Лондона охватывает алгоритмы, разработку ПО, "
                "ИИ и безопасность с сильными связями с индустрией."
            ),
            "who_its_for": (
                "Иностранные студенты, желающие получить опыт в ведущем лондонском университете "
                "в сочетании с глубокой технической подготовкой и глобальными карьерными перспективами."
            ),
            "career_options": [
                "Инженер-программист", "ИИ-инженер", "Аналитик по кибербезопасности",
                "Бэкенд-разработчик", "Учёный-исследователь",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по математике/информатике", "Личные проекты"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Глобальная стипендия UCL для бакалавров",
                    "amount": "£5 000/год",
                    "conditions": "Иностранные студенты с выдающейся успеваемостью",
                },
            ],
        },
        {
            "name": "Нейронауки (бакалавр)",
            "direction_slug": "medicine-biology",
            "language": "Английский",
            "cost_per_year": 35000,
            "description": (
                "UCL — один из ведущих мировых центров нейронаук; программа охватывает "
                "функции мозга, когнитивные науки и нейрологические расстройства."
            ),
            "who_its_for": (
                "Студенты, увлечённые мозгом и сознанием, желающие заниматься "
                "исследованиями, медициной или карьерой в клинической нейронауке."
            ),
            "career_options": [
                "Нейроучёный", "Клинический исследователь", "Психиатр",
                "Когнитивный учёный", "Биотех-специалист",
            ],
            "requirements": {
                "min_gpa": 3.8,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Олимпиады по биологии/химии", "Волонтёрство в лабораториях"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Глобальная стипендия UCL для бакалавров",
                    "amount": "£5 000/год",
                    "conditions": "Иностранные студенты с выдающейся успеваемостью",
                },
            ],
        },
    ],
    "University of Edinburgh": [
        {
            "name": "Информатика (бакалавр / бакалавр инженерии)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 26500,
            "description": (
                "Школа информатики Эдинбурга — крупнейший факультет информатики Европы, "
                "предлагающий программы мирового класса в области CS, ИИ и когнитивных наук."
            ),
            "who_its_for": (
                "Студенты, желающие получить широкую подготовку в области вычислений, ИИ "
                "и когнитивных наук в одном из наиболее инновационных университетов Великобритании."
            ),
            "career_options": [
                "Инженер-программист", "ИИ-инженер", "Специалист по данным",
                "UX-исследователь", "Учёный-исследователь",
            ],
            "requirements": {
                "min_gpa": 3.6,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по математике/информатике", "Соревнования по программированию"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-05-01",
            },
            "grants": [
                {
                    "name": "Глобальная исследовательская стипендия Edinburgh",
                    "amount": "£10 000 (единовременно)",
                    "conditions": "Выдающаяся успеваемость для иностранных студентов",
                },
            ],
        },
        {
            "name": "Искусственный интеллект (магистр)",
            "direction_slug": "artificial-intelligence",
            "language": "Английский",
            "cost_per_year": 28500,
            "description": (
                "Годичная магистерская программа по ИИ в Эдинбурге охватывает машинное обучение, "
                "NLP, компьютерное зрение и планирование ИИ от ведущей мировой школы ИИ."
            ),
            "who_its_for": (
                "Выпускники CS или инженерных специальностей, желающие специализироваться в ИИ "
                "и войти в быстрорастущую ИИ-индустрию или продолжить учёбу в докторантуре."
            ),
            "career_options": [
                "ML-инженер", "Исследователь ИИ", "NLP-учёный",
                "Инженер по компьютерному зрению", "ИИ-консультант",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["ML-проекты на GitHub", "Соревнования на Kaggle", "Научные статьи"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-03-31",
                "exam_deadline": "2026-03-01",
                "decision_date": "2026-05-15",
            },
            "grants": [
                {
                    "name": "Стипендия факультета информатики",
                    "amount": "£5 000",
                    "conditions": "Академические заслуги, ограниченное число мест",
                },
            ],
        },
    ],
    "University of Manchester": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 26500,
            "description": (
                "Программа CS Манчестера охватывает разработку ПО, алгоритмы, сети "
                "и ИИ с отличными возможностями промышленного трудоустройства."
            ),
            "who_its_for": (
                "Студенты, желающие получить разностороннее образование в области CS "
                "в крупном городе Великобритании с отличными результатами трудоустройства."
            ),
            "career_options": [
                "Разработчик ПО", "Системный аналитик", "DevOps-инженер",
                "ИИ-инженер", "IT-консультант",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Проекты по программированию", "Хакатоны"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Премия Manchester за глобальное превосходство",
                    "amount": "£2 000–£5 000",
                    "conditions": "Иностранные студенты, академические заслуги",
                },
            ],
        },
        {
            "name": "Наука о данных (магистр)",
            "direction_slug": "data-science",
            "language": "Английский",
            "cost_per_year": 27500,
            "description": (
                "Годичная магистерская программа, охватывающая машинное обучение, аналитику больших данных, "
                "инженерию данных и статистическое моделирование с отраслевым проектом."
            ),
            "who_its_for": (
                "Выпускники STEM-специальностей, желающие перейти "
                "на должности специалистов по данным в индустрии или науке."
            ),
            "career_options": [
                "Специалист по данным", "ML-инженер", "Аналитик данных",
                "BI-аналитик", "Инженер данных",
            ],
            "requirements": {
                "min_gpa": 3.3,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Проекты с данными", "Kaggle", "Опыт работы с Python/R"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-06-30",
                "exam_deadline": "2026-06-01",
                "decision_date": "2026-07-31",
            },
            "grants": [
                {
                    "name": "Стипендия Manchester для аспирантов",
                    "amount": "£3 000",
                    "conditions": "По заслугам",
                },
            ],
        },
    ],
    "Delft University of Technology": [
        {
            "name": "Информатика и инженерия (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 11170,
            "description": (
                "Программа CS&E TU Delft в Нидерландах сочетает глубокие основы "
                "разработки ПО с практическим проектированием и исследованиями."
            ),
            "who_its_for": (
                "Студенты, желающие получить ведущее европейское техническое образование "
                "по доступной цене с сильными связями с нидерландской и мировой IT-индустрией."
            ),
            "career_options": [
                "Инженер-программист", "Системный разработчик", "Инженер-исследователь",
                "Продуктовый инженер", "Инженер данных",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["IELTS", "TOEFL", "SAT"],
                "min_ielts": 6.5,
                "min_sat": 1350,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по математике/информатике", "Проекты по программированию"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-01",
                "decision_date": "2026-04-01",
            },
            "grants": [
                {
                    "name": "Стипендия Holland",
                    "amount": "€5 000 (единовременно)",
                    "conditions": "Студенты не из ЕС с выдающейся успеваемостью",
                },
                {
                    "name": "Стипендия TU Delft за превосходство",
                    "amount": "Полная оплата обучения + €12 000/год на проживание",
                    "conditions": "Топ 5% абитуриентов в мире",
                },
            ],
        },
        {
            "name": "Компьютерная инженерия (магистр)",
            "direction_slug": "engineering-architecture",
            "language": "Английский",
            "cost_per_year": 18750,
            "description": (
                "Магистерская программа TU Delft по компьютерной инженерии охватывает "
                "встроенные системы, архитектуру компьютеров и совместное проектирование аппаратного и программного обеспечения."
            ),
            "who_its_for": (
                "Выпускники инженерных специальностей, интересующиеся низкоуровневыми системами, "
                "встроенными вычислениями и проектированием аппаратного обеспечения."
            ),
            "career_options": [
                "Инженер встроенных систем", "Инженер по аппаратному обеспечению", "Системный архитектор",
                "FPGA-разработчик", "IoT-инженер",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Проекты по электронике", "Робототехнические клубы"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-04-01",
                "exam_deadline": "2026-03-01",
                "decision_date": "2026-05-15",
            },
            "grants": [
                {
                    "name": "Стипендия Holland",
                    "amount": "€5 000 (единовременно)",
                    "conditions": "Студенты не из ЕС",
                },
            ],
        },
    ],
    "Ludwig Maximilian University of Munich": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Немецкий / Английский",
            "cost_per_year": 258,
            "description": (
                "Программа CS LMU Мюнхен практически бесплатна (только семестровые взносы), "
                "предлагая сильную теоретическую подготовку и возможности для исследований."
            ),
            "who_its_for": (
                "Студенты, желающие получить образование CS мирового класса почти бесплатно "
                "и готовые учить немецкий язык или обучаться на английском треке."
            ),
            "career_options": [
                "Инженер-программист", "Учёный-исследователь", "Бэкенд-разработчик",
                "Системный программист", "Инженер по алгоритмам",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["TestDaF", "IELTS", "Abitur / IB"],
                "min_ielts": 6.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Математические олимпиады", "Проекты по программированию"],
            },
            "deadlines": {
                "application_open": "2026-05-01",
                "application_close": "2026-07-15",
                "exam_deadline": "2026-06-30",
                "decision_date": "2026-08-15",
            },
            "grants": [
                {
                    "name": "Стипендия DAAD",
                    "amount": "€850/мес + дорожные расходы",
                    "conditions": "Иностранные студенты, конкурсная успеваемость",
                },
            ],
        },
        {
            "name": "Информатика (магистр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 258,
            "description": (
                "Совместная магистерская программа LMU + TU Мюнхен по информатике — "
                "одна из наиболее престижных аспирантских CS-программ Германии, практически бесплатная."
            ),
            "who_its_for": (
                "Иностранные выпускники, стремящиеся к исследовательской магистратуре в Европе "
                "без оплаты за обучение, с возможностями в ведущих немецких IT-компаниях."
            ),
            "career_options": [
                "Инженер-исследователь", "ML-инженер", "Архитектор ПО",
                "Аспирант", "ИИ-учёный",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Исследовательские проекты", "Портфолио на GitHub", "Публикации"],
            },
            "deadlines": {
                "application_open": "2025-11-15",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-01",
                "decision_date": "2026-03-31",
            },
            "grants": [
                {
                    "name": "Стипендия DAAD",
                    "amount": "€850/мес",
                    "conditions": "Иностранные выпускники, по заслугам",
                },
            ],
        },
    ],
    "ETH Zurich": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Немецкий",
            "cost_per_year": 730,
            "description": (
                "Программа CS ETH Zurich — одна из лучших в мире, предлагающая "
                "строгую подготовку в области алгоритмов, систем и ИИ практически бесплатно."
            ),
            "who_its_for": (
                "Лучшие студенты с исключительными математическими способностями, желающие "
                "получить образование мирового класса в одном из самых безопасных городов Европы."
            ),
            "career_options": [
                "Инженер-программист", "Инженер по алгоритмам", "Учёный-исследователь",
                "Системный архитектор", "Квант-разработчик",
            ],
            "requirements": {
                "min_gpa": 3.8,
                "exams": ["Matura", "IB", "TestDaF"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": True,
                "extracurriculars": ["Олимпиады по математике/информатике", "Высокая успеваемость"],
            },
            "deadlines": {
                "application_open": "2025-11-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-05-01",
            },
            "grants": [
                {
                    "name": "Стипендия ETH за превосходство",
                    "amount": "CHF 12 000/год + освобождение от платы за обучение",
                    "conditions": "Лучшие соискатели MSc, конкурсный отбор",
                },
            ],
        },
        {
            "name": "Наука о данных (магистр)",
            "direction_slug": "data-science",
            "language": "Английский",
            "cost_per_year": 730,
            "description": (
                "Магистерская программа ETH по науке о данных охватывает МО, статистику, "
                "системы больших данных и междисциплинарные приложения. Преподавание полностью на английском."
            ),
            "who_its_for": (
                "Выпускники STEM, желающие получить ведущее образование в области науки о данных "
                "в Европе при минимальной стоимости обучения с отличными карьерными перспективами."
            ),
            "career_options": [
                "Специалист по данным", "ML-исследователь", "Количественный аналитик",
                "ИИ-инженер", "Инженер данных",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["ML-исследовательские проекты", "Публикации", "Высокие позиции на Kaggle"],
            },
            "deadlines": {
                "application_open": "2025-11-01",
                "application_close": "2025-12-15",
                "exam_deadline": "2025-12-01",
                "decision_date": "2026-04-15",
            },
            "grants": [
                {
                    "name": "Стипендия ETH за превосходство",
                    "amount": "CHF 12 000/год + освобождение от платы за обучение",
                    "conditions": "Лучшие соискатели MSc, конкурсный отбор",
                },
            ],
        },
    ],
    "EPFL": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Французский / Английский",
            "cost_per_year": 730,
            "description": (
                "Программа CS EPFL — одна из лучших в Европе, известная строгостью "
                "в области алгоритмов, теории программирования и междисциплинарных проектов."
            ),
            "who_its_for": (
                "Высокомотивированные студенты, стремящиеся к строгой и сложной среде обучения "
                "и желающие получить швейцарское инженерное образование мирового класса."
            ),
            "career_options": [
                "Инженер-программист", "Инженер-исследователь", "Блокчейн-разработчик",
                "Системный программист", "Продуктовый инженер",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["Maturité", "IB", "IELTS"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": False,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по математике/информатике", "Робототехнические проекты"],
            },
            "deadlines": {
                "application_open": "2026-01-15",
                "application_close": "2026-04-30",
                "exam_deadline": "2026-04-01",
                "decision_date": "2026-06-01",
            },
            "grants": [
                {
                    "name": "Стипендия EPFL за превосходство",
                    "amount": "CHF 20 000/год",
                    "conditions": "Лучшие соискатели MSc из любой страны",
                },
            ],
        },
        {
            "name": "Наука о данных (магистр)",
            "direction_slug": "data-science",
            "language": "Английский",
            "cost_per_year": 730,
            "description": (
                "Двухлетняя магистерская программа EPFL по науке о данных, сочетающая "
                "машинное обучение, прикладную математику и крупномасштабные системы данных."
            ),
            "who_its_for": (
                "Сильные количественные выпускники, желающие решать сложные задачи с данными "
                "и получить доступ к исследовательской экосистеме мирового класса EPFL."
            ),
            "career_options": [
                "Специалист по данным", "ML-инженер", "Прикладной исследователь",
                "Квант-разработчик", "ИИ-продакт-менеджер",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Соревнования на Kaggle", "Исследовательские стажировки", "Open-source ML"],
            },
            "deadlines": {
                "application_open": "2025-10-15",
                "application_close": "2025-12-15",
                "exam_deadline": "2025-12-01",
                "decision_date": "2026-03-31",
            },
            "grants": [
                {
                    "name": "Стипендия EPFL за превосходство",
                    "amount": "CHF 20 000/год",
                    "conditions": "Лучшие соискатели MSc из любой страны",
                },
            ],
        },
    ],
    "University of Toronto": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 47260,
            "description": (
                "Программа CS UofT — родина пионеров глубокого обучения Хинтона, ЛеКуна и Бенжио — "
                "предлагает исследовательские возможности мирового уровня в области ИИ, систем и теории."
            ),
            "who_its_for": (
                "Студенты, желающие изучать CS там, где было изобретено глубокое обучение, "
                "с доступом к ведущим исследовательским лабораториям и технологическому хабу Торонто."
            ),
            "career_options": [
                "Инженер-программист", "ML-исследователь", "ИИ-инженер",
                "Учёный-исследователь", "Технологический предприниматель",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1400,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Соревнования по информатике", "Исследовательские проекты", "Хакатоны"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-13",
                "exam_deadline": "2026-01-01",
                "decision_date": "2026-05-01",
            },
            "grants": [
                {
                    "name": "Международная стипендия Lester B. Pearson",
                    "amount": "Полная оплата обучения + расходы на проживание",
                    "conditions": "Лучшие иностранные студенты, исключительная академическая успеваемость и лидерство",
                },
                {
                    "name": "Программа стипендиатов Университета Торонто",
                    "amount": "$7 500/год",
                    "conditions": "Лучшие поступающие студенты",
                },
            ],
        },
        {
            "name": "Искусственный интеллект (магистр)",
            "direction_slug": "artificial-intelligence",
            "language": "Английский",
            "cost_per_year": 21890,
            "description": (
                "Магистерская программа UofT по прикладным вычислениям со специализацией в ИИ — "
                "годичная отраслевая программа в родине современного глубокого обучения."
            ),
            "who_its_for": (
                "Выпускники CS, желающие создавать ИИ-системы для индустрии "
                "и воспользоваться непревзойдённой экосистемой исследований глубокого обучения UofT."
            ),
            "career_options": [
                "ML-инженер", "Исследователь ИИ", "Инженер глубокого обучения",
                "NLP-инженер", "Прикладной учёный",
            ],
            "requirements": {
                "min_gpa": 3.5,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["ML-проекты", "Kaggle", "Стажировки в области ИИ"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-02-01",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-15",
            },
            "grants": [
                {
                    "name": "Стипендия для аспирантов Онтарио",
                    "amount": "CAD $15 000",
                    "conditions": "Академические заслуги",
                },
            ],
        },
    ],
    "University of British Columbia": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 40310,
            "description": (
                "Программа CS UBC в живописном Ванкувере предлагает сильную базовую подготовку, "
                "специализации в ИИ и отличные возможности кооперативной работы."
            ),
            "who_its_for": (
                "Студенты, желающие получить лучшую канадскую степень CS с доступом "
                "к стажировкам в крупных IT-компаниях и технологической сцене Ванкувера."
            ),
            "career_options": [
                "Разработчик ПО", "Инженер данных", "ИИ-инженер",
                "Full-stack разработчик", "Продакт-менеджер",
            ],
            "requirements": {
                "min_gpa": 3.6,
                "exams": ["SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1380,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": False,
                "needs_interview": False,
                "extracurriculars": ["Программистские клубы", "Хакатоны", "Научные ярмарки"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-01",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Международная вступительная стипендия",
                    "amount": "$10 000–$40 000",
                    "conditions": "Лучшие иностранные студенты по академической успеваемости",
                },
            ],
        },
        {
            "name": "Наука о данных (магистр)",
            "direction_slug": "data-science",
            "language": "Английский",
            "cost_per_year": 9690,
            "description": (
                "Интенсивная 10-месячная магистерская программа UBC по науке о данных, "
                "охватывающая статистическое обучение, МО и визуализацию данных."
            ),
            "who_its_for": (
                "Количественные выпускники, желающие быстро перейти "
                "на должности специалистов по данным в процветающей технологической экосистеме Канады."
            ),
            "career_options": [
                "Специалист по данным", "ML-инженер", "Аналитик данных",
                "Аналитик-исследователь", "BI-аналитик",
            ],
            "requirements": {
                "min_gpa": 3.3,
                "exams": ["IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Проекты с данными", "Опыт работы с Python/R", "Курсы по статистике"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-02-28",
                "exam_deadline": "2026-02-01",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Аспирантская премия UBC",
                    "amount": "CAD $6 000",
                    "conditions": "Академические заслуги",
                },
            ],
        },
    ],
    "National University of Singapore": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 17550,
            "description": (
                "CS NUS — программа с наивысшим рейтингом в Азии, предлагающая специализации "
                "в ИИ, разработке ПО, безопасности и мультимедиа в учреждении мирового класса."
            ),
            "who_its_for": (
                "Студенты из Азии и всего мира, желающие получить элитное образование в CS "
                "с доступом к процветающей IT-индустрии Сингапура."
            ),
            "career_options": [
                "Инженер-программист", "ИИ-инженер", "Аналитик по кибербезопасности",
                "Full-stack разработчик", "Учёный-исследователь",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["A-Levels", "IB", "SAT", "IELTS"],
                "min_ielts": 6.5,
                "min_sat": 1450,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по программированию", "Исследовательские проекты", "Хакатоны"],
            },
            "deadlines": {
                "application_open": "2025-10-01",
                "application_close": "2026-02-28",
                "exam_deadline": "2026-02-01",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Стипендия ASEAN для бакалавров",
                    "amount": "Полная оплата обучения + надбавка на проживание",
                    "conditions": "Граждане стран ASEAN с выдающейся успеваемостью",
                },
                {
                    "name": "Учебная премия NUS",
                    "amount": "SGD $5 000",
                    "conditions": "Иностранные студенты с финансовой нуждаемостью",
                },
            ],
        },
        {
            "name": "Бизнес-аналитика (магистр)",
            "direction_slug": "data-science",
            "language": "Английский",
            "cost_per_year": 37000,
            "description": (
                "Годичная магистерская программа NUS по бизнес-аналитике сочетает науку о данных, "
                "аналитику и бизнес-стратегию для подготовки аналитиков, готовых к работе в индустрии."
            ),
            "who_its_for": (
                "Выпускники любой специальности, желающие сочетать навыки работы с данными "
                "с деловой хваткой и работать в организациях, управляемых аналитикой."
            ),
            "career_options": [
                "Бизнес-аналитик", "Аналитик данных", "Аналитический консультант",
                "Менеджер BI", "Стратегический аналитик",
            ],
            "requirements": {
                "min_gpa": 3.3,
                "exams": ["GMAT", "GRE", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Бизнес-проекты", "Стажировки в области аналитики"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-03-31",
                "exam_deadline": "2026-03-01",
                "decision_date": "2026-05-31",
            },
            "grants": [
                {
                    "name": "Стипендия бизнес-школы NUS",
                    "amount": "Частичная оплата обучения",
                    "conditions": "Академические и профессиональные заслуги",
                },
            ],
        },
    ],
    "KAIST": [
        {
            "name": "Компьютерные науки (бакалавр)",
            "direction_slug": "it-development",
            "language": "Английский / Корейский",
            "cost_per_year": 4400,
            "description": (
                "Программа CS KAIST — лучшая в Южной Корее, предлагающая интенсивную "
                "исследовательскую подготовку в области ИИ, систем и алгоритмов с возможностью обучения на английском."
            ),
            "who_its_for": (
                "Высокоуспевающие студенты, интересующиеся наукой и технологиями, "
                "желающие получить опыт исследовательского университета в Азии по низкой цене."
            ),
            "career_options": [
                "Инженер-программист", "ML-исследователь", "Системный инженер",
                "ИИ-инженер", "Учёный-исследователь",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1400,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Олимпиады по математике/информатике", "Исследовательские проекты"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2025-11-01",
                "exam_deadline": "2025-10-31",
                "decision_date": "2025-12-15",
            },
            "grants": [
                {
                    "name": "Международная стипендия KAIST",
                    "amount": "Полная оплата обучения + ежемесячная стипендия",
                    "conditions": "Выдающиеся иностранные студенты",
                },
            ],
        },
        {
            "name": "Электроинженерия (бакалавр)",
            "direction_slug": "engineering-architecture",
            "language": "Английский / Корейский",
            "cost_per_year": 4400,
            "description": (
                "Программа EE KAIST охватывает схемотехнику, обработку сигналов, полупроводники "
                "и средства связи — основа для карьеры в области аппаратного обеспечения и проектирования микросхем."
            ),
            "who_its_for": (
                "Студенты, увлечённые электроникой, аппаратными системами "
                "и полупроводниковыми технологиями в ведущей стране-производителе микросхем."
            ),
            "career_options": [
                "Инженер по аппаратному обеспечению", "Разработчик микросхем", "Инженер по обработке сигналов",
                "Инженер встроенных систем", "РЧ-инженер",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1350,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Олимпиады по физике/математике", "Проекты по электронике"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2025-11-01",
                "exam_deadline": "2025-10-31",
                "decision_date": "2025-12-15",
            },
            "grants": [
                {
                    "name": "Международная стипендия KAIST",
                    "amount": "Полная оплата обучения + ежемесячная стипендия",
                    "conditions": "Выдающиеся иностранные студенты",
                },
            ],
        },
    ],
    "Imperial College London": [
        {
            "name": "Вычислительная техника (магистр инженерии)",
            "direction_slug": "it-development",
            "language": "Английский",
            "cost_per_year": 37900,
            "description": (
                "Четырёхлетняя программа MEng Imperial по вычислительной технике — одна из наиболее "
                "строгих CS-программ Великобритании, охватывающая ИИ, системы, графику и разработку ПО."
            ),
            "who_its_for": (
                "Лучшие студенты, желающие получить интегрированную степень магистра "
                "от университета из мировой топ-10 в центре Лондона."
            ),
            "career_options": [
                "Инженер-программист", "Исследователь ИИ", "Системный архитектор",
                "Квант-разработчик", "Технологический консультант",
            ],
            "requirements": {
                "min_gpa": 3.9,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Олимпиады по математике/информатике", "Исследовательские или open-source проекты"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Президентская стипендия Imperial",
                    "amount": "Полная оплата обучения + £5 000/год",
                    "conditions": "Лучшие соискатели PhD; частичное финансирование доступно для бакалавров",
                },
            ],
        },
        {
            "name": "Биомедицинская инженерия (магистр инженерии)",
            "direction_slug": "medicine-biology",
            "language": "Английский",
            "cost_per_year": 37900,
            "description": (
                "Программа MEng Imperial по биомедицинской инженерии сочетает инженерные принципы "
                "с медицинскими приложениями: от устройств до биосенсоров."
            ),
            "who_its_for": (
                "Студенты на стыке инженерии и медицины, желающие проектировать устройства, "
                "разрабатывать диагностику или заниматься клинической инженерией."
            ),
            "career_options": [
                "Биомедицинский инженер", "Разработчик медицинских устройств", "Клинический инженер",
                "Разработчик биосенсоров", "Предприниматель в сфере медтеха",
            ],
            "requirements": {
                "min_gpa": 3.8,
                "exams": ["A-Levels", "IB", "IELTS"],
                "min_ielts": 7.0,
                "min_sat": None,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Опыт работы в лаборатории по биологии/химии", "Инженерные проекты"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2026-01-15",
                "exam_deadline": "2026-01-15",
                "decision_date": "2026-04-30",
            },
            "grants": [
                {
                    "name": "Стипендия Imperial College Trust",
                    "amount": "£10 000",
                    "conditions": "Иностранные студенты с исключительной успеваемостью",
                },
            ],
        },
    ],
    "Seoul National University": [
        {
            "name": "Информатика и инженерия (бакалавр)",
            "direction_slug": "it-development",
            "language": "Корейский / Английский",
            "cost_per_year": 5500,
            "description": (
                "Программа CSE SNU — наиболее престижная в Южной Корее, сочетающая "
                "сильную теоретическую подготовку с крупными исследовательскими и промышленными связями."
            ),
            "who_its_for": (
                "Высокоуспевающие студенты, интересующиеся разработкой ПО, ИИ или системами, "
                "желающие учиться в лучшем университете Южной Кореи по доступной цене."
            ),
            "career_options": [
                "Инженер-программист", "ИИ-инженер", "Системный разработчик",
                "Учёный-исследователь", "Технологический предприниматель",
            ],
            "requirements": {
                "min_gpa": 3.8,
                "exams": ["CSAT", "SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.5,
                "min_sat": 1400,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": True,
                "extracurriculars": ["Олимпиады по информатике/математике", "Исследовательские стажировки"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2025-11-15",
                "exam_deadline": "2025-11-01",
                "decision_date": "2025-12-20",
            },
            "grants": [
                {
                    "name": "Глобальная стипендия SNU",
                    "amount": "Полная оплата обучения",
                    "conditions": "Выдающиеся иностранные студенты",
                },
            ],
        },
        {
            "name": "Промышленная инженерия (бакалавр)",
            "direction_slug": "engineering-architecture",
            "language": "Корейский / Английский",
            "cost_per_year": 5500,
            "description": (
                "Программа SNU по промышленной инженерии охватывает исследование операций, "
                "цепочки поставок, системную инженерию и науку об управлении."
            ),
            "who_its_for": (
                "Студенты, интересующиеся оптимизацией сложных систем — от логистики "
                "до производства — с использованием количественных и инженерных методов."
            ),
            "career_options": [
                "Аналитик операционных исследований", "Менеджер по цепочке поставок", "Системный инженер",
                "Консультант по управлению", "Менеджер проектов",
            ],
            "requirements": {
                "min_gpa": 3.7,
                "exams": ["CSAT", "SAT", "IELTS", "TOEFL"],
                "min_ielts": 6.0,
                "min_sat": 1350,
                "needs_portfolio": False,
                "needs_essay": True,
                "needs_recommendations": True,
                "needs_interview": False,
                "extracurriculars": ["Математические олимпиады", "Робототехнические/инженерные клубы"],
            },
            "deadlines": {
                "application_open": "2025-09-01",
                "application_close": "2025-11-15",
                "exam_deadline": "2025-11-01",
                "decision_date": "2025-12-20",
            },
            "grants": [
                {
                    "name": "Глобальная стипендия SNU",
                    "amount": "Полная оплата обучения",
                    "conditions": "Выдающиеся иностранные студенты",
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
                existing_uni = University(**uni_data)
                db.add(existing_uni)
                await db.flush()
                uni_inserted += 1
            else:
                changed = False
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
                        "direction_slug", "language", "cost_per_year", "description",
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
