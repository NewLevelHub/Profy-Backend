"""
Seed script: populate universities and programs tables.
Run inside Docker: docker-compose exec api python scripts/seed_universities.py
Idempotent: upserts by university name; upserts programs by (university_id, name).
Coverage: KZ, USA, UK, Europe, Canada, Asia — 43 universities, 64 programs.

Specialty pivot (2026-07): direction_slug used to reference 15 "orphaned"
slugs (it-development, artificial-intelligence, etc.) that had no matching
Direction row at all — program_direction_slugs_for never expanded them, so
these 64 programs silently never appeared in a normal test-result flow. All
15 are now replaced with real section/specialty slugs from
seed_akinator_content.py (module-level assert below enforces this going
forward). `data-science` needed no change — old slug and new specialty slug
coincide.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from scripts.seed_akinator_content import SECTIONS, SPECIALTIES

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
        "ranking": 450,
        "description": (
            "Ведущий исследовательский университет Казахстана с полностью англоязычным "
            "обучением, автономным статусом и программами, разработанными совместно "
            "с топ-30 университетами мира."
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
        "ranking": 317,
        "description": (
            "Крупнейший национальный исследовательский университет Казахстана в Астане "
            "с сильными программами в IT, инженерии, естественных науках, праве и "
            "международных отношениях."
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
    {
        "name": "S. Seifullin Kazakh Agrotechnical Research University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://kazatu.edu.kz",
        "ranking": 1300,
        "description": (
            "Крупный агротехнический исследовательский университет Астаны с сильными "
            "программами в инженерии, агротехнологиях и экологии."
        ),
    },
    {
        "name": "Astana Medical University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://amu.edu.kz",
        "ranking": None,
        "description": (
            "Один из ведущих медицинских университетов Казахстана, готовящий врачей, "
            "фармацевтов и специалистов общественного здравоохранения."
        ),
    },
    {
        "name": "Kazakh National University of Arts",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://kaznui.edu.kz",
        "ranking": None,
        "description": (
            "Крупнейший творческий вуз Астаны, известный как центр подготовки "
            "музыкантов, режиссёров, дизайнеров и деятелей культуры."
        ),
    },
    {
        "name": "Kazakh National Academy of Choreography",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://balletacademy.edu.kz",
        "ranking": None,
        "description": (
            "Специализированная академия хореографии, объединяющая творческую, "
            "педагогическую и арт-менеджерскую подготовку."
        ),
    },
    {
        "name": "Astana International University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://aiu.kz",
        "ranking": 1450,
        "description": (
            "Частный многопрофильный университет Астаны с программами в IT, праве, "
            "экономике, дизайне и педагогике, включая двудипломные треки."
        ),
    },
    {
        "name": "Qazaq AI Research University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://qairu.kz",
        "ranking": None,
        "description": (
            "Новый AI-ориентированный исследовательский университет Астаны с фокусом "
            "на машинном обучении, робототехнике и междисциплинарных AI-направлениях."
        ),
    },
    {
        "name": "Esil University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://esil.edu.kz",
        "ranking": None,
        "description": (
            "Многопрофильный предпринимательский университет Астаны с сильными "
            "направлениями в экономике, праве, IT и управлении."
        ),
    },
    {
        "name": "Turan-Astana University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://tau-edu.kz",
        "ranking": None,
        "description": (
            "Частный университет Астаны с программами в праве, дизайне, IT, туризме "
            "и бизнесе, ориентированный на практическую подготовку."
        ),
    },
    {
        "name": "K. Kulazhanov Kazakh University of Technology and Business",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://www.kaztbu.edu.kz",
        "ranking": None,
        "description": (
            "Отраслевой университет Астаны, развивающий подготовку в области "
            "инжиниринга, пищевых технологий, IT и прикладного бизнеса."
        ),
    },
    {
        "name": "A.K. Kussayinov Eurasian Humanities Institute",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://egi.edu.kz",
        "ranking": None,
        "description": (
            "Гуманитарный вуз Астаны, специализирующийся на педагогике, психологии, "
            "языках, переводе и праве."
        ),
    },
    {
        "name": "Financial Academy",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://fin-academy.kz",
        "ranking": None,
        "description": (
            "Специализированный вуз в сфере финансов, бухгалтерского учёта, экономики "
            "и информационных систем."
        ),
    },
    {
        "name": "Astana University",
        "country": "Казахстан",
        "city": "Астана",
        "website": "http://astanauniver.kz",
        "ranking": None,
        "description": (
            "Многопрофильный частный университет в центре Астаны с программами "
            "в дизайне, туризме, праве, IT и управлении."
        ),
    },
    {
        "name": "Lomonosov Moscow State University Kazakhstan Branch",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://www.msu.kz",
        "ranking": 105,
        "description": (
            "Казахстанский филиал МГУ с сильной фундаментальной подготовкой "
            "в математике, прикладной информатике, экологии и экономике."
        ),
    },
    {
        "name": "Cardiff University Kazakhstan",
        "country": "Казахстан",
        "city": "Астана",
        "website": "https://cardiff.edu.kz",
        "ranking": 179,
        "description": (
            "Кампус Cardiff University в Астане с англоязычными программами "
            "в компьютерных науках, бизнесе, инженерии и геологии."
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
            "direction_slug": "software-engineer",
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
        {
            "name": "Физика (бакалавр)",
            "direction_slug": "mechanical-engineer",
            "language": "Английский",
            "cost_per_year": 3000,
            "description": (
                "Фундаментальная программа School of Sciences and Humanities по физике "
                "с сильной математической и исследовательской подготовкой."
            ),
            "who_its_for": (
                "Абитуриенты, увлечённые фундаментальной наукой и готовые к интенсивной "
                "академической подготовке на английском языке."
            ),
            "career_options": [
                "Научный сотрудник", "Исследователь", "Преподаватель физики",
                "Инженер-физик", "Аналитик в R&D",
            ],
            "requirements": {
                "exams": ["NUET", "SAT", "ACT", "ЕНТ", "IELTS"],
                "min_ielts": 6.5,
            },
            "deadlines": {"application_close": "2026-02-28"},
            "grants": [{"name": "Президентская стипендия", "amount": "Полная оплата", "conditions": "Конкурсный отбор"}],
        },
    ],
    "KIMEP University": [
        {
            "name": "Управление бизнесом (BBA)",
            "direction_slug": "management-entrepreneurship",
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
            "direction_slug": "finance-accounting",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "zoologist",
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
            "direction_slug": "mechanical-engineer",
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
            "direction_slug": "data-science",
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
            "direction_slug": "design",
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
            "direction_slug": "architect",
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
            "direction_slug": "ecologist",
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
            "direction_slug": "psychologist",
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
            "direction_slug": "lawyer",
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
            "direction_slug": "journalist",
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
            "direction_slug": "marketing",
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
            "direction_slug": "management-entrepreneurship",
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
    "S. Seifullin Kazakh Agrotechnical Research University": [
        {
            "name": "Агроинженерия и мехатроника (бакалавр)",
            "direction_slug": "mechanical-engineer",
            "language": "Казахский / Русский",
            "cost_per_year": 2200,
            "description": (
                "Инженерная программа КазАТИУ, ориентированная на агротехнику, автоматизацию "
                "и эксплуатацию современных производственных систем."
            ),
            "who_its_for": (
                "Абитуриенты, которым интересны техника, механика и прикладные инженерные "
                "задачи в промышленности и агросекторе."
            ),
            "career_options": [
                "Инженер-механик", "Инженер по автоматизации", "Производственный инженер",
                "Инженер по сельхозтехнике", "Технический менеджер",
            ],
            "requirements": {"exams": ["ЕНТ"], "profile_subjects": ["Математика", "Физика"]},
            "deadlines": {"application_close": "2026-08-25"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурс ЕНТ"}],
        },
    ],
    "Astana Medical University": [
        {
            "name": "Общая медицина (бакалавриат/интегрированная программа)",
            "direction_slug": "general-medicine",
            "language": "Казахский / Русский",
            "cost_per_year": 3400,
            "description": (
                "Программа по общей медицине с сильной клинической базой и требованиями "
                "по профильным предметам биология + химия."
            ),
            "who_its_for": (
                "Абитуриенты, нацеленные на карьеру врача и готовые к интенсивной "
                "естественнонаучной и клинической подготовке."
            ),
            "career_options": [
                "Врач общей практики", "Клинический ординатор", "Медицинский исследователь",
                "Специалист общественного здравоохранения", "Врач-стажёр",
            ],
            "requirements": {"exams": ["ЕНТ"], "profile_subjects": ["Биология", "Химия"]},
            "deadlines": {"application_close": "2026-08-25"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурс ЕНТ"}],
        },
    ],
    "Kazakh National University of Arts": [
        {
            "name": "Графический дизайн и визуальные коммуникации (бакалавр)",
            "direction_slug": "design",
            "language": "Казахский / Русский",
            "cost_per_year": 2100,
            "description": (
                "Творческая программа по графическому дизайну с акцентом на композицию, "
                "визуальную культуру и практику в креативных индустриях."
            ),
            "who_its_for": (
                "Абитуриенты с художественной подготовкой, которым интересны визуальные "
                "коммуникации, брендинг и цифровой дизайн."
            ),
            "career_options": [
                "Графический дизайнер", "Иллюстратор", "Арт-директор",
                "Motion-дизайнер", "Бренд-дизайнер",
            ],
            "requirements": {"exams": ["ЕНТ", "Творческий экзамен"], "needs_portfolio": True},
            "deadlines": {"application_close": "2026-07-20"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Творческий конкурс"}],
        },
    ],
    "Kazakh National Academy of Choreography": [
        {
            "name": "Арт-менеджмент в хореографии (бакалавр)",
            "direction_slug": "akinator-stage-media",
            "language": "Казахский / Русский",
            "cost_per_year": 2300,
            "description": (
                "Программа сочетает управление творческими проектами, организацию событий "
                "и понимание культурной индустрии."
            ),
            "who_its_for": (
                "Студенты, которым интересны креативные проекты, культурные события "
                "и организационная работа в сфере искусства."
            ),
            "career_options": [
                "Арт-менеджер", "Координатор проектов", "Продюсер мероприятий",
                "Администратор театра", "Менеджер культурных программ",
            ],
            "requirements": {"exams": ["ЕНТ", "Собеседование/творческий отбор"]},
            "deadlines": {"application_close": "2026-07-25"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурсный отбор"}],
        },
    ],
    "Astana International University": [
        {
            "name": "Data Science (бакалавр)",
            "direction_slug": "data-science",
            "language": "Английский / Русский",
            "cost_per_year": 3000,
            "description": (
                "Программа по анализу данных и прикладной статистике с фокусом на цифровые "
                "инструменты и междисциплинарные проекты."
            ),
            "who_its_for": (
                "Абитуриенты с интересом к математике, аналитике и программированию, "
                "нацеленные на карьеру в data-driven командах."
            ),
            "career_options": [
                "Аналитик данных", "BI-аналитик", "Data Scientist",
                "Продуктовый аналитик", "Исследователь данных",
            ],
            "requirements": {"exams": ["ЕНТ"], "profile_subjects": ["Математика", "Информатика"]},
            "deadlines": {"application_close": "2026-08-25"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурс ЕНТ"}],
        },
    ],
    "Qazaq AI Research University": [
        {
            "name": "AI and Machine Learning (бакалавр)",
            "direction_slug": "data-science",
            "language": "Английский",
            "cost_per_year": 4700,
            "description": (
                "Флагманская программа QAIRU по искусственному интеллекту и машинному "
                "обучению с внутренним диагностическим тестом QPT."
            ),
            "who_its_for": (
                "Сильные абитуриенты с интересом к математике, ML и инженерной реализации "
                "AI-систем в реальных продуктах."
            ),
            "career_options": [
                "ML-инженер", "AI-разработчик", "Research Engineer",
                "Data Scientist", "Инженер по робототехнике",
            ],
            "requirements": {"exams": ["ЕНТ", "QPT"], "min_ielts": 6.0},
            "deadlines": {"application_close": "2026-08-25"},
            "grants": [{"name": "Внутренний грант QAIRU", "amount": "До полной оплаты", "conditions": "По конкурсу"}],
        },
    ],
    "Esil University": [
        {
            "name": "Финансы (бакалавр)",
            "direction_slug": "finance-accounting",
            "language": "Казахский / Русский",
            "cost_per_year": 1900,
            "description": (
                "Прикладная программа по финансам с подготовкой в корпоративных финансах, "
                "бухучёте и финансовом анализе."
            ),
            "who_its_for": (
                "Абитуриенты, которым интересны экономика, расчёты, банки и финансовое "
                "управление в бизнесе."
            ),
            "career_options": [
                "Финансовый аналитик", "Бухгалтер", "Кредитный аналитик",
                "Казначей", "Специалист финконтроля",
            ],
            "requirements": {"exams": ["ЕНТ"], "profile_subjects": ["Математика", "География"]},
            "deadlines": {"application_close": "2026-08-25"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурс ЕНТ"}],
        },
    ],
    "Turan-Astana University": [
        {
            "name": "Digital-маркетинг (бакалавр)",
            "direction_slug": "marketing",
            "language": "Казахский / Русский",
            "cost_per_year": 2100,
            "description": (
                "Программа по современному маркетингу с акцентом на digital-каналы, "
                "брендинг, аналитику и продвижение."
            ),
            "who_its_for": (
                "Креативные и коммуникабельные абитуриенты, которым интересны бренды, "
                "контент и работа с аудиторией."
            ),
            "career_options": [
                "Digital-маркетолог", "SMM-менеджер", "Бренд-менеджер",
                "Контент-стратег", "PR-специалист",
            ],
            "requirements": {"exams": ["ЕНТ"]},
            "deadlines": {"application_close": "2026-08-25"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурс ЕНТ"}],
        },
    ],
    "K. Kulazhanov Kazakh University of Technology and Business": [
        {
            "name": "Искусственный интеллект (бакалавр)",
            "direction_slug": "data-science",
            "language": "Казахский / Русский",
            "cost_per_year": 2400,
            "description": (
                "Инженерная программа по AI с прикладным уклоном в автоматизацию, "
                "цифровую энергетику и IT-системы."
            ),
            "who_its_for": (
                "Абитуриенты, желающие изучать ИИ в прикладном техническом контексте "
                "и работать на стыке производства и цифровых решений."
            ),
            "career_options": [
                "AI-инженер", "Аналитик данных", "Инженер автоматизации",
                "ML-разработчик", "Технический аналитик",
            ],
            "requirements": {"exams": ["ЕНТ"], "profile_subjects": ["Математика", "Физика"]},
            "deadlines": {"application_close": "2026-08-25"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурс ЕНТ"}],
        },
    ],
    "A.K. Kussayinov Eurasian Humanities Institute": [
        {
            "name": "Педагогика и психология (бакалавр)",
            "direction_slug": "akinator-education",
            "language": "Казахский / Русский",
            "cost_per_year": 1700,
            "description": (
                "Гуманитарная программа по психологии и педагогике для подготовки "
                "специалистов школ, образовательных центров и консультационной практики."
            ),
            "who_its_for": (
                "Абитуриенты с выраженной эмпатией и интересом к развитию, обучению "
                "и сопровождению детей и подростков."
            ),
            "career_options": [
                "Педагог-психолог", "Школьный психолог", "Методист",
                "Куратор образовательных программ", "HR-специалист",
            ],
            "requirements": {"exams": ["ЕНТ"]},
            "deadlines": {"application_close": "2026-08-25"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурс ЕНТ"}],
        },
    ],
    "Financial Academy": [
        {
            "name": "Экономика и финансовая аналитика (бакалавр)",
            "direction_slug": "finance-accounting",
            "language": "Казахский / Русский",
            "cost_per_year": 1800,
            "description": (
                "Программа по экономике и финансовой аналитике, ориентированная на подготовку "
                "специалистов для банков, госструктур и бизнеса."
            ),
            "who_its_for": (
                "Абитуриенты, которым интересны экономика, аналитика и работа с финансовыми "
                "показателями организаций."
            ),
            "career_options": [
                "Экономист", "Финансовый аналитик", "Бюджетный специалист",
                "Бухгалтер-аналитик", "Кредитный менеджер",
            ],
            "requirements": {"exams": ["ЕНТ"], "profile_subjects": ["Математика", "География"]},
            "deadlines": {"application_close": "2026-08-25"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурс ЕНТ"}],
        },
    ],
    "Astana University": [
        {
            "name": "Туризм и сервисный менеджмент (бакалавр)",
            "direction_slug": "hospitality-manager",
            "language": "Казахский / Русский",
            "cost_per_year": 1850,
            "description": (
                "Программа сочетает организацию сервисных процессов, управление проектами "
                "и клиентский опыт в индустрии туризма и услуг."
            ),
            "who_its_for": (
                "Абитуриенты, которым интересны организация, коммуникации и управление "
                "сервисными командами и проектами."
            ),
            "career_options": [
                "Менеджер проектов", "Менеджер по туризму", "Операционный координатор",
                "Event-менеджер", "Менеджер клиентского сервиса",
            ],
            "requirements": {"exams": ["ЕНТ"]},
            "deadlines": {"application_close": "2026-08-25"},
            "grants": [{"name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурс ЕНТ"}],
        },
    ],
    "Lomonosov Moscow State University Kazakhstan Branch": [
        {
            "name": "Прикладная математика и информатика (бакалавр)",
            "direction_slug": "data-science",
            "language": "Русский",
            "cost_per_year": 0,
            "description": (
                "Фундаментальная программа филиала МГУ с сильной математической базой и "
                "собственными вступительными экзаменами вместо ЕНТ."
            ),
            "who_its_for": (
                "Очень сильные абитуриенты, которым интересны математика, моделирование "
                "и прикладная информатика на академическом уровне."
            ),
            "career_options": [
                "Аналитик данных", "Исследователь", "Прикладной математик",
                "Алгоритмист", "ML-инженер",
            ],
            "requirements": {"exams": ["Внутренние вступительные экзамены МГУ-КФ"]},
            "deadlines": {"application_close": "2026-07-25"},
            "grants": [{"name": "Госзаказ РК", "amount": "Полная оплата", "conditions": "Обучение бесплатное по конкурсу"}],
        },
    ],
    "Cardiff University Kazakhstan": [
        {
            "name": "Civil Engineering (бакалавр)",
            "direction_slug": "civil-engineering",
            "language": "Английский",
            "cost_per_year": 9000,
            "description": (
                "Англоязычная программа кампуса Cardiff в Астане по гражданскому "
                "строительству с возможностью Foundation Year."
            ),
            "who_its_for": (
                "Абитуриенты, ориентированные на международное инженерное образование "
                "и карьеру в строительстве, инфраструктуре и проектировании."
            ),
            "career_options": [
                "Civil engineer", "Проектировщик", "Site engineer",
                "BIM-специалист", "Инженер-конструктор",
            ],
            "requirements": {"exams": ["Аттестат/ЕНТ", "IELTS"]},
            "deadlines": {"application_close": "2026-08-20"},
            "grants": [{"name": "Грант кампуса Cardiff KZ", "amount": "Частичная/полная оплата", "conditions": "По конкурсу"}],
        },
    ],
    "Massachusetts Institute of Technology": [
        {
            "name": "Информатика и инженерия (бакалавр)",
            "direction_slug": "software-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "data-science",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "management-entrepreneurship",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "general-medicine",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "data-science",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "mechanical-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "data-science",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "mechanical-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "mechanical-engineer",
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
            "direction_slug": "software-engineer",
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
            "direction_slug": "management-entrepreneurship",
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

_KNOWN_DIRECTION_SLUGS = {s["slug"] for s in SECTIONS} | {s["slug"] for s in SPECIALTIES}
for _uni_name, _programs in PROGRAMS_BY_UNIVERSITY.items():
    for _prog in _programs:
        assert _prog["direction_slug"] in _KNOWN_DIRECTION_SLUGS, (
            f"{_uni_name}/{_prog['name']}: unknown direction_slug {_prog['direction_slug']!r}"
        )


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
