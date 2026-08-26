"""One-time helper: fills `direction_slugs` in
scripts/data/jinaq/specialty_direction_review.json with an LLM-drafted
proposal, per specialty NAME (not category — see that file's own _readme
and this project's established rule against category-based tagging).

This is a DRAFT for human review, not an authoritative mapping — run this,
then open the review file and check/correct entries before running
scripts/apply_jinaq_specialty_directions.py (which reads the *reviewed*
file, not this script). Left empty deliberately for names too generic to
confidently map to one specific profession (e.g. "Инженерия" alone could be
any engineering discipline, "Философия" has no matching profession in the
catalog at all) — an empty list is treated as an honest answer, not a gap
to be forced.

Run: python scripts/draft_fill_specialty_directions.py
"""
import json
import os

REVIEW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jinaq", "specialty_direction_review.json")


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


# Keyed by specialty name as it appears in the review file (matched via
# normalized lowercase/whitespace, not exact string, so casing/spacing
# typos here don't silently fail to match).
DRAFT: dict[str, list[str]] = {
    "Бизнес-администрирование": ["predprinimatel", "proektnyy-menedzher"],
    "Психология": ["psiholog-konsultant", "psiholog-issledovatel"],
    "Информатика": ["razrabotchik-programmnogo-obespecheniya", "sistemnyy-analitik"],
    "Экономика": ["ekonomist-analitik", "finansovyy-analitik"],
    "Медицина": ["vrach-obschey-praktiki"],
    "Компьютерные науки": ["razrabotchik-programmnogo-obespecheniya", "analitik-dannyh"],
    "Право": ["yurist-advokat"],
    "Международные отношения": ["diplomat"],
    "Информационные технологии": ["razrabotchik-programmnogo-obespecheniya", "sistemnyy-administrator"],
    "Биология": ["biolog"],
    "Юриспруденция": ["yurist-advokat"],
    "Образование": ["shkolnyy-uchitel", "prepodavatel-vuza"],
    "Механическая инженерия": ["inzhener-mehanik"],
    "Computer Science": ["razrabotchik-programmnogo-obespecheniya"],
    "Архитектура": ["arhitektor"],
    "Бакалавр наук в области компьютерных наук": ["razrabotchik-programmnogo-obespecheniya"],
    "Экономика и управление": ["ekonomist-analitik"],
    "Economics": ["ekonomist-analitik"],
    "Машиностроение": ["inzhener-mehanik", "inzhener-konstruktor"],
    "Фармация": ["farmatsevt"],
    "Medicine": ["vrach-obschey-praktiki"],
    "Менеджмент": ["proektnyy-menedzher"],
    "Гражданское строительство": ["inzhener-stroitel"],
    "Бакалавр бизнеса": ["predprinimatel"],
    "Стоматология": ["stomatolog"],
    "Прикладная информатика": ["razrabotchik-programmnogo-obespecheniya"],
    "Информационные системы и технологии": ["sistemnyy-analitik", "razrabotchik-programmnogo-obespecheniya"],
    "Математика": ["matematik"],
    "Журналистика": ["zhurnalist"],
    "Бакалавр делового администрирования": ["predprinimatel"],
    "Law": ["yurist-advokat"],
    "Педагогика": ["shkolnyy-uchitel"],
    "Физика": ["fizik"],
    "Бакалавр информационных технологий": ["razrabotchik-programmnogo-obespecheniya"],
    "Магистр делового администрирования (MBA)": ["predprinimatel", "proektnyy-menedzher"],
    "Бакалавр наук в области биологии": ["biolog"],
    "Бакалавриат по информатике": ["razrabotchik-programmnogo-obespecheniya"],
    "Psychology": ["psiholog-konsultant"],
    "Графический дизайн": ["graficheskiy-dizayner"],
    "Экология и охрана окружающей среды": ["inzhener-ekolog"],
    "Информационные системы": ["sistemnyy-analitik"],
    "Информатика и вычислительная техника": ["razrabotchik-programmnogo-obespecheniya"],
    "Медицинские науки": ["vrach-obschey-praktiki"],
    "Магистратура по международным отношениям": ["diplomat"],
    "Финансы": ["finansovyy-analitik", "finansovyy-konsultant"],
    "Медицина и хирургия": ["hirurg"],
    "Инженерия программного обеспечения": ["razrabotchik-programmnogo-obespecheniya"],
    "Дизайн": ["graficheskiy-dizayner"],
    "Прикладная математика и информатика": ["matematik", "razrabotchik-programmnogo-obespecheniya"],
    "Бакалавр наук в области бизнеса": ["predprinimatel"],
    "Строительство": ["inzhener-stroitel"],
    "Mechanical Engineering": ["inzhener-mehanik"],
    "Международный бизнес": ["predprinimatel", "biznes-perevodchik"],
    "Социальная работа": ["sotsialnyy-rabotnik"],
    "International Relations": ["diplomat"],
    "Агрономия": ["agronom"],
    "Автоматизация и управление": ["inzhener-po-avtomatizatsii-i-robototehnike"],
    "Бакалавр наук в области психологии": ["psiholog-konsultant"],
    "Бакалавр образования": ["shkolnyy-uchitel"],
    "Business Administration": ["predprinimatel"],
    "Physics": ["fizik"],
    "Анимация": ["animator-2d-3d"],
    "Сестринское дело": ["meditsinskaya-sestra-medbrat"],
    "Бакалавриат по бизнес-администрированию": ["predprinimatel"],
    "Бакалавриат по праву": ["yurist-advokat"],
    "Биотехнология": ["issledovatel-v-oblasti-biotehnologiy"],
    "Экология и природопользование": ["inzhener-ekolog"],
    "Педагогическое образование": ["shkolnyy-uchitel"],
    "Физическая культура и спорт": ["trener-po-sportu"],
    "Политология": ["gosudarstvennyy-sluzhaschiy"],
    "Бакалавр наук в области образования": ["shkolnyy-uchitel"],
    "Педагогика и психология": ["shkolnyy-uchitel", "psiholog-konsultant"],
    "Начальное Образование": ["shkolnyy-uchitel"],
    "Электротехника и электроника": ["inzhener-elektrik"],
    "Медицина и здравоохранение": ["vrach-obschey-praktiki"],
    "Бакалавр здравоохранения": ["vrach-obschey-praktiki"],
    "Biology": ["biolog"],
    "Педиатрия": ["pediatr"],
    "Бакалавр наук в области здравоохранения": ["vrach-obschey-praktiki"],
    "Бакалавриат по биологии": ["biolog"],
    "Экономика и менеджмент": ["ekonomist-analitik"],
    "Architecture": ["arhitektor"],
    "Дизайн интерьера": ["dizayner-interera"],
    "Факультет образования": ["shkolnyy-uchitel"],
    "Медицинская биология": ["biolog"],
    "Бакалавр искусств в области психологии": ["psiholog-konsultant"],
    "Business": ["predprinimatel"],
    "Бакалавр искусств в области бизнеса": ["predprinimatel"],
    "Специальное образование": ["defektolog"],
    "Маркетинг": ["marketolog"],
    "Магистратура по психологии": ["psiholog-konsultant"],
    "Музыка": ["muzykant-ispolnitel"],
    "Медицинская сестринская деятельность": ["meditsinskaya-sestra-medbrat"],
    "Бакалавр компьютерных наук": ["razrabotchik-programmnogo-obespecheniya"],
    "Биологические науки": ["biolog"],
    "Горное дело": ["gornyy-inzhener"],
    "Агробиологические науки": ["agronom"],
    "Mathematics": ["matematik"],
    "Живопись": ["hudozhnik"],
    "Композиция": ["kompozitor"],
    "Изобразительное искусство": ["hudozhnik"],
    "Физиотерапия": ["fizioterapevt-massazhist"],
    "Jurisprudence": ["yurist-advokat"],
    "Бакалавриат по экономике и управлению": ["ekonomist-analitik"],
    "Information Technology": ["razrabotchik-programmnogo-obespecheniya"],
    "Dentistry": ["stomatolog"],
    "Ветеринария": ["veterinar"],
    "Ветеринарная медицина": ["veterinar"],
    "Туризм": ["upravlyayuschiy-otelem-restoranom"],
    "Электроэнергетика и электротехника": ["inzhener-energetik"],
    "Pharmacy": ["farmatsevt"],
    "Бакалавр психологии": ["psiholog-konsultant"],
    "Бакалавр права": ["yurist-advokat"],
    "Скульптура": ["hudozhnik"],
    "Музыкальное исполнительство": ["muzykant-ispolnitel"],
    "Музыкальная педагогика": ["prepodavatel-iskusstva"],
    "Лечебное дело": ["vrach-obschey-praktiki"],
    "Бакалавриат по экономике": ["ekonomist-analitik"],
    "Экология и природные ресурсы": ["inzhener-ekolog"],
    "Бакалавриат по психологии": ["psiholog-konsultant"],
    "Магистратура по менеджменту": ["proektnyy-menedzher"],
    "Finance": ["finansovyy-analitik"],
    "Electrical Engineering": ["inzhener-elektrik"],
    "Кибербезопасность": ["inzhener-po-kiberbezopasnosti"],
    "Факультет экономики и управления": ["ekonomist-analitik"],
    "Магистратура по информатике": ["razrabotchik-programmnogo-obespecheniya"],
    "Компьютерная инженерия": ["razrabotchik-programmnogo-obespecheniya"],
    "Магистратура по биологии": ["biolog"],
    "Chemistry": ["himik"],
    "Бухгалтерский учет": ["buhgalter"],
    "Management": ["proektnyy-menedzher"],
    "Nursing": ["meditsinskaya-sestra-medbrat"],
    "Гражданская инженерия": ["inzhener-stroitel"],
    "Бакалавриат по компьютерным наукам": ["razrabotchik-programmnogo-obespecheniya"],
    "Автоматизация технологических процессов и производств": ["inzhener-po-avtomatizatsii-i-robototehnike"],
    "Химия": ["himik"],
    "Биотехнологии": ["issledovatel-v-oblasti-biotehnologiy"],
    "Нефтегазовое дело": ["burovoy-inzhener-neftegazovoe-delo"],
    "Факультет сельского хозяйства": ["agronom"],
    "Факультет медицины": ["vrach-obschey-praktiki"],
    "Экология и окружающая среда": ["inzhener-ekolog"],
    "Business Management": ["proektnyy-menedzher"],
    "Материаловедение и инженерия": ["metallurg"],
    "Инженерия окружающей среды": ["inzhener-ekolog"],
    "Бакалавр в области управления бизнесом": ["predprinimatel"],
    "Спортивная тренировка": ["trener-po-sportu"],
    "Civil Engineering": ["inzhener-stroitel"],
    "Applied Mathematics and Informatics": ["matematik"],
    "Data Science": ["analitik-dannyh"],
    "Образование и педагогика": ["shkolnyy-uchitel"],
    "Градостроительство": ["urbanist-gradostroitel"],
    "Теплоэнергетика и теплотехника": ["inzhener-energetik"],
    "Зоотехния": ["veterinar"],
    "Финансы и бухгалтерский учет": ["buhgalter", "finansovyy-analitik"],
    "Физическая культура": ["trener-po-sportu"],
    "Электротехника и информационные технологии": ["inzhener-elektrik"],
    "Педагогика и образование": ["shkolnyy-uchitel"],
    "Естественные науки, математика и статистика": ["matematik"],
    "Информационно-коммуникационные технологии": ["razrabotchik-programmnogo-obespecheniya"],
    "Информационные и коммуникационные технологии": ["razrabotchik-programmnogo-obespecheniya"],
    "Педагогика и методика начального образования": ["shkolnyy-uchitel"],
    "Бакалавр в области компьютерных наук": ["razrabotchik-programmnogo-obespecheniya"],
    "Бизнес и менеджмент": ["predprinimatel"],
    "Геология": ["geolog"],
    "Journalism": ["zhurnalist"],
    "Information Systems and Technologies": ["sistemnyy-analitik"],
    "Науки о жизни": ["biolog"],
    "Бакалавр медицины": ["vrach-obschey-praktiki"],
    "Журналистика и коммуникации": ["zhurnalist"],
    "Бакалавр делового администрирования (BBA)": ["predprinimatel"],
    "Магистратура по праву": ["yurist-advokat"],
    "Business and Management": ["predprinimatel"],
    "Information Systems": ["sistemnyy-analitik"],
    "Экология": ["inzhener-ekolog"],
    "Интерьерный дизайн": ["dizayner-interera"],
    "Дирижирование": ["kompozitor"],
    "Учет и аудит": ["auditor"],
    "Электроэнергетика": ["inzhener-energetik"],
    "Информационная безопасность": ["inzhener-po-kiberbezopasnosti"],
    "Ресторанное дело и гостиничный бизнес": ["upravlyayuschiy-otelem-restoranom"],
    "Бакалавр наук в области информатики": ["razrabotchik-programmnogo-obespecheniya"],
    "Программная инженерия": ["razrabotchik-programmnogo-obespecheniya"],
    "Бухгалтерский учет, анализ и аудит": ["buhgalter"],
    "Лесное хозяйство": ["lesnichiy"],
    "Туризм и рекреация": ["upravlyayuschiy-otelem-restoranom"],
    "Медиа и коммуникации": ["spetsialist-po-mediakommunikatsiyam"],
    "Переводческое дело": ["biznes-perevodchik"],
    "Социальные науки, журналистика и информация": ["zhurnalist"],
    "Педагогические Науки": ["shkolnyy-uchitel"],
    "Электроника и электротехника": ["inzhener-elektrik"],
    "Геофизика": ["geolog"],
    "Information Security": ["inzhener-po-kiberbezopasnosti"],
    "Перевод и переводоведение": ["biznes-perevodchik"],
    "Клиническая медицина": ["vrach-obschey-praktiki"],
    "Международная экономика и торговля": ["ekonomist-analitik"],
    "Финансы и кредит": ["finansovyy-analitik"],
    "Радиотехника": ["inzhener-elektrik"],
    "Международная торговля": ["predprinimatel"],
    "Бакалавр медицины и здравоохранения": ["vrach-obschey-praktiki"],
    "Информационные и вычислительные науки": ["razrabotchik-programmnogo-obespecheniya"],
    "Коммуникация": ["spetsialist-po-mediakommunikatsiyam"],
    "Агробизнес": ["agronom"],
    "Software Engineering": ["razrabotchik-programmnogo-obespecheniya"],
    "Магистр образования": ["shkolnyy-uchitel"],
    "Графика": ["graficheskiy-dizayner"],
    "Мода и текстиль": ["modeler"],
    "Инструментальное исполнительство": ["muzykant-ispolnitel"],
    "Туризм и гостиничное дело": ["upravlyayuschiy-otelem-restoranom"],
    "Управление воздушным движением": ["aviadispetcher"],
    "Электротехника": ["inzhener-elektrik"],
    "Электроника и телекоммуникации": ["inzhener-elektrik"],
    "Бакалавриат по образованию": ["shkolnyy-uchitel"],
    "Логистика и управление цепями поставок": ["logist", "direktor-po-logistike"],
    "Физиотерапия и реабилитация": ["fizioterapevt-massazhist"],
    "Мода и дизайн": ["modeler"],
    "Педагогика и методика начального обучения": ["shkolnyy-uchitel"],
    "Магистр финансов": ["finansovyy-analitik"],
    "Магистратура по бизнес-администрированию (MBA)": ["predprinimatel"],
    "Инженерная экология": ["inzhener-ekolog"],
    "Менеджмент и управление": ["proektnyy-menedzher"],
    "Медико-профилактическое дело": ["epidemiolog"],
    "Международное право": ["yurist-advokat"],
    "Бакалавр искусств в области коммуникаций": ["spetsialist-po-mediakommunikatsiyam"],
    "Правоохранительная деятельность": ["politseyskiy"],
    "Автоматизация и робототехника": ["inzhener-po-avtomatizatsii-i-robototehnike"],
    "Магистратура по экономике": ["ekonomist-analitik"],
    "Bachelor of Science in Computer Science": ["razrabotchik-programmnogo-obespecheniya"],
    "Cybersecurity": ["inzhener-po-kiberbezopasnosti"],
    "Computer Science and Computer Engineering": ["razrabotchik-programmnogo-obespecheniya"],
    "Applied Mathematics and Computer Science": ["matematik"],
    "Перевод и интерпретация": ["biznes-perevodchik"],
    "Электротехника и автоматизация": ["inzhener-elektrik"],
    "Бакалавр бизнес-администрирования": ["predprinimatel"],
    "Магистр информационных технологий": ["razrabotchik-programmnogo-obespecheniya"],
    "Магистратура по международному бизнесу": ["predprinimatel"],
    "Бакалавр медицины и хирургии": ["hirurg"],
    "Бакалавр наук (BSc) в области компьютерных наук": ["razrabotchik-programmnogo-obespecheniya"],

    # Added after the initial pass — 5 new professions were added to the
    # catalog specifically to cover these previously-unmappable clusters.
    "История": ["istorik"],
    "Бакалавриат по истории": ["istorik"],
    "History": ["istorik"],
    "Филология": ["filolog-lingvist"],
    "Philology": ["filolog-lingvist"],
    "Лингвистика": ["filolog-lingvist"],
    "Иностранные языки и литература": ["filolog-lingvist"],
    "Английский язык и литература": ["filolog-lingvist"],
    "Английская литература и язык": ["filolog-lingvist"],
    "Английская литература": ["filolog-lingvist"],
    "Корейский язык и литература": ["filolog-lingvist"],
    "Казахский язык и литература": ["filolog-lingvist"],
    "Китайский язык и литература": ["filolog-lingvist"],
    "Русский язык и литература": ["filolog-lingvist"],
    "Французский язык и литература": ["filolog-lingvist"],
    "Химическая инженерия": ["inzhener-himik"],
    "Chemical Engineering": ["inzhener-himik"],
    "Химическая технология": ["inzhener-himik"],
    "Химическая инженерия и технологии": ["inzhener-himik"],
    "Медицинская биохимия": ["meditsinskiy-laboratornyy-tehnolog"],
    "Биомедицинская инженерия": ["meditsinskiy-laboratornyy-tehnolog"],
    "Биомедицинские науки": ["meditsinskiy-laboratornyy-tehnolog"],
    "Медицинская лабораторная техника": ["meditsinskiy-laboratornyy-tehnolog"],
    "Теология": ["teolog-religioved"],
    "Магистратура по теологии": ["teolog-religioved"],
    "Библейские исследования": ["teolog-religioved"],

    # Deliberately left unmapped (not in this dict at all == stays []):
    # Инженерия, Инженерное дело, Бакалавр инженерии, Engineering,
    # Философия, Бакалавр искусств, Факультет инженерии, Факультет гуманитарных наук,
    # Бакалавр гуманитарных наук, Бакалавр наук, Естественные науки,
    # Бакалавр наук в области инженерии, Английский язык и литература,
    # Социальные науки, Китайский язык и литература, Факультет естественных наук,
    # Гуманитарные науки, Медицинская биохимия, Биомедицинская инженерия,
    # Лингвистика, History, Английская литература и язык,
    # Философия, политика и экономика, Химическая инженерия, Химическая технология,
    # Теология, Услуги, Philosophy, Философия, политика и экономика (PPE),
    # Иностранные языки и литература, Корейский язык и литература,
    # Морская инженерия, Philology, Бакалавриат по истории, Казахский язык и
    # литература, Искусство и дизайн, Бакалавр социальных наук, Библейские
    # исследования, Design, Русский язык и литература, Искусство и
    # гуманитарные науки, Музыкология, Магистр наук, Бакалавр инженерных наук,
    # Аэрокосмическая инженерия, Aerospace Engineering, Бакалавриат по инженерии,
    # Магистратура по теологии, Химическая инженерия и технологии,
    # Общественные науки, Бизнес, управление и право, Бакалавриат по философии,
    # Магистратура по философии, Английская литература, Биомедицинские науки,
    # Bachelor of Engineering, Бакалавр дизайна, Магистр искусств,
    # Медицинская лабораторная техника, Французский язык и литература
}


def main() -> None:
    with open(REVIEW_PATH, encoding="utf-8") as f:
        review = json.load(f)

    valid_slugs = {d["slug"] for d in review["available_directions"]}
    draft_by_key = {_normalize(name): slugs for name, slugs in DRAFT.items()}

    matched = 0
    unmatched_draft_keys = set(draft_by_key.keys())
    bad_slugs: list[str] = []

    for specialty in review["specialties"]:
        key = _normalize(specialty["name"])
        if key in draft_by_key:
            slugs = draft_by_key[key]
            for slug in slugs:
                if slug not in valid_slugs:
                    bad_slugs.append(f"{specialty['name']!r} -> {slug!r}")
            specialty["direction_slugs"] = slugs
            matched += 1
            unmatched_draft_keys.discard(key)

    with open(REVIEW_PATH, "w", encoding="utf-8") as f:
        json.dump(review, f, ensure_ascii=False, indent=2)

    print(f"Filled {matched}/{len(review['specialties'])} specialties with a draft mapping")
    print(f"Left {len(review['specialties']) - matched} empty (too generic / no confident match)")
    if unmatched_draft_keys:
        print(f"WARNING: {len(unmatched_draft_keys)} draft dict keys never matched a specialty name (typo?):")
        for k in unmatched_draft_keys:
            print(f"  {k!r}")
    if bad_slugs:
        print(f"WARNING: {len(bad_slugs)} referenced slugs don't exist in available_directions:")
        for b in bad_slugs:
            print(f"  {b}")


if __name__ == "__main__":
    main()
