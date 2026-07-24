"""
Seed Astana universities and programs from scripts/astana_universities_data.py.

Specialty pivot (2026-07): direction_slug now targets the specific specialty
slug from seed_akinator_content.py (e.g. "software-engineer") wherever a
program clearly matches one accredited specialty. Programs whose name spans
several specialties or an ambiguous mix (e.g. "Педагогика и психология") are
left at the section level (e.g. "akinator-education") as a conscious
compromise — see SPECIALTY_PIVOT_TICKET.md.

Run inside Docker:
    docker compose exec api python scripts/seed_astana_universities.py
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
from scripts.astana_universities_data import ASTANA_UNIVERSITIES
from scripts.seed_akinator_content import EXPLORE_NODES, SECTIONS, SPECIALTIES

# direction_slugs = list of akinator section/specialty slugs from seed_akinator_content.py
PROGRAMS_BY_UNIVERSITY_SLUG: dict[str, list[dict]] = {
    "nazarbayev-university": [
        {
            "name": "Computer Science (бакалавр)",
            "direction_slugs": ["software-engineer"],
            "language": "Английский",
            "description": "Программа School of Engineering and Digital Sciences по компьютерным наукам.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Doctor of Medicine (6 лет)",
            "direction_slugs": ["general-medicine"],
            "language": "Английский",
            "description": "6-летняя медицинская программа School of Medicine (NUSOM).",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Business Administration (BBA)",
            "direction_slugs": ["management-entrepreneurship"],
            "language": "Английский",
            "description": "Программа Graduate School of Business.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
    ],
    "enu": [
        {
            "name": "Информационные технологии (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development"],
            "language": "Казахский / Русский / Английский",
            "description": "Факультет информационных технологий ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer"],
            "language": "Казахский / Русский",
            "description": "Юридический факультет ЕНУ.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Экология и природопользование (бакалавр)",
            "direction_slugs": ["ecologist"],
            "language": "Казахский / Русский",
            "description": "Естественнонаучные программы ЕНУ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Строительство (бакалавр)",
            "direction_slugs": ["civil-engineering"],
            "language": "Казахский / Русский / Английский",
            "description": "Архитектурно-строительный факультет ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Электроэнергетика (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "civil-engineering"],
            "language": "Казахский / Русский / Английский",
            "description": "Транспортно-энергетический факультет ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship"],
            "language": "Казахский / Русский / Английский",
            "description": "Экономический факультет ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Журналистика (бакалавр)",
            "direction_slugs": ["journalist", "media-journalism"],
            "language": "Казахский / Русский / Английский",
            "description": "Факультет журналистики и политологии ЕНУ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Психология (бакалавр)",
            "direction_slugs": ["psychologist"],
            "language": "Казахский / Русский",
            "description": "Факультет социальных наук ЕНУ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Финансы (бакалавр)",
            "direction_slugs": ["finance-accounting", "finance-economics"],
            "language": "Казахский / Русский",
            "description": "Экономический факультет ЕНУ — финансы.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Переводческое дело (бакалавр)",
            "direction_slugs": ["translator"],
            "language": "Казахский / Русский / Английский",
            "description": "Филологический факультет ЕНУ.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Математика (бакалавр)",
            "direction_slugs": ["data-science", "explore-numbers"],
            "language": "Казахский / Русский",
            "description": "Механико-математический факультет ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Физика (бакалавр)",
            "direction_slugs": ["science-research"],
            "language": "Казахский / Русский / Английский",
            "description": "Физико-технический факультет ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Биология (бакалавр)",
            "direction_slugs": ["zoologist", "medicine-biology"],
            "language": "Казахский / Русский",
            "description": "Факультет естественных наук ЕНУ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Педагогика и психология (бакалавр)",
            "direction_slugs": ["school-teacher", "psychology-pedagogy"],
            "language": "Казахский / Русский / Английский",
            "description": "Педагогические программы ЕНУ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Архитектура (бакалавр)",
            "direction_slugs": ["architect"],
            "language": "Казахский",
            "description": "Архитектурный факультет ЕНУ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Искусственный интеллект (бакалавр)",
            "direction_slugs": ["artificial-intelligence", "data-science"],
            "language": "Казахский / Русский / Английский",
            "description": "IT-факультет ЕНУ — технологии ИИ.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Кибербезопасность (бакалавр)",
            "direction_slugs": ["it-infrastructure-security"],
            "language": "Казахский / Русский / Английский",
            "description": "Системы информационной безопасности ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Международные отношения (бакалавр)",
            "direction_slugs": ["law-public-administration"],
            "language": "Казахский / Русский / Английский",
            "description": "Факультет международных отношений ЕНУ.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Учёт и аудит (бакалавр)",
            "direction_slugs": ["finance-accounting", "akinator-business-sales"],
            "language": "Русский/Казахский",
            "description": "Бухгалтерский учёт и аудит на экономическом факультете ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Социальная работа (бакалавр)",
            "direction_slugs": ["social-worker", "akinator-psychology-help"],
            "language": "Русский/Казахский",
            "description": "Социальная работа и поддержка населения на факультете социальных наук ЕНУ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "История (бакалавр)",
            "direction_slugs": ["law-public-administration", "akinator-words-communication"],
            "language": "Русский/Казахский",
            "description": "Исторические науки и культурное наследие на гуманитарном факультете ЕНУ.",
            "requirements": {"ent_subjects": ["Всемирная история", "География"]},
        },
        {
            "name": "Политология (бакалавр)",
            "direction_slugs": ["law-public-administration", "akinator-words-communication"],
            "language": "Русский/Казахский",
            "description": "Политические науки и государственное управление ЕНУ.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Социология (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "akinator-business-sales"],
            "language": "Русский/Казахский",
            "description": "Социологические исследования и анализ общества ЕНУ.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Казахский язык и литература (бакалавр)",
            "direction_slugs": ["school-teacher", "akinator-education"],
            "language": "Казахский",
            "description": "Казахская филология и лингвистика на филологическом факультете ЕНУ.",
            "requirements": {"ent_subjects": ["Казахский язык", "Казахская литература"]},
        },
        {
            "name": "Русский язык и литература (бакалавр)",
            "direction_slugs": ["school-teacher", "akinator-education"],
            "language": "Русский",
            "description": "Русская филология и литературоведение на филологическом факультете ЕНУ.",
            "requirements": {"ent_subjects": ["Русский язык", "Русская литература"]},
        },
        {
            "name": "Архитектурный дизайн (бакалавр)",
            "direction_slugs": ["design", "akinator-creative-design"],
            "language": "Русский/Казахский",
            "description": "Архитектурный дизайн зданий и интерьеров на архитектурно-строительном факультете ЕНУ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Туризм (бакалавр)",
            "direction_slugs": ["hospitality-manager", "akinator-food-hospitality"],
            "language": "Русский/Казахский",
            "description": "Туризм и гостеприимство на факультете социальных наук ЕНУ.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "Ресторанное дело и гостиничный бизнес (бакалавр)",
            "direction_slugs": ["hospitality-manager", "akinator-food-hospitality"],
            "language": "Русский/Казахский",
            "description": "Управление в индустрии гостеприимства и ресторанном бизнесе ЕНУ.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "Востоковедение (бакалавр)",
            "direction_slugs": ["translator", "akinator-words-communication"],
            "language": "Русский/Казахский",
            "description": "Изучение языков и культур Востока на факультете международных отношений ЕНУ.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Транспорт и транспортные технологии (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "akinator-engineering-tech"],
            "language": "Русский/Казахский",
            "description": "Транспортные системы и технологии на транспортно-энергетическом факультете ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Системы информационной безопасности (бакалавр)",
            "direction_slugs": ["it-infrastructure-security", "akinator-it-data"],
            "language": "Русский/Казахский",
            "description": "Информационная безопасность компьютерных систем на IT-факультете ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Государственное и местное управление (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "akinator-business-sales"],
            "language": "Русский/Казахский",
            "description": "Государственное и местное управление на экономическом факультете ЕНУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Дошкольное образование (бакалавр)",
            "direction_slugs": ["kindergarten-teacher", "akinator-education"],
            "language": "Русский/Казахский",
            "description": "Педагогика дошкольного образования и воспитания ЕНУ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Химия (бакалавр)",
            "direction_slugs": ["medicine-biology", "akinator-medicine"],
            "language": "Русский/Казахский",
            "description": "Химические науки и прикладная химия на факультете естественных наук ЕНУ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
    ],
    "mnu": [
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer"],
            "language": "Казахский / Русский / Английский",
            "description": "MNU Law School.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Finance (бакалавр)",
            "direction_slugs": ["finance-accounting", "finance-economics"],
            "language": "Английский",
            "description": "International School of Economics.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Psychology (бакалавр)",
            "direction_slugs": ["psychologist"],
            "language": "Английский",
            "description": "School of Liberal Arts.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "International Journalism (бакалавр)",
            "direction_slugs": ["journalist"],
            "language": "Английский",
            "description": "International School of Journalism.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Маркетинг (бакалавр)",
            "direction_slugs": ["marketing", "marketing-advertising"],
            "language": "Английский",
            "description": "Маркетинговое направление MNU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship"],
            "language": "Английский",
            "description": "Менеджмент International School of Economics MNU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Переводческое дело (бакалавр)",
            "direction_slugs": ["translator"],
            "language": "Казахский / Русский / Английский",
            "description": "Лингвистические программы School of Liberal Arts MNU.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Прикладная лингвистика (бакалавр)",
            "direction_slugs": ["translator"],
            "language": "Английский",
            "description": "Прикладная лингвистика School of Liberal Arts MNU.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Международные отношения (бакалавр)",
            "direction_slugs": ["law-public-administration"],
            "language": "Английский",
            "description": "Международные отношения School of Liberal Arts MNU.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Учёт и аудит (бакалавр)",
            "direction_slugs": ["finance-accounting"],
            "language": "Английский",
            "description": "Учётно-аудиторское направление MNU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Экономика (бакалавр)",
            "direction_slugs": ["finance-economics"],
            "language": "Английский",
            "description": "Экономика и наука о данных International School of Economics MNU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "IT в бизнесе (бакалавр)",
            "direction_slugs": ["it-development", "management-entrepreneurship"],
            "language": "Английский",
            "description": "IT-бизнес направление MNU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Туризм (бакалавр)",
            "direction_slugs": ["hospitality-manager"],
            "language": "Казахский / Английский",
            "description": "Туризм и гостиничное дело MNU.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "Data Science (бакалавр)",
            "direction_slugs": ["data-science", "akinator-it-data"],
            "language": "Английский",
            "description": "Наука о данных и аналитика в International School of Economics MNU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Информационные системы и технологии (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development", "akinator-it-data"],
            "language": "Казахский / Русский / Английский",
            "description": "Информационные системы и технологии MNU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Дизайн (бакалавр)",
            "direction_slugs": ["design", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Графический, веб- и архитектурный дизайн в School of Liberal Arts MNU.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Экология и природопользование (бакалавр)",
            "direction_slugs": ["ecologist", "akinator-animals-nature"],
            "language": "Казахский / Русский",
            "description": "Экология и устойчивое природопользование MNU.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Биология (бакалавр)",
            "direction_slugs": ["medicine-biology", "akinator-medicine"],
            "language": "Казахский / Русский",
            "description": "Биологические науки в School of Liberal Arts MNU.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Педагогика и методика начального обучения (бакалавр)",
            "direction_slugs": ["school-teacher", "akinator-education"],
            "language": "Казахский / Русский",
            "description": "Подготовка учителей начальных классов в MNU.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Педагогика и психология (бакалавр)",
            "direction_slugs": ["school-teacher", "psychology-pedagogy"],
            "language": "Казахский / Русский",
            "description": "Педагогика и психология в School of Liberal Arts MNU.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Дошкольное образование (бакалавр)",
            "direction_slugs": ["kindergarten-teacher", "akinator-education"],
            "language": "Казахский / Русский",
            "description": "Подготовка педагогов дошкольного образования в MNU.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Физика (бакалавр)",
            "direction_slugs": ["science-research", "akinator-engineering-tech"],
            "language": "Казахский / Русский",
            "description": "Физика и подготовка учителей физики в School of Liberal Arts MNU.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Информатика (бакалавр)",
            "direction_slugs": ["software-engineer", "akinator-it-data"],
            "language": "Казахский / Русский",
            "description": "Информатика и компьютерные технологии в MNU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Казахский язык и литература (бакалавр)",
            "direction_slugs": ["school-teacher", "akinator-education"],
            "language": "Казахский",
            "description": "Казахская филология и методика преподавания в MNU.",
            "requirements": {"ent_subjects": ["Казахский язык", "Казахская литература"]},
        },
        {
            "name": "Русский язык и литература (бакалавр)",
            "direction_slugs": ["school-teacher", "akinator-education"],
            "language": "Русский",
            "description": "Русская филология и методика преподавания в MNU.",
            "requirements": {"ent_subjects": ["Русский язык", "Русская литература"]},
        },
        {
            "name": "Электронная коммерция (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "akinator-business-sales"],
            "language": "Казахский / Русский",
            "description": "Электронная коммерция и цифровые бизнес-технологии в MNU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Международный бизнес (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "finance-economics"],
            "language": "Казахский / Русский / Английский",
            "description": "Международный бизнес и управление в International School of Economics MNU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Право и государственное управление (бакалавр)",
            "direction_slugs": ["lawyer", "law-public-administration"],
            "language": "Казахский / Русский / Английский",
            "description": "Право и государственное управление в MNU Law School.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Международное право (бакалавр)",
            "direction_slugs": ["lawyer", "law-public-administration"],
            "language": "Казахский / Русский / Английский",
            "description": "Международно-правовые программы MNU Law School.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
    ],
    "aitu": [
        {
            "name": "Software Engineering (бакалавр)",
            "direction_slugs": ["software-engineer"],
            "language": "Английский",
            "description": "Школа программной инженерии AITU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Big Data Analysis (бакалавр)",
            "direction_slugs": ["data-science"],
            "language": "Английский",
            "description": "Школа искусственного интеллекта и науки о данных.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Digital Journalism (бакалавр)",
            "direction_slugs": ["journalist", "media-journalism"],
            "language": "Английский",
            "description": "Школа креативных индустрий.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Computer Science (бакалавр)",
            "direction_slugs": ["software-engineer", "data-science"],
            "language": "Английский",
            "description": "Программа компьютерных наук AITU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Cybersecurity (бакалавр)",
            "direction_slugs": ["it-infrastructure-security"],
            "language": "Английский",
            "description": "Школа кибербезопасности AITU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "IT Management (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "it-development"],
            "language": "Английский",
            "description": "ИТ-менеджмент в Школе креативных индустрий AITU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "AI Business (бакалавр)",
            "direction_slugs": ["artificial-intelligence", "management-entrepreneurship"],
            "language": "Английский",
            "description": "AI-бизнес направление AITU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "IT Entrepreneurship (бакалавр)",
            "direction_slugs": ["business-entrepreneurship", "it-development"],
            "language": "Английский",
            "description": "IT-предпринимательство AITU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Mathematical and Computational Science (бакалавр)",
            "direction_slugs": ["data-science", "explore-numbers"],
            "language": "Английский",
            "description": "Математические и вычислительные науки AITU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Media Technologies (бакалавр)",
            "direction_slugs": ["media-journalism", "journalist"],
            "language": "Английский",
            "description": "Медиатехнологии Школы креативных индустрий AITU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Electronic Engineering (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "it-infrastructure-security"],
            "language": "Английский",
            "description": "Электронная инженерия AITU.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Industrial Internet of Things (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "artificial-intelligence"],
            "language": "Английский",
            "description": "Промышленный интернет вещей AITU.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Телекоммуникационные системы (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "akinator-engineering-tech"],
            "language": "Русский/Казахский",
            "description": "Проектирование и эксплуатация телекоммуникационных систем и сетей в AITU.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Промышленная автоматизация (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development", "akinator-it-data"],
            "language": "Русский/Казахский",
            "description": "Автоматизация промышленных процессов и встраиваемые системы в AITU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Smart Технологии (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "akinator-engineering-tech"],
            "language": "Русский/Казахский",
            "description": "Разработка умных технологий и интеллектуальных систем в AITU.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
    ],
    "kazatu": [
        {
            "name": "Агроинженерия (бакалавр)",
            "direction_slugs": ["agronomist", "mechanical-engineer"],
            "language": "Казахский / Русский",
            "description": "Технический факультет КазАТИУ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Ветеринария (бакалавр)",
            "direction_slugs": ["veterinary-zootechnics"],
            "language": "Казахский / Русский",
            "description": "Факультет ветеринарии и технологии животноводства.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Архитектура и дизайн (бакалавр)",
            "direction_slugs": ["design", "architect"],
            "language": "Казахский / Русский",
            "description": "Факультет управления земельными ресурсами, архитектуры и дизайна.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Агрономия (бакалавр)",
            "direction_slugs": ["agronomist"],
            "language": "Казахский / Русский",
            "description": "Аграрный факультет КазАТИУ — агрономия, растениеводство.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Экология и природопользование (бакалавр)",
            "direction_slugs": ["ecologist"],
            "language": "Казахский / Русский",
            "description": "Экологическое направление КазАТИУ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Программная инженерия (бакалавр)",
            "direction_slugs": ["software-engineer"],
            "language": "Казахский / Русский / Английский",
            "description": "Факультет компьютерных систем КазАТИУ.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Биотехнология (бакалавр)",
            "direction_slugs": ["medicine-biology"],
            "language": "Казахский / Русский",
            "description": "Биотехнологическое направление КазАТИУ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Животноводство (бакалавр)",
            "direction_slugs": ["veterinary-zootechnics"],
            "language": "Казахский / Русский",
            "description": "Зоотехническое направление КазАТИУ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Электроэнергетика (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "civil-engineering"],
            "language": "Казахский / Русский / Английский",
            "description": "Энергетическое направление КазАТИУ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Аквакультура и водные биоресурсы (бакалавр)",
            "direction_slugs": ["zoologist", "akinator-animals-nature"],
            "language": "Русский/Казахский",
            "description": "Разведение рыбы и управление водными биоресурсами на факультете ветеринарии КазАТУ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Охотоведение и звероводство (бакалавр)",
            "direction_slugs": ["zoologist", "akinator-animals-nature"],
            "language": "Русский/Казахский",
            "description": "Охотничье хозяйство и разведение зверей на аграрном факультете КазАТУ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Ландшафтный дизайн и озеленение (бакалавр)",
            "direction_slugs": ["ecologist", "akinator-animals-nature"],
            "language": "Русский/Казахский",
            "description": "Проектирование ландшафтов и парковых пространств на факультете архитектуры и дизайна КазАТУ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Механическая инженерия (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "akinator-engineering-tech"],
            "language": "Русский/Казахский",
            "description": "Машиностроение и конструирование сельскохозяйственных машин на техническом факультете КазАТУ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Управление бизнесом и предпринимательство (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "akinator-business-sales"],
            "language": "Русский/Казахский",
            "description": "Предпринимательство и управление бизнесом на экономическом факультете КазАТУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Технология пищевых продуктов (бакалавр)",
            "direction_slugs": ["food-production-tech", "akinator-food-hospitality"],
            "language": "Русский/Казахский",
            "description": "Технологии переработки и производства пищевых продуктов на технологическом факультете КазАТУ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Землеустройство (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "akinator-business-sales"],
            "language": "Русский/Казахский",
            "description": "Землеустройство и кадастр на факультете управления земельными ресурсами КазАТУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Компьютерная инженерия (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development", "akinator-it-data"],
            "language": "Русский/Казахский",
            "description": "Компьютерные системы и сети на факультете информационных технологий КазАТУ.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Агроэкология (бакалавр)",
            "direction_slugs": ["ecologist", "akinator-animals-nature"],
            "language": "Русский/Казахский",
            "description": "Экология сельскохозяйственных систем и природопользование на аграрном факультете КазАТУ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Финансовая аналитика (бакалавр)",
            "direction_slugs": ["finance-accounting", "finance-economics", "akinator-business-sales"],
            "language": "Русский/Казахский",
            "description": "Финансовый анализ и управление на экономическом факультете КазАТУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Digital Маркетинг (бакалавр)",
            "direction_slugs": ["marketing", "marketing-advertising", "akinator-business-sales"],
            "language": "Русский/Казахский",
            "description": "Цифровой маркетинг и продвижение агробизнеса на экономическом факультете КазАТУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Сельскохозяйственная биотехнология (бакалавр)",
            "direction_slugs": ["agronomist", "akinator-animals-nature"],
            "language": "Русский/Казахский",
            "description": "Биотехнологии в сельском хозяйстве и растениеводстве КазАТУ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Агротехнология (бакалавр)",
            "direction_slugs": ["agronomist", "akinator-animals-nature"],
            "language": "Русский/Казахский",
            "description": "Современные технологии земледелия и агропроизводства на аграрном факультете КазАТУ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Автоматизация и энергоэффективность (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "akinator-engineering-tech"],
            "language": "Русский/Казахский",
            "description": "Автоматизация производственных процессов и энергоэффективность в сельском хозяйстве КазАТУ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Логистика на транспорте (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "akinator-business-sales"],
            "language": "Русский/Казахский",
            "description": "Транспортная логистика и управление грузоперевозками на факультете транспорта КазАТУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
    ],
    "amu": [
        {
            "name": "Общая медицина (бакалавриат)",
            "direction_slugs": ["general-medicine"],
            "language": "Казахский / Русский",
            "description": "Лечебное направление Медицинского университета Астана.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Фармация (бакалавр)",
            "direction_slugs": ["pharmacist"],
            "language": "Казахский / Русский",
            "description": "Фармацевтическое направление МУА.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Сестринское дело (бакалавр)",
            "direction_slugs": ["general-medicine"],
            "language": "Казахский / Русский",
            "description": "Направления кинезитерапии и эрготерапии.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Стоматология (бакалавр)",
            "direction_slugs": ["dentist"],
            "language": "Казахский / Русский",
            "description": "Стоматологическое направление МУА.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Общественное здравоохранение (бакалавр)",
            "direction_slugs": ["general-medicine"],
            "language": "Казахский / Русский",
            "description": "Общественное здоровье и профилактическая медицина МУА.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Кинезитерапия (бакалавр)",
            "direction_slugs": ["rehabilitation-therapist"],
            "language": "Казахский / Русский",
            "description": "Кинезитерапия — реабилитационное направление МУА.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Эрготерапия (бакалавр)",
            "direction_slugs": ["rehabilitation-therapist"],
            "language": "Казахский / Русский",
            "description": "Эрготерапия — реабилитационное направление МУА.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Общественное здоровье (бакалавр)",
            "direction_slugs": ["general-medicine", "akinator-medicine"],
            "language": "Казахский / Русский",
            "description": "Общественное здравоохранение и эпидемиология в Медицинском университете Астана.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
    ],
    "kaznui": [
        {
            "name": "Графический дизайн (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "Направление «Мода, дизайн» КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Театральное искусство (бакалавр)",
            "direction_slugs": ["actor"],
            "language": "Казахский / Русский",
            "description": "Театральные и актёрские программы КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Режиссура кино и телевидения (бакалавр)",
            "direction_slugs": ["film-director"],
            "language": "Казахский / Русский",
            "description": "Кинематографические программы КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Вокальное искусство (бакалавр)",
            "direction_slugs": ["musician"],
            "language": "Казахский / Русский",
            "description": "Вокальные программы КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Инструментальное исполнительство (бакалавр)",
            "direction_slugs": ["musician"],
            "language": "Казахский / Русский",
            "description": "Инструментальные программы КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Операторское искусство (бакалавр)",
            "direction_slugs": ["cinematographer"],
            "language": "Казахский / Русский",
            "description": "Операторское направление КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Дизайн интерьера (бакалавр)",
            "direction_slugs": ["design", "architect"],
            "language": "Казахский / Русский",
            "description": "Интерьерный дизайн КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Арт-менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "explore-creative"],
            "language": "Казахский / Русский",
            "description": "Арт-менеджмент КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Режиссура анимационного фильма (бакалавр)",
            "direction_slugs": ["film-director", "design-digital-art"],
            "language": "Казахский / Русский",
            "description": "Анимационная режиссура КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Грим и сценография (бакалавр)",
            "direction_slugs": ["makeup-artist-film"],
            "language": "Казахский / Русский",
            "description": "Сценография и художественный образ КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Музыкальное образование (бакалавр)",
            "direction_slugs": ["musician", "school-teacher"],
            "language": "Казахский / Русский",
            "description": "Музыкально-педагогические программы КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Музыковедение (бакалавр)",
            "direction_slugs": ["musician", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Теория и история музыки, музыкальная критика в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Режиссура театра (бакалавр)",
            "direction_slugs": ["actor", "film-director", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Режиссура драматического и музыкального театра в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Сценография (бакалавр)",
            "direction_slugs": ["actor", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Художественное оформление спектаклей и театральных постановок в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Изобразительное искусство (бакалавр)",
            "direction_slugs": ["design", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Живопись, скульптура и декоративное искусство в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Промышленный дизайн (бакалавр)",
            "direction_slugs": ["design", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Проектирование промышленных изделий и предметного дизайна в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Звукорежиссура кино и ТВ (бакалавр)",
            "direction_slugs": ["cinematographer", "akinator-stage-media"],
            "language": "Казахский / Русский",
            "description": "Звукорежиссура аудиовизуальных произведений и звукозапись в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Хоровое и оркестровое дирижирование (бакалавр)",
            "direction_slugs": ["musician", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Дирижирование хоровыми и оркестровыми коллективами в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Традиционное музыкальное искусство (бакалавр)",
            "direction_slugs": ["musician", "akinator-creative-design"],
            "language": "Казахский",
            "description": "Казахские народные инструменты, традиционный жыр и айтыс в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Искусство эстрады (бакалавр)",
            "direction_slugs": ["actor", "musician", "akinator-stage-media"],
            "language": "Казахский / Русский",
            "description": "Эстрадное вокальное и инструментальное исполнительство в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Искусствоведение (бакалавр)",
            "direction_slugs": ["actor", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Теория и история изобразительного, театрального и кинематографического искусства в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Киноведение и кинодраматургия (бакалавр)",
            "direction_slugs": ["film-director", "cinematographer", "akinator-stage-media"],
            "language": "Казахский / Русский",
            "description": "Теория кино, написание сценариев и история кинематографа в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Композиция (бакалавр)",
            "direction_slugs": ["musician", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Сочинение музыкальных произведений и композиторское мастерство в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Артист театра и кино (бакалавр)",
            "direction_slugs": ["actor", "akinator-stage-media"],
            "language": "Казахский / Русский",
            "description": "Актёрское мастерство в драматическом, музыкальном и кукольном театре в КазНУИ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
    ],
    "academy-of-choreography": [
        {
            "name": "Арт-менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "explore-creative"],
            "language": "Казахский / Русский",
            "description": "Программа арт-менеджмента Академии хореографии.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Педагогика хореографического искусства (бакалавр)",
            "direction_slugs": ["school-teacher"],
            "language": "Казахский / Русский",
            "description": "Педагогическое направление Академии хореографии.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Балетмейстерское искусство (бакалавр)",
            "direction_slugs": ["actor", "musician", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Постановочное искусство и хореографическое мастерство в Академии хореографии.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Педагогика спортивного бального танца (бакалавр)",
            "direction_slugs": ["school-teacher", "akinator-education"],
            "language": "Казахский / Русский",
            "description": "Спортивные бальные танцы и педагогика хореографии в Академии хореографии.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Искусствоведение (бакалавр)",
            "direction_slugs": ["actor", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Теория и история искусства с акцентом на хореографии в Академии хореографии.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
    ],
    "aiu": [
        {
            "name": "Data Science (бакалавр)",
            "direction_slugs": ["data-science"],
            "language": "Английский",
            "description": "School of Information Technology and Engineering.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer"],
            "language": "Казахский / Русский",
            "description": "School of Law AIU.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Graphic design (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "School of Arts and Humanities.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Педагогика дошкольного образования (бакалавр)",
            "direction_slugs": ["kindergarten-teacher"],
            "language": "Казахский / Русский",
            "description": "Pedagogical Institute AIU.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Международное право (бакалавр)",
            "direction_slugs": ["lawyer", "law-public-administration"],
            "language": "Казахский / Русский / Английский",
            "description": "School of Law AIU — международное право.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship"],
            "language": "Казахский / Русский / Английский",
            "description": "School of Economics AIU.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Финансы (бакалавр)",
            "direction_slugs": ["finance-accounting", "finance-economics"],
            "language": "Казахский / Русский",
            "description": "School of Economics AIU — финансы.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Маркетинг (бакалавр)",
            "direction_slugs": ["marketing", "marketing-advertising"],
            "language": "Казахский / Русский",
            "description": "School of Economics AIU — маркетинг.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Переводческое дело (бакалавр)",
            "direction_slugs": ["translator"],
            "language": "Казахский / Русский",
            "description": "School of Arts and Humanities AIU — перевод.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Архитектурный дизайн (бакалавр)",
            "direction_slugs": ["design", "architect"],
            "language": "Казахский / Русский",
            "description": "Архитектурный дизайн School of Arts and Humanities AIU.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Психология (бакалавр)",
            "direction_slugs": ["psychologist"],
            "language": "Казахский / Русский",
            "description": "Психология School of Liberal Arts AIU.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Педагогика и методика начального обучения (бакалавр)",
            "direction_slugs": ["school-teacher"],
            "language": "Казахский / Русский",
            "description": "Начальное образование Pedagogical Institute AIU.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Информационные системы и технологии (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development"],
            "language": "Казахский / Русский / Английский",
            "description": "School of IT and Engineering AIU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Экология и природопользование (бакалавр)",
            "direction_slugs": ["ecologist"],
            "language": "Казахский / Русский / Английский",
            "description": "School of Natural Sciences AIU.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Computer Science (бакалавр)",
            "direction_slugs": ["software-engineer", "data-science"],
            "language": "Казахский / Русский / Английский",
            "description": "Computer Science School of IT and Engineering AIU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "История (бакалавр)",
            "direction_slugs": ["school-teacher"],
            "language": "Казахский / Русский",
            "description": "Историческое направление AIU.",
            "requirements": {"ent_subjects": ["Всемирная история", "География"]},
        },
        {
            "name": "Биология (бакалавр)",
            "direction_slugs": ["zoologist", "medicine-biology"],
            "language": "Казахский / Русский",
            "description": "Биологическое направление AIU.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Дизайн (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский / Английский",
            "description": "Дизайн School of Arts and Humanities AIU.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
    ],
    "qairu": [
        {
            "name": "AI and Machine Learning (бакалавр)",
            "direction_slugs": ["data-science", "artificial-intelligence"],
            "language": "Английский",
            "description": "Флагманская AI-программа QAIRU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Physical AI (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "artificial-intelligence"],
            "language": "Английский",
            "description": "Робототехника и интеллектуальные системы QAIRU.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
    ],
    "esil-university": [
        {
            "name": "Финансы (бакалавр)",
            "direction_slugs": ["finance-accounting", "finance-economics"],
            "language": "Казахский / Русский",
            "description": "Финансовое направление Esil University.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Вычислительная техника и ПО (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development"],
            "language": "Казахский / Русский",
            "description": "IT-направление Esil University.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer"],
            "language": "Казахский / Русский",
            "description": "Правовые программы Esil University.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship"],
            "language": "Казахский / Русский",
            "description": "Управленческое направление Esil University.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Экономика (бакалавр)",
            "direction_slugs": ["finance-economics"],
            "language": "Казахский / Русский",
            "description": "Экономическое направление Esil University.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Маркетинг (бакалавр)",
            "direction_slugs": ["marketing", "marketing-advertising"],
            "language": "Казахский / Русский",
            "description": "Маркетинговое направление Esil University.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Учёт и аудит (бакалавр)",
            "direction_slugs": ["finance-accounting"],
            "language": "Казахский / Русский",
            "description": "Учётно-аудиторское направление Esil University.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Информационные системы (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development"],
            "language": "Казахский / Русский",
            "description": "ИТ-инфраструктурное направление Esil University.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Туризм (бакалавр)",
            "direction_slugs": ["hospitality-manager"],
            "language": "Казахский / Русский",
            "description": "Туристическое направление Esil University.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "Социальная работа (бакалавр)",
            "direction_slugs": ["social-worker"],
            "language": "Казахский / Русский",
            "description": "Социальное направление Esil University.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Мировая экономика (бакалавр)",
            "direction_slugs": ["finance-economics"],
            "language": "Казахский / Русский",
            "description": "Направление мировой экономики Esil University.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Digital бизнес (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "business-entrepreneurship"],
            "language": "Казахский / Русский",
            "description": "Цифровой бизнес Esil University.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "HR-менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "project-management"],
            "language": "Казахский / Русский",
            "description": "HR-направление Esil University.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Бизнес-право (бакалавр)",
            "direction_slugs": ["lawyer", "akinator-words-communication"],
            "language": "Казахский / Русский",
            "description": "Правовое регулирование предпринимательской и экономической деятельности в Esil University.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Правовое обеспечение экономической безопасности (бакалавр)",
            "direction_slugs": ["lawyer", "akinator-words-communication"],
            "language": "Казахский / Русский",
            "description": "Обеспечение экономической и правовой безопасности предприятий в Esil University.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Информационные технологии и защита данных (бакалавр)",
            "direction_slugs": ["it-infrastructure-security", "akinator-it-data"],
            "language": "Казахский / Русский",
            "description": "Информационные технологии и кибербезопасность данных в Esil University.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Вычислительная техника и программное обеспечение (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development", "akinator-it-data"],
            "language": "Казахский / Русский",
            "description": "Разработка программного обеспечения и вычислительные системы Esil University.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Государственное и местное управление (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "akinator-business-sales"],
            "language": "Казахский / Русский",
            "description": "Государственное управление и государственная служба в Esil University.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
    ],
    "turan-astana": [
        {
            "name": "Digital-маркетинг (бакалавр)",
            "direction_slugs": ["marketing", "marketing-advertising"],
            "language": "Казахский / Русский",
            "description": "Маркетинговые программы Туран-Астана.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Дизайн (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "Дизайнерские программы Туран-Астана.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Психология (бакалавр)",
            "direction_slugs": ["psychologist"],
            "language": "Казахский / Русский",
            "description": "Гуманитарный факультет Туран-Астана.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer"],
            "language": "Казахский / Русский",
            "description": "Правовые программы Туран-Астана.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Экономика (бакалавр)",
            "direction_slugs": ["finance-economics"],
            "language": "Казахский / Русский",
            "description": "Экономическое направление Туран-Астана.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship"],
            "language": "Казахский / Русский",
            "description": "Управленческое направление Туран-Астана.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Финансы (бакалавр)",
            "direction_slugs": ["finance-accounting", "finance-economics"],
            "language": "Казахский / Русский",
            "description": "Финансовое направление Туран-Астана.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Переводческое дело (бакалавр)",
            "direction_slugs": ["translator"],
            "language": "Казахский / Русский",
            "description": "Лингвистическое направление Туран-Астана.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Туризм (бакалавр)",
            "direction_slugs": ["hospitality-manager"],
            "language": "Казахский / Русский",
            "description": "Туристическое направление Туран-Астана.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "Ресторанный и гостиничный бизнес (бакалавр)",
            "direction_slugs": ["hospitality-manager"],
            "language": "Казахский / Русский",
            "description": "Гостиничный и ресторанный бизнес Туран-Астана.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "Учёт и аудит (бакалавр)",
            "direction_slugs": ["finance-accounting"],
            "language": "Казахский / Русский",
            "description": "Учётно-аудиторское направление Туран-Астана.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Информационные системы (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development"],
            "language": "Казахский / Русский",
            "description": "IT-направление Туран-Астана.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Международное право (бакалавр)",
            "direction_slugs": ["lawyer", "law-public-administration"],
            "language": "Казахский / Русский",
            "description": "Международно-правовое направление Туран-Астана.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Декоративное искусство и этнодизайн (бакалавр)",
            "direction_slugs": ["design", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Этнический дизайн и декоративно-прикладное искусство Туран-Астана.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Вычислительная техника и программное обеспечение (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development", "akinator-it-data"],
            "language": "Казахский / Русский",
            "description": "Разработка ПО и компьютерные системы в Туран-Астана.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Государственное и местное управление (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "akinator-business-sales"],
            "language": "Казахский / Русский",
            "description": "Государственное управление на экономическом факультете Туран-Астана.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Правовое регулирование экономики (бакалавр)",
            "direction_slugs": ["lawyer", "akinator-words-communication"],
            "language": "Казахский / Русский",
            "description": "Правовые аспекты экономической деятельности в Туран-Астана.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Филология (бакалавр)",
            "direction_slugs": ["school-teacher", "akinator-education"],
            "language": "Казахский / Русский",
            "description": "Казахская и русская филология и лингвистические исследования в Туран-Астана.",
            "requirements": {"ent_subjects": ["Казахский/Русский язык", "Казахская/Русская литература"]},
        },
    ],
    "kazutb": [
        {
            "name": "Искусственный интеллект (бакалавр)",
            "direction_slugs": ["data-science", "artificial-intelligence"],
            "language": "Казахский / Русский",
            "description": "Факультет инжиниринга и информационных технологий КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Дизайн (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "Технологический факультет КазУТБ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Туризм (бакалавр)",
            "direction_slugs": ["hospitality-manager"],
            "language": "Казахский / Русский",
            "description": "Факультет экономики и бизнеса КазУТБ.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "Информационные системы (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development"],
            "language": "Казахский / Русский",
            "description": "IT-направление КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Экономика (бакалавр)",
            "direction_slugs": ["finance-economics"],
            "language": "Казахский / Русский",
            "description": "Экономическое направление КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship"],
            "language": "Казахский / Русский",
            "description": "Управленческое направление КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Финансы (бакалавр)",
            "direction_slugs": ["finance-accounting", "finance-economics"],
            "language": "Казахский / Русский",
            "description": "Финансовое направление КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Учёт и аудит (бакалавр)",
            "direction_slugs": ["finance-accounting"],
            "language": "Казахский / Русский",
            "description": "Учётно-аудиторское направление КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Автоматизация и управление (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "it-infrastructure-security"],
            "language": "Казахский / Русский",
            "description": "Инженерное направление автоматизации КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Нефтегазовое дело (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "civil-engineering"],
            "language": "Казахский / Русский",
            "description": "Нефтегазовое направление КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Горное дело (бакалавр)",
            "direction_slugs": ["mechanical-engineer"],
            "language": "Казахский / Русский",
            "description": "Горнодобывающее направление КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Экология (бакалавр)",
            "direction_slugs": ["ecologist"],
            "language": "Казахский / Русский",
            "description": "Экологическое направление КазУТБ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Биотехнология (бакалавр)",
            "direction_slugs": ["medicine-biology"],
            "language": "Казахский / Русский",
            "description": "Биотехнологическое направление КазУТБ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Ресторанное дело и гостиничный бизнес (бакалавр)",
            "direction_slugs": ["hospitality-manager"],
            "language": "Казахский / Русский",
            "description": "Ресторанно-гостиничное направление КазУТБ.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "IT-менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "it-development"],
            "language": "Казахский / Русский",
            "description": "IT-менеджмент КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Технология и конструирование изделий лёгкой промышленности (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "akinator-engineering-tech"],
            "language": "Казахский / Русский",
            "description": "Производство одежды и изделий из кожи на технологическом факультете КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Технология продовольственных продуктов (бакалавр)",
            "direction_slugs": ["food-production-tech", "akinator-food-hospitality"],
            "language": "Казахский / Русский",
            "description": "Технологии производства и переработки продовольствия на технологическом факультете КазУТБ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Государственное и местное управление (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "akinator-business-sales"],
            "language": "Казахский / Русский",
            "description": "Государственное управление и государственная служба на экономическом факультете КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Химическая технология органических веществ (бакалавр)",
            "direction_slugs": ["pharmacist", "akinator-medicine"],
            "language": "Казахский / Русский",
            "description": "Химические технологии и нефтехимия на инженерном факультете КазУТБ.",
            "requirements": {"ent_subjects": ["Биология", "Химия"]},
        },
        {
            "name": "Безопасность жизнедеятельности и защита окружающей среды (бакалавр)",
            "direction_slugs": ["fire-safety-engineer", "akinator-safety-rescue"],
            "language": "Казахский / Русский",
            "description": "Промышленная безопасность и охрана окружающей среды на инженерном факультете КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Технологические машины и оборудование (бакалавр)",
            "direction_slugs": ["mechanical-engineer", "akinator-engineering-tech"],
            "language": "Казахский / Русский",
            "description": "Проектирование и эксплуатация промышленного технологического оборудования КазУТБ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Международный туризм (бакалавр)",
            "direction_slugs": ["hospitality-manager", "akinator-food-hospitality"],
            "language": "Казахский / Русский",
            "description": "Международный туризм и событийный менеджмент на факультете экономики КазУТБ.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "Графический дизайн (бакалавр)",
            "direction_slugs": ["design", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Графический дизайн и визуальные коммуникации на технологическом факультете КазУТБ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Дизайн моды (бакалавр)",
            "direction_slugs": ["design", "akinator-creative-design"],
            "language": "Казахский / Русский",
            "description": "Модный дизайн и fashion-индустрия на технологическом факультете КазУТБ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "ИТ-технологии в сфере сервиса (бакалавр)",
            "direction_slugs": ["hospitality-manager", "it-development"],
            "language": "Казахский / Русский",
            "description": "Применение информационных технологий в индустрии сервиса и гостеприимства КазУТБ.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
    ],
    "eagi": [
        {
            "name": "Педагогика и психология (бакалавр)",
            "direction_slugs": ["psychologist", "school-teacher", "psychology-pedagogy"],
            "language": "Казахский / Русский",
            "description": "Педагогические программы ЕАГИ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Переводческое дело (бакалавр)",
            "direction_slugs": ["translator"],
            "language": "Казахский / Русский",
            "description": "Лингвистические программы ЕАГИ.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Финансы (бакалавр)",
            "direction_slugs": ["finance-accounting", "finance-economics"],
            "language": "Казахский / Русский",
            "description": "Финансовое направление ЕАГИ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer"],
            "language": "Казахский / Русский",
            "description": "Правовые программы ЕАГИ.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Дошкольное образование и воспитание (бакалавр)",
            "direction_slugs": ["kindergarten-teacher"],
            "language": "Казахский / Русский",
            "description": "Дошкольное образование ЕАГИ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Педагогика и методика начального обучения (бакалавр)",
            "direction_slugs": ["school-teacher"],
            "language": "Казахский / Русский",
            "description": "Начальное образование ЕАГИ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Казахский язык и литература (бакалавр)",
            "direction_slugs": ["school-teacher", "akinator-education"],
            "language": "Казахский",
            "description": "Казахская филология и методика преподавания казахского языка в ЕАГИ.",
            "requirements": {"ent_subjects": ["Казахский язык", "Казахская литература"]},
        },
        {
            "name": "История (бакалавр)",
            "direction_slugs": ["school-teacher", "akinator-education"],
            "language": "Казахский / Русский",
            "description": "Историческое образование и подготовка учителей истории в ЕАГИ.",
            "requirements": {"ent_subjects": ["Всемирная история", "География"]},
        },
        {
            "name": "Иностранный язык: два иностранных языка (бакалавр)",
            "direction_slugs": ["translator", "akinator-words-communication"],
            "language": "Казахский / Русский",
            "description": "Лингвистика и преподавание двух иностранных языков в ЕАГИ.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Уголовная юстиция (бакалавр)",
            "direction_slugs": ["lawyer", "akinator-words-communication"],
            "language": "Казахский / Русский",
            "description": "Уголовное право и криминалистическая деятельность в ЕАГИ.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
    ],
    "financial-academy": [
        {
            "name": "Финансы (бакалавр)",
            "direction_slugs": ["finance-accounting", "finance-economics"],
            "language": "Казахский / Русский",
            "description": "Финансовая академия — направление «Финансы».",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Информационные системы (бакалавр)",
            "direction_slugs": ["software-engineer", "it-development"],
            "language": "Казахский / Русский",
            "description": "IT-направление Финансовой академии.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
    ],
    "astana-university": [
        {
            "name": "Туризм (бакалавр)",
            "direction_slugs": ["hospitality-manager"],
            "language": "Казахский / Русский",
            "description": "Туристические программы Astana University.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "Дизайн (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "Дизайнерские программы Astana University.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
    ],
    "msu-kz-branch": [
        {
            "name": "Прикладная математика и информатика (бакалавр)",
            "direction_slugs": ["data-science", "software-engineer", "explore-numbers"],
            "language": "Русский",
            "description": "Факультет вычислительной математики и кибернетики МГУ-КФ.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
        {
            "name": "Экология и природопользование (бакалавр)",
            "direction_slugs": ["ecologist"],
            "language": "Русский",
            "description": "Географический факультет МГУ-КФ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
    ],
    "cardiff-kazakhstan": [
        {
            "name": "Computer Science (бакалавр)",
            "direction_slugs": ["software-engineer"],
            "language": "Английский",
            "description": "Программа компьютерных наук Cardiff University Kazakhstan.",
            "requirements": {"ent_subjects": ["Математика", "Информатика"]},
        },
        {
            "name": "Civil Engineering (бакалавр)",
            "direction_slugs": ["civil-engineering"],
            "language": "Английский",
            "description": "Инженерно-строительная программа Cardiff University Kazakhstan.",
            "requirements": {"ent_subjects": ["Математика", "Физика"]},
        },
    ],
    "kazgyuu": [
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer", "akinator-words-communication"],
            "language": "Казахский / Русский",
            "description": "Юридическое образование в Университете КАЗГЮУ им. М.С. Нарикбаева.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Международное право (бакалавр)",
            "direction_slugs": ["lawyer", "law-public-administration"],
            "language": "Казахский / Русский",
            "description": "Международно-правовые программы Университета КАЗГЮУ им. М.С. Нарикбаева.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Право и правоохранительная деятельность (бакалавр)",
            "direction_slugs": ["lawyer", "akinator-words-communication"],
            "language": "Казахский / Русский",
            "description": "Правоохранительная деятельность и уголовная юстиция КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Всемирная история", "Основы права"]},
        },
        {
            "name": "Маркетинг (бакалавр)",
            "direction_slugs": ["marketing", "marketing-advertising", "akinator-business-sales"],
            "language": "Казахский / Русский",
            "description": "Маркетинг и управление брендом в Школе бизнеса КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Экономика (бакалавр)",
            "direction_slugs": ["finance-economics", "akinator-business-sales"],
            "language": "Казахский / Русский",
            "description": "Экономика и наука о данных в Школе бизнеса КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Финансы (бакалавр)",
            "direction_slugs": ["finance-accounting", "finance-economics", "akinator-business-sales"],
            "language": "Казахский / Русский",
            "description": "Финансовый менеджмент и анализ в Школе бизнеса КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Менеджмент (бакалавр)",
            "direction_slugs": ["management-entrepreneurship", "akinator-business-sales"],
            "language": "Казахский / Русский",
            "description": "Управление бизнесом и проектный менеджмент в Школе бизнеса КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "IT в бизнесе (бакалавр)",
            "direction_slugs": ["it-development", "management-entrepreneurship", "akinator-it-data"],
            "language": "Казахский / Русский",
            "description": "Информационные технологии для бизнеса в Школе бизнеса КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Учёт и аудит (бакалавр)",
            "direction_slugs": ["finance-accounting", "akinator-business-sales"],
            "language": "Казахский / Русский",
            "description": "Бухгалтерский учёт, аудит и финансовая отчётность в КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Математика", "География"]},
        },
        {
            "name": "Журналистика (бакалавр)",
            "direction_slugs": ["journalist", "media-journalism", "akinator-stage-media"],
            "language": "Казахский / Русский",
            "description": "Аналитическая и расследовательская журналистика в КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Международные отношения (бакалавр)",
            "direction_slugs": ["translator", "law-public-administration", "akinator-words-communication"],
            "language": "Казахский / Русский",
            "description": "Международные отношения и дипломатия в КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Туризм (бакалавр)",
            "direction_slugs": ["hospitality-manager", "akinator-food-hospitality"],
            "language": "Казахский / Русский",
            "description": "Туризм и индустрия гостеприимства в КАЗГЮУ.",
            "requirements": {"ent_subjects": ["География", "Иностранный язык"]},
        },
        {
            "name": "Психология (бакалавр)",
            "direction_slugs": ["psychologist", "akinator-psychology-help"],
            "language": "Казахский / Русский",
            "description": "Психология и поведенческие науки в КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Биология", "География"]},
        },
        {
            "name": "Переводческое дело (бакалавр)",
            "direction_slugs": ["translator", "akinator-words-communication"],
            "language": "Казахский / Русский",
            "description": "Перевод и переводоведение на гуманитарном факультете КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Прикладная лингвистика (бакалавр)",
            "direction_slugs": ["translator", "akinator-words-communication"],
            "language": "Казахский / Русский",
            "description": "Прикладная лингвистика и языковые технологии в КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Иностранный язык", "Всемирная история"]},
        },
        {
            "name": "Казахский язык и лингвистика (бакалавр)",
            "direction_slugs": ["school-teacher", "akinator-education"],
            "language": "Казахский",
            "description": "Казахско-английская лингвистика и межкультурная коммуникация в КАЗГЮУ.",
            "requirements": {"ent_subjects": ["Казахский/Русский язык", "Казахская/Русская литература"]},
        },
    ],
    "akademiya-fizicheskoj-kultury": [
        {
            "name": "Физическая культура и спорт (бакалавр)",
            "direction_slugs": ["sports-coach"],
            "language": "Казахский / Русский",
            "description": "Подготовка учителей физической культуры и тренеров АФКиМС.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Тренер по национальным видам спорта (бакалавр)",
            "direction_slugs": ["sports-coach"],
            "language": "Казахский / Русский",
            "description": "Педагог-тренер по национальным видам спорта и спортивным играм АФКиМС.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Тренер по Qazaq kuresi (бакалавр)",
            "direction_slugs": ["sports-coach"],
            "language": "Казахский / Русский / Английский",
            "description": "Педагог-тренер по Qazaq kuresi АФКиМС.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
        {
            "name": "Инструктор-методист по физкультурно-оздоровительной работе (бакалавр)",
            "direction_slugs": ["sports-coach", "school-teacher"],
            "language": "Казахский / Русский",
            "description": "Подготовка инструкторов-методистов по массовой физкультурно-оздоровительной работе АФКиМС.",
            "requirements": {"ent_subjects": ["Творческий экзамен"]},
        },
    ],
}

_KNOWN_DIRECTION_SLUGS = (
    {s["slug"] for s in SECTIONS}
    | {s["slug"] for s in SPECIALTIES}
    | {n["slug"] for n in EXPLORE_NODES}
)
for _uni_slug, _programs in PROGRAMS_BY_UNIVERSITY_SLUG.items():
    for _prog in _programs:
        for _slug in _prog["direction_slugs"]:
            assert _slug in _KNOWN_DIRECTION_SLUGS, (
                f"{_uni_slug}/{_prog['name']}: unknown direction slug {_slug!r}"
            )


def _extract_ranking(rankings: list[str]) -> int | None:
    for line in rankings:
        match = re.search(r"#(\d+)", line)
        if match:
            return int(match.group(1))
    return None


_CAREERS_BY_DIRECTION: dict[str, list[str]] = {
    "akinator-medicine": ["Врач", "Клинический ординатор", "Медицинский исследователь", "Специалист общественного здравоохранения"],
    "akinator-it-data": ["Разработчик ПО", "Аналитик данных", "ML-инженер", "Системный администратор"],
    "akinator-engineering-tech": ["Инженер", "Проектировщик", "Технический специалист", "Инженер-исследователь"],
    "akinator-creative-design": ["Дизайнер", "Арт-директор", "Иллюстратор", "Архитектор"],
    "akinator-stage-media": ["Журналист", "Режиссёр", "Продюсер", "SMM-специалист"],
    "akinator-business-sales": ["Менеджер", "Финансовый аналитик", "Предприниматель", "Маркетолог"],
    "akinator-psychology-help": ["Психолог", "Коуч", "HR-специалист", "Социальный работник"],
    "akinator-education": ["Педагог", "Методист", "Преподаватель", "Воспитатель"],
    "akinator-words-communication": ["Юрист", "Переводчик", "PR-специалист", "Лингвист"],
    "akinator-animals-nature": ["Эколог", "Биолог", "Ветеринар", "Агроном"],
    "akinator-food-hospitality": ["Менеджер по туризму", "Event-менеджер", "Специалист гостеприимства", "Операционный менеджер"],
}

_WHO_ITS_FOR_BY_DIRECTION: dict[str, str] = {
    "akinator-medicine": "Для абитуриентов с интересом к медицине и готовностью к интенсивной естественнонаучной подготовке.",
    "akinator-it-data": "Для тех, кому интересны программирование, аналитика и цифровые технологии.",
    "akinator-engineering-tech": "Для абитуриентов с сильной математикой и интересом к технике, инженерии и прикладным системам.",
    "akinator-creative-design": "Для творческих абитуриентов с интересом к визуальным коммуникациям, дизайну и искусству.",
    "akinator-stage-media": "Для коммуникабельных абитуриентов, которым интересны медиа, сцена и работа с аудиторией.",
    "akinator-business-sales": "Для тех, кто хочет развиваться в бизнесе, экономике, финансах и управлении.",
    "akinator-psychology-help": "Для эмпатичных абитуриентов, которым интересна работа с людьми и развитие личности.",
    "akinator-education": "Для тех, кто хочет работать с детьми и подростками в образовательной среде.",
    "akinator-words-communication": "Для абитуриентов с интересом к языкам, праву, коммуникации и публичной речи.",
    "akinator-animals-nature": "Для тех, кому близки природа, экология, биология и устойчивое развитие.",
    "akinator-food-hospitality": "Для абитуриентов, которым интересны сервис, туризм и организация мероприятий.",
}


_DEFAULT_GRANT = {
    "name": "Государственный образовательный грант",
    "amount": "Полная оплата обучения",
    "conditions": "Конкурсный отбор по баллам ЕНТ",
}


_SPECIALTIES_BY_SLUG: dict[str, dict] = {s["slug"]: s for s in SPECIALTIES}


def _related_specialties(uni_data: dict, program_name: str) -> list[str]:
    name_lower = program_name.lower()
    matched: list[str] = []
    for group in uni_data.get("specialties", []):
        for specialty in group.get("programs", []):
            specialty_lower = specialty.lower()
            if specialty_lower in name_lower or name_lower in specialty_lower:
                matched.append(specialty)
    return matched


def _enrich_program(uni_data: dict, prog: dict) -> dict:
    # direction_slugs is now a list; use the first slug for specialty lookup
    # and career enrichment (the primary specialty intent of the program).
    direction = prog["direction_slugs"][0]
    specialty = _SPECIALTIES_BY_SLUG.get(direction)
    related = _related_specialties(uni_data, prog["name"])
    if specialty is not None:
        careers = prog.get("career_options") or specialty["professions"]
        who_its_for = prog.get("who_its_for") or specialty["description"]
    else:
        careers = prog.get("career_options") or _CAREERS_BY_DIRECTION.get(direction, [])
        who_its_for = prog.get("who_its_for") or _WHO_ITS_FOR_BY_DIRECTION.get(direction)
    if related:
        careers = list(dict.fromkeys(related + careers))

    description_parts = [prog["description"], uni_data["description"]]
    if uni_data.get("specialties_summary"):
        description_parts.append(uni_data["specialties_summary"])

    # requirements contains only program-specific admission data.
    # University-level fields (location, rankings, admission_summary,
    # admission_requirements) are stored on the University record and must
    # NOT be duplicated here — they would pollute every program response
    # with boilerplate that belongs to the university, not the program.
    requirements = {**prog.get("requirements", {})}
    if "ЕНТ" in uni_data.get("admission_summary", ""):
        requirements.setdefault("exams", ["ЕНТ"])

    return {
        **prog,
        "description": " ".join(part for part in description_parts if part),
        "who_its_for": who_its_for,
        "career_options": careers,
        "requirements": requirements,
        "deadlines": {},
        "grants": prog.get("grants") or [_DEFAULT_GRANT.copy()],
        "cost_per_year": prog.get("cost_per_year"),
    }



async def main() -> None:
    uni_by_slug = {u["slug"]: u for u in ASTANA_UNIVERSITIES}
    uni_inserted = uni_updated = uni_skipped = 0
    prog_inserted = prog_updated = prog_skipped = 0

    async with async_session() as db:
        for uni_slug, programs in PROGRAMS_BY_UNIVERSITY_SLUG.items():
            uni_data = uni_by_slug.get(uni_slug)
            if uni_data is None:
                raise ValueError(f"Unknown university slug in program map: {uni_slug}")

            result = await db.execute(
                select(University).where(University.name == uni_data["name"])
            )
            university = result.scalar_one_or_none()
            uni_payload = {
                "name": uni_data["name"],
                "country": uni_data["country"],
                "city": uni_data["city"],
                "website": uni_data["website"],
                "ranking": _extract_ranking(uni_data["rankings"]),
                "description": uni_data["description"],
            }

            if university is None:
                university = University(**uni_payload)
                db.add(university)
                await db.flush()
                uni_inserted += 1
            else:
                changed = False
                for field, value in uni_payload.items():
                    if getattr(university, field) != value:
                        setattr(university, field, value)
                        changed = True
                if changed:
                    uni_updated += 1
                else:
                    uni_skipped += 1

            for prog in programs:
                prog_payload = _enrich_program(uni_data, prog)
                result = await db.execute(
                    select(Program).where(
                        Program.university_id == university.id,
                        Program.name == prog_payload["name"],
                    )
                )
                existing = result.scalar_one_or_none()
                if existing is None:
                    db.add(Program(university_id=university.id, **prog_payload))
                    prog_inserted += 1
                else:
                    changed = False
                    for field in (
                        "direction_slugs",
                        "language",
                        "cost_per_year",
                        "description",
                        "who_its_for",
                        "career_options",
                        "requirements",
                        "deadlines",
                        "grants",
                    ):
                        if getattr(existing, field) != prog_payload.get(field):
                            setattr(existing, field, prog_payload[field])
                            changed = True
                    if changed:
                        prog_updated += 1
                    else:
                        prog_skipped += 1

        await db.commit()

    total_progs = sum(len(v) for v in PROGRAMS_BY_UNIVERSITY_SLUG.values())
    print(
        f"Astana universities — inserted: {uni_inserted}, updated: {uni_updated}, "
        f"skipped: {uni_skipped}. Total: {len(ASTANA_UNIVERSITIES)}"
    )
    print(
        f"Astana programs — inserted: {prog_inserted}, updated: {prog_updated}, "
        f"skipped: {prog_skipped}. Total mapped: {total_progs}"
    )


if __name__ == "__main__":
    asyncio.run(main())
