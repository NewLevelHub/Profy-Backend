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
from scripts.seed_akinator_content import SECTIONS, SPECIALTIES

# direction_slugs = list of akinator section/specialty slugs from seed_akinator_content.py
PROGRAMS_BY_UNIVERSITY_SLUG: dict[str, list[dict]] = {
    "nazarbayev-university": [
        {
            "name": "Computer Science (бакалавр)",
            "direction_slugs": ["software-engineer"],
            "language": "Английский",
            "description": "Программа School of Engineering and Digital Sciences по компьютерным наукам.",
        },
        {
            "name": "Doctor of Medicine (6 лет)",
            "direction_slugs": ["general-medicine"],
            "language": "Английский",
            "description": "6-летняя медицинская программа School of Medicine (NUSOM).",
        },
        {
            "name": "Business Administration (BBA)",
            "direction_slugs": ["management-entrepreneurship"],
            "language": "Английский",
            "description": "Программа Graduate School of Business.",
        },
    ],
    "enu": [
        {
            "name": "Информационные технологии (бакалавр)",
            "direction_slugs": ["software-engineer"],
            "language": "Казахский / Русский / Английский",
            "description": "Факультет информационных технологий ЕНУ.",
        },
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer"],
            "language": "Казахский / Русский",
            "description": "Юридический факультет ЕНУ.",
        },
        {
            "name": "Экология и природопользование (бакалавр)",
            "direction_slugs": ["ecologist"],
            "language": "Казахский / Русский",
            "description": "Естественнонаучные программы ЕНУ.",
        },
    ],
    "mnu": [
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer"],
            "language": "Казахский / Русский / Английский",
            "description": "MNU Law School.",
        },
        {
            "name": "Finance (бакалавр)",
            "direction_slugs": ["finance-accounting"],
            "language": "Английский",
            "description": "International School of Economics.",
        },
        {
            "name": "Psychology (бакалавр)",
            "direction_slugs": ["psychologist"],
            "language": "Английский",
            "description": "School of Liberal Arts.",
        },
        {
            "name": "International Journalism (бакалавр)",
            "direction_slugs": ["journalist"],
            "language": "Английский",
            "description": "International School of Journalism.",
        },
    ],
    "aitu": [
        {
            "name": "Software Engineering (бакалавр)",
            "direction_slugs": ["software-engineer"],
            "language": "Английский",
            "description": "Школа программной инженерии AITU.",
        },
        {
            "name": "Big Data Analysis (бакалавр)",
            "direction_slugs": ["data-science"],
            "language": "Английский",
            "description": "Школа искусственного интеллекта и науки о данных.",
        },
        {
            "name": "Digital Journalism (бакалавр)",
            "direction_slugs": ["journalist"],
            "language": "Английский",
            "description": "Школа креативных индустрий.",
        },
    ],
    "kazatu": [
        {
            "name": "Агроинженерия (бакалавр)",
            "direction_slugs": ["agronomist"],
            "language": "Казахский / Русский",
            "description": "Технический факультет КазАТИУ.",
        },
        {
            "name": "Ветеринария (бакалавр)",
            "direction_slugs": ["veterinary-zootechnics"],
            "language": "Казахский / Русский",
            "description": "Факультет ветеринарии и технологии животноводства.",
        },
        {
            "name": "Архитектура и дизайн (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "Факультет управления земельными ресурсами, архитектуры и дизайна.",
        },
    ],
    "amu": [
        {
            "name": "Общая медицина (бакалавриат)",
            "direction_slugs": ["general-medicine"],
            "language": "Казахский / Русский",
            "description": "Лечебное направление Медицинского университета Астана.",
        },
        {
            "name": "Фармация (бакалавр)",
            "direction_slugs": ["pharmacist"],
            "language": "Казахский / Русский",
            "description": "Фармацевтическое направление МУА.",
        },
        {
            "name": "Сестринское дело (бакалавр)",
            "direction_slugs": ["akinator-medicine"],
            "language": "Казахский / Русский",
            "description": "Направления кинезитерапии и эрготерапии.",
        },
    ],
    "kaznui": [
        {
            "name": "Графический дизайн (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "Направление «Мода, дизайн» КазНУИ.",
        },
        {
            "name": "Театральное искусство (бакалавр)",
            "direction_slugs": ["actor"],
            "language": "Казахский / Русский",
            "description": "Театральные и актёрские программы КазНУИ.",
        },
        {
            "name": "Режиссура кино и телевидения (бакалавр)",
            "direction_slugs": ["film-director"],
            "language": "Казахский / Русский",
            "description": "Кинематографические программы КазНУИ.",
        },
    ],
    "academy-of-choreography": [
        {
            "name": "Арт-менеджмент (бакалавр)",
            "direction_slugs": ["akinator-stage-media"],
            "language": "Казахский / Русский",
            "description": "Программа арт-менеджмента Академии хореографии.",
        },
        {
            "name": "Педагогика хореографического искусства (бакалавр)",
            "direction_slugs": ["school-teacher"],
            "language": "Казахский / Русский",
            "description": "Педагогическое направление Академии хореографии.",
        },
    ],
    "aiu": [
        {
            "name": "Data Science (бакалавр)",
            "direction_slugs": ["data-science"],
            "language": "Английский",
            "description": "School of Information Technology and Engineering.",
        },
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer"],
            "language": "Казахский / Русский",
            "description": "School of Law AIU.",
        },
        {
            "name": "Graphic design (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "School of Arts and Humanities.",
        },
        {
            "name": "Педагогика дошкольного образования (бакалавр)",
            "direction_slugs": ["kindergarten-teacher"],
            "language": "Казахский / Русский",
            "description": "Pedagogical Institute AIU.",
        },
    ],
    "qairu": [
        {
            "name": "AI and Machine Learning (бакалавр)",
            "direction_slugs": ["data-science"],
            "language": "Английский",
            "description": "Флагманская AI-программа QAIRU.",
        },
        {
            "name": "Physical AI (бакалавр)",
            "direction_slugs": ["mechanical-engineer"],
            "language": "Английский",
            "description": "Робототехника и интеллектуальные системы QAIRU.",
        },
    ],
    "esil-university": [
        {
            "name": "Финансы (бакалавр)",
            "direction_slugs": ["finance-accounting"],
            "language": "Казахский / Русский",
            "description": "Финансовое направление Esil University.",
        },
        {
            "name": "Вычислительная техника и ПО (бакалавр)",
            "direction_slugs": ["software-engineer"],
            "language": "Казахский / Русский",
            "description": "IT-направление Esil University.",
        },
        {
            "name": "Юриспруденция (бакалавр)",
            "direction_slugs": ["lawyer"],
            "language": "Казахский / Русский",
            "description": "Правовые программы Esil University.",
        },
    ],
    "turan-astana": [
        {
            "name": "Digital-маркетинг (бакалавр)",
            "direction_slugs": ["marketing"],
            "language": "Казахский / Русский",
            "description": "Маркетинговые программы Туран-Астана.",
        },
        {
            "name": "Дизайн (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "Дизайнерские программы Туран-Астана.",
        },
        {
            "name": "Психология (бакалавр)",
            "direction_slugs": ["psychologist"],
            "language": "Казахский / Русский",
            "description": "Гуманитарный факультет Туран-Астана.",
        },
    ],
    "kazutb": [
        {
            "name": "Искусственный интеллект (бакалавр)",
            "direction_slugs": ["data-science"],
            "language": "Казахский / Русский",
            "description": "Факультет инжиниринга и информационных технологий КазУТБ.",
        },
        {
            "name": "Дизайн (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "Технологический факультет КазУТБ.",
        },
        {
            "name": "Туризм (бакалавр)",
            "direction_slugs": ["hospitality-manager"],
            "language": "Казахский / Русский",
            "description": "Факультет экономики и бизнеса КазУТБ.",
        },
    ],
    "eagi": [
        {
            "name": "Педагогика и психология (бакалавр)",
            "direction_slugs": ["akinator-education"],
            "language": "Казахский / Русский",
            "description": "Педагогические программы ЕАГИ.",
        },
        {
            "name": "Переводческое дело (бакалавр)",
            "direction_slugs": ["translator"],
            "language": "Казахский / Русский",
            "description": "Лингвистические программы ЕАГИ.",
        },
    ],
    "financial-academy": [
        {
            "name": "Финансы (бакалавр)",
            "direction_slugs": ["finance-accounting"],
            "language": "Казахский / Русский",
            "description": "Финансовая академия — направление «Финансы».",
        },
        {
            "name": "Информационные системы (бакалавр)",
            "direction_slugs": ["software-engineer"],
            "language": "Казахский / Русский",
            "description": "IT-направление Финансовой академии.",
        },
    ],
    "astana-university": [
        {
            "name": "Туризм (бакалавр)",
            "direction_slugs": ["hospitality-manager"],
            "language": "Казахский / Русский",
            "description": "Туристические программы Astana University.",
        },
        {
            "name": "Дизайн (бакалавр)",
            "direction_slugs": ["design"],
            "language": "Казахский / Русский",
            "description": "Дизайнерские программы Astana University.",
        },
    ],
    "msu-kz-branch": [
        {
            "name": "Прикладная математика и информатика (бакалавр)",
            "direction_slugs": ["data-science"],
            "language": "Русский",
            "description": "Факультет вычислительной математики и кибернетики МГУ-КФ.",
        },
        {
            "name": "Экология и природопользование (бакалавр)",
            "direction_slugs": ["ecologist"],
            "language": "Русский",
            "description": "Географический факультет МГУ-КФ.",
        },
    ],
    "cardiff-kazakhstan": [
        {
            "name": "Computer Science (бакалавр)",
            "direction_slugs": ["software-engineer"],
            "language": "Английский",
            "description": "Программа компьютерных наук Cardiff University Kazakhstan.",
        },
        {
            "name": "Civil Engineering (бакалавр)",
            "direction_slugs": ["civil-engineering"],
            "language": "Английский",
            "description": "Инженерно-строительная программа Cardiff University Kazakhstan.",
        },
    ],
}

_KNOWN_DIRECTION_SLUGS = {s["slug"] for s in SECTIONS} | {s["slug"] for s in SPECIALTIES}
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

    requirements = {
        "admission_summary": uni_data.get("admission_summary"),
        "admission_requirements": uni_data.get("admission_requirements", []),
        "location": uni_data.get("location"),
        "rankings": uni_data.get("rankings", []),
        **prog.get("requirements", {}),
    }
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
