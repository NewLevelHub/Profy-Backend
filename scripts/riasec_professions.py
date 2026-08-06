"""Localized RIASEC profession -> Holland-code + category reference data.

Replaces the original English/US-centric transcription (160 rows from a
`Profession.java` seed, no Kazakhstan/CIS relevance) with a Russian-language
catalog of professions that are actually reachable through Kazakhstani higher
education and represented in the labor market (see university-data/*.py for
the specialties this maps to on the program side).

Each entry also carries `category_slug` — one of the same ~10 categories used
for Program.direction_slug (scripts/seed_universities.py,
scripts/specialty_category_lookup.py) — so a matched profession can point
straight at real programs instead of relying on a second, disconnected
tagging pass.

Kept as raw section-ordered data; scripts/seed_riasec_directions.py dedupes
by title (first occurrence wins) and upserts into the `directions` table.
"""

PROFESSIONS: list[dict] = [
    # Realistic
    {"section": "Realistic", "title": "Инженер-механик", "holland_code": "RIS", "category_slugs": ["engineering-science"]},
    {"section": "Realistic", "title": "Пилот гражданской авиации", "holland_code": "RIE", "category_slugs": ["engineering-science"]},
    {"section": "Realistic", "title": "Авиадиспетчер", "holland_code": "SER", "category_slugs": ["engineering-science"]},
    {"section": "Realistic", "title": "Геодезист", "holland_code": "IRE", "category_slugs": ["engineering-science"]},
    {"section": "Realistic", "title": "Инженер-строитель", "holland_code": "RIE", "category_slugs": ["engineering-science"]},
    {"section": "Realistic", "title": "Инженер-электрик", "holland_code": "REI", "category_slugs": ["engineering-science"]},
    {"section": "Realistic", "title": "Агроном", "holland_code": "IRS", "category_slugs": ["biology-ecology"]},
    {"section": "Realistic", "title": "Ветеринар", "holland_code": "IRS", "category_slugs": ["biology-ecology"]},
    {"section": "Realistic", "title": "Лесничий", "holland_code": "RIS", "category_slugs": ["biology-ecology"]},
    {"section": "Realistic", "title": "Буровой инженер (нефтегазовое дело)", "holland_code": "RIE", "category_slugs": ["engineering-science"]},
    {"section": "Realistic", "title": "Машинист локомотива", "holland_code": "RES", "category_slugs": ["engineering-science"]},
    {"section": "Realistic", "title": "Технолог пищевого производства", "holland_code": "RCI", "category_slugs": ["engineering-science"]},
    {"section": "Realistic", "title": "Ландшафтный дизайнер", "holland_code": "RAE", "category_slugs": ["design-digital-art"]},
    {"section": "Realistic", "title": "Полицейский", "holland_code": "SER", "category_slugs": ["law-public-administration"]},
    {"section": "Realistic", "title": "Спасатель МЧС", "holland_code": "SRE", "category_slugs": ["law-public-administration"]},
    {"section": "Realistic", "title": "Системный администратор", "holland_code": "RIC", "category_slugs": ["it-development"]},
    {"section": "Realistic", "title": "Управляющий фермерским хозяйством", "holland_code": "ESR", "category_slugs": ["biology-ecology"]},

    # Investigative
    {"section": "Investigative", "title": "Разработчик программного обеспечения", "holland_code": "IRC", "category_slugs": ["it-development"]},
    {"section": "Investigative", "title": "Аналитик данных", "holland_code": "IRE", "category_slugs": ["data-science-ai"]},
    {"section": "Investigative", "title": "Специалист по искусственному интеллекту", "holland_code": "IRA", "category_slugs": ["data-science-ai"]},
    {"section": "Investigative", "title": "Геолог", "holland_code": "IRE", "category_slugs": ["engineering-science"]},
    {"section": "Investigative", "title": "Биолог", "holland_code": "IRE", "category_slugs": ["biology-ecology"]},
    {"section": "Investigative", "title": "Химик", "holland_code": "IRE", "category_slugs": ["engineering-science"]},
    {"section": "Investigative", "title": "Врач общей практики", "holland_code": "ISR", "category_slugs": ["medicine-pharmacy"]},
    {"section": "Investigative", "title": "Стоматолог", "holland_code": "ISR", "category_slugs": ["medicine-pharmacy"]},
    {"section": "Investigative", "title": "Фармацевт", "holland_code": "IES", "category_slugs": ["medicine-pharmacy"]},
    {"section": "Investigative", "title": "Психолог-исследователь", "holland_code": "IES", "category_slugs": ["psychology-pedagogy"]},
    {"section": "Investigative", "title": "Экономист-аналитик", "holland_code": "IAS", "category_slugs": ["finance-economics"]},
    {"section": "Investigative", "title": "Актуарий", "holland_code": "ISE", "category_slugs": ["finance-economics"]},
    {"section": "Investigative", "title": "Математик", "holland_code": "IRE", "category_slugs": ["engineering-science"]},
    {"section": "Investigative", "title": "Археолог", "holland_code": "IRE", "category_slugs": ["engineering-science"]},
    {"section": "Investigative", "title": "Метеоролог", "holland_code": "IRS", "category_slugs": ["engineering-science"]},
    {"section": "Investigative", "title": "Системный аналитик", "holland_code": "IER", "category_slugs": ["it-development"]},
    {"section": "Investigative", "title": "Исследователь в области биотехнологий", "holland_code": "IRS", "category_slugs": ["biology-ecology"]},
    {"section": "Investigative", "title": "Инженер-эколог", "holland_code": "IRE", "category_slugs": ["biology-ecology"]},

    # Artistic
    {"section": "Artistic", "title": "Архитектор", "holland_code": "AIR", "category_slugs": ["engineering-science", "design-digital-art"]},
    {"section": "Artistic", "title": "Графический дизайнер", "holland_code": "AES", "category_slugs": ["design-digital-art"]},
    {"section": "Artistic", "title": "Модельер", "holland_code": "ASR", "category_slugs": ["design-digital-art", "engineering-science"]},
    {"section": "Artistic", "title": "Художник", "holland_code": "ASI", "category_slugs": ["design-digital-art"]},
    {"section": "Artistic", "title": "Писатель / Копирайтер", "holland_code": "ASI", "category_slugs": ["media-marketing"]},
    {"section": "Artistic", "title": "Журналист", "holland_code": "ASE", "category_slugs": ["media-marketing"]},
    {"section": "Artistic", "title": "Режиссёр", "holland_code": "AES", "category_slugs": ["design-digital-art"]},
    {"section": "Artistic", "title": "Актёр", "holland_code": "AES", "category_slugs": ["design-digital-art"]},
    {"section": "Artistic", "title": "Хореограф", "holland_code": "AER", "category_slugs": ["design-digital-art"]},
    {"section": "Artistic", "title": "Музыкант-исполнитель", "holland_code": "ASI", "category_slugs": ["design-digital-art"]},
    {"section": "Artistic", "title": "Фотограф", "holland_code": "AES", "category_slugs": ["design-digital-art"]},
    {"section": "Artistic", "title": "Дизайнер интерьера", "holland_code": "AES", "category_slugs": ["design-digital-art"]},
    {"section": "Artistic", "title": "Аниматор (2D/3D)", "holland_code": "ARI", "category_slugs": ["design-digital-art"]},
    {"section": "Artistic", "title": "Преподаватель искусства", "holland_code": "ASE", "category_slugs": ["psychology-pedagogy"]},
    {"section": "Artistic", "title": "Искусствовед", "holland_code": "AIE", "category_slugs": ["design-digital-art"]},

    # Social
    {"section": "Social", "title": "Школьный учитель", "holland_code": "SAE", "category_slugs": ["psychology-pedagogy"]},
    {"section": "Social", "title": "Психолог-консультант", "holland_code": "SAE", "category_slugs": ["psychology-pedagogy"]},
    {"section": "Social", "title": "Медицинская сестра / медбрат", "holland_code": "SIA", "category_slugs": ["medicine-pharmacy"]},
    {"section": "Social", "title": "Логопед", "holland_code": "SAI", "category_slugs": ["psychology-pedagogy"]},
    {"section": "Social", "title": "Социальный работник", "holland_code": "SEA", "category_slugs": ["psychology-pedagogy"]},
    {"section": "Social", "title": "Воспитатель детского сада", "holland_code": "SAE", "category_slugs": ["psychology-pedagogy"]},
    {"section": "Social", "title": "HR-менеджер", "holland_code": "SEC", "category_slugs": ["business-management"]},
    {"section": "Social", "title": "Тренер по спорту", "holland_code": "SRE", "category_slugs": ["sport-physical-education"]},
    {"section": "Social", "title": "Гид-экскурсовод", "holland_code": "SEA", "category_slugs": ["business-management"]},
    {"section": "Social", "title": "Библиотекарь", "holland_code": "SAI", "category_slugs": ["psychology-pedagogy"]},
    {"section": "Social", "title": "Преподаватель вуза", "holland_code": "SEI", "category_slugs": ["psychology-pedagogy"]},
    {"section": "Social", "title": "Специалист по работе с молодёжью", "holland_code": "SEA", "category_slugs": ["psychology-pedagogy"]},
    {"section": "Social", "title": "Реабилитолог / Эрготерапевт", "holland_code": "SIE", "category_slugs": ["medicine-pharmacy"]},

    # Enterprising
    {"section": "Enterprising", "title": "Предприниматель", "holland_code": "ESA", "category_slugs": ["business-management"]},
    {"section": "Enterprising", "title": "Менеджер по продажам", "holland_code": "ESR", "category_slugs": ["business-management"]},
    {"section": "Enterprising", "title": "Директор по маркетингу", "holland_code": "ESA", "category_slugs": ["media-marketing"]},
    {"section": "Enterprising", "title": "Юрист / Адвокат", "holland_code": "ESA", "category_slugs": ["law-public-administration"]},
    {"section": "Enterprising", "title": "Дипломат", "holland_code": "ESA", "category_slugs": ["law-public-administration"]},
    {"section": "Enterprising", "title": "Финансовый консультант", "holland_code": "ESR", "category_slugs": ["finance-economics"]},
    {"section": "Enterprising", "title": "Государственный служащий", "holland_code": "ESA", "category_slugs": ["law-public-administration"]},
    {"section": "Enterprising", "title": "Риелтор", "holland_code": "ESA", "category_slugs": ["business-management"]},
    {"section": "Enterprising", "title": "Event-менеджер", "holland_code": "ESA", "category_slugs": ["business-management"]},
    {"section": "Enterprising", "title": "Страховой агент", "holland_code": "ESC", "category_slugs": ["finance-economics"]},
    {"section": "Enterprising", "title": "PR-менеджер", "holland_code": "EAS", "category_slugs": ["media-marketing"]},
    {"section": "Enterprising", "title": "Управляющий отелем / рестораном", "holland_code": "ESR", "category_slugs": ["business-management"]},
    {"section": "Enterprising", "title": "Биржевой брокер", "holland_code": "ESI", "category_slugs": ["finance-economics"]},
    {"section": "Enterprising", "title": "Директор по логистике", "holland_code": "ESC", "category_slugs": ["business-management"]},
    {"section": "Enterprising", "title": "Бизнес-переводчик", "holland_code": "ESA", "category_slugs": ["business-management"]},

    # Conventional
    {"section": "Conventional", "title": "Бухгалтер", "holland_code": "CSE", "category_slugs": ["finance-economics"]},
    {"section": "Conventional", "title": "Налоговый консультант", "holland_code": "CES", "category_slugs": ["finance-economics"]},
    {"section": "Conventional", "title": "Финансовый аналитик", "holland_code": "CSI", "category_slugs": ["finance-economics"]},
    {"section": "Conventional", "title": "Аудитор", "holland_code": "CSE", "category_slugs": ["finance-economics"]},
    {"section": "Conventional", "title": "Специалист по таможенному делу", "holland_code": "CEI", "category_slugs": ["law-public-administration"]},
    {"section": "Conventional", "title": "Секретарь-делопроизводитель", "holland_code": "ESC", "category_slugs": ["business-management"]},
    {"section": "Conventional", "title": "Специалист технической поддержки", "holland_code": "CSR", "category_slugs": ["it-development"]},
    {"section": "Conventional", "title": "Кредитный аналитик", "holland_code": "CES", "category_slugs": ["finance-economics"]},
    {"section": "Conventional", "title": "Специалист по кадровому делопроизводству", "holland_code": "ESC", "category_slugs": ["business-management"]},
    {"section": "Conventional", "title": "Архивариус", "holland_code": "CSE", "category_slugs": ["business-management"]},
    {"section": "Conventional", "title": "Специалист по стандартизации и сертификации", "holland_code": "CES", "category_slugs": ["engineering-science"]},
    {"section": "Conventional", "title": "Страховой андеррайтер", "holland_code": "CSE", "category_slugs": ["finance-economics"]},
    {"section": "Conventional", "title": "Специалист по закупкам", "holland_code": "CES", "category_slugs": ["business-management"]},
    {"section": "Conventional", "title": "Администратор баз данных", "holland_code": "CRI", "category_slugs": ["it-development"]},
]

assert len(PROFESSIONS) == len({p["title"] for p in PROFESSIONS}), "duplicate profession titles in PROFESSIONS"
