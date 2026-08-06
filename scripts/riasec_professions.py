"""Localized RIASEC profession -> Holland-code reference data.

Replaces the original English/US-centric transcription (160 rows from a
`Profession.java` seed, no Kazakhstan/CIS relevance) with a Russian-language
catalog of professions that are actually reachable through Kazakhstani higher
education and represented in the labor market.

The profession -> matching-programs link now lives directly on the program
side (see scripts/specialty_profession_map.py), not as a category on this
catalog — a profession only needs its name and Holland code here.

Kept as raw section-ordered data; scripts/seed_riasec_directions.py dedupes
by title (first occurrence wins) and upserts into the `directions` table.
"""

PROFESSIONS: list[dict] = [
    # Realistic
    {"section": "Realistic", "title": "Инженер-механик", "holland_code": "RIS"},
    {"section": "Realistic", "title": "Пилот гражданской авиации", "holland_code": "RIE"},
    {"section": "Realistic", "title": "Авиадиспетчер", "holland_code": "SER"},
    {"section": "Realistic", "title": "Геодезист", "holland_code": "IRE"},
    {"section": "Realistic", "title": "Инженер-строитель", "holland_code": "RIE"},
    {"section": "Realistic", "title": "Инженер-электрик", "holland_code": "REI"},
    {"section": "Realistic", "title": "Агроном", "holland_code": "IRS"},
    {"section": "Realistic", "title": "Ветеринар", "holland_code": "IRS"},
    {"section": "Realistic", "title": "Лесничий", "holland_code": "RIS"},
    {"section": "Realistic", "title": "Буровой инженер (нефтегазовое дело)", "holland_code": "RIE"},
    {"section": "Realistic", "title": "Машинист локомотива", "holland_code": "RES"},
    {"section": "Realistic", "title": "Технолог пищевого производства", "holland_code": "RCI"},
    {"section": "Realistic", "title": "Ландшафтный дизайнер", "holland_code": "RAE"},
    {"section": "Realistic", "title": "Полицейский", "holland_code": "SER"},
    {"section": "Realistic", "title": "Спасатель МЧС", "holland_code": "SRE"},
    {"section": "Realistic", "title": "Системный администратор", "holland_code": "RIC"},
    {"section": "Realistic", "title": "Управляющий фермерским хозяйством", "holland_code": "ESR"},

    # Investigative
    {"section": "Investigative", "title": "Разработчик программного обеспечения", "holland_code": "IRC"},
    {"section": "Investigative", "title": "Аналитик данных", "holland_code": "IRE"},
    {"section": "Investigative", "title": "Специалист по искусственному интеллекту", "holland_code": "IRA"},
    {"section": "Investigative", "title": "Геолог", "holland_code": "IRE"},
    {"section": "Investigative", "title": "Биолог", "holland_code": "IRE"},
    {"section": "Investigative", "title": "Химик", "holland_code": "IRE"},
    {"section": "Investigative", "title": "Врач общей практики", "holland_code": "ISR"},
    {"section": "Investigative", "title": "Стоматолог", "holland_code": "ISR"},
    {"section": "Investigative", "title": "Фармацевт", "holland_code": "IES"},
    {"section": "Investigative", "title": "Психолог-исследователь", "holland_code": "IES"},
    {"section": "Investigative", "title": "Экономист-аналитик", "holland_code": "IAS"},
    {"section": "Investigative", "title": "Актуарий", "holland_code": "ISE"},
    {"section": "Investigative", "title": "Математик", "holland_code": "IRE"},
    {"section": "Investigative", "title": "Археолог", "holland_code": "IRE"},
    {"section": "Investigative", "title": "Метеоролог", "holland_code": "IRS"},
    {"section": "Investigative", "title": "Системный аналитик", "holland_code": "IER"},
    {"section": "Investigative", "title": "Исследователь в области биотехнологий", "holland_code": "IRS"},
    {"section": "Investigative", "title": "Инженер-эколог", "holland_code": "IRE"},

    # Artistic
    {"section": "Artistic", "title": "Архитектор", "holland_code": "AIR"},
    {"section": "Artistic", "title": "Графический дизайнер", "holland_code": "AES"},
    {"section": "Artistic", "title": "Модельер", "holland_code": "ASR"},
    {"section": "Artistic", "title": "Художник", "holland_code": "ASI"},
    {"section": "Artistic", "title": "Писатель / Копирайтер", "holland_code": "ASI"},
    {"section": "Artistic", "title": "Журналист", "holland_code": "ASE"},
    {"section": "Artistic", "title": "Режиссёр", "holland_code": "AES"},
    {"section": "Artistic", "title": "Актёр", "holland_code": "AES"},
    {"section": "Artistic", "title": "Хореограф", "holland_code": "AER"},
    {"section": "Artistic", "title": "Музыкант-исполнитель", "holland_code": "ASI"},
    {"section": "Artistic", "title": "Фотограф", "holland_code": "AES"},
    {"section": "Artistic", "title": "Дизайнер интерьера", "holland_code": "AES"},
    {"section": "Artistic", "title": "Аниматор (2D/3D)", "holland_code": "ARI"},
    {"section": "Artistic", "title": "Преподаватель искусства", "holland_code": "ASE"},
    {"section": "Artistic", "title": "Искусствовед", "holland_code": "AIE"},

    # Social
    {"section": "Social", "title": "Школьный учитель", "holland_code": "SAE"},
    {"section": "Social", "title": "Психолог-консультант", "holland_code": "SAE"},
    {"section": "Social", "title": "Медицинская сестра / медбрат", "holland_code": "SIA"},
    {"section": "Social", "title": "Логопед", "holland_code": "SAI"},
    {"section": "Social", "title": "Социальный работник", "holland_code": "SEA"},
    {"section": "Social", "title": "Воспитатель детского сада", "holland_code": "SAE"},
    {"section": "Social", "title": "HR-менеджер", "holland_code": "SEC"},
    {"section": "Social", "title": "Тренер по спорту", "holland_code": "SRE"},
    {"section": "Social", "title": "Гид-экскурсовод", "holland_code": "SEA"},
    {"section": "Social", "title": "Библиотекарь", "holland_code": "SAI"},
    {"section": "Social", "title": "Преподаватель вуза", "holland_code": "SEI"},
    {"section": "Social", "title": "Специалист по работе с молодёжью", "holland_code": "SEA"},
    {"section": "Social", "title": "Реабилитолог / Эрготерапевт", "holland_code": "SIE"},

    # Enterprising
    {"section": "Enterprising", "title": "Предприниматель", "holland_code": "ESA"},
    {"section": "Enterprising", "title": "Менеджер по продажам", "holland_code": "ESR"},
    {"section": "Enterprising", "title": "Директор по маркетингу", "holland_code": "ESA"},
    {"section": "Enterprising", "title": "Юрист / Адвокат", "holland_code": "ESA"},
    {"section": "Enterprising", "title": "Дипломат", "holland_code": "ESA"},
    {"section": "Enterprising", "title": "Финансовый консультант", "holland_code": "ESR"},
    {"section": "Enterprising", "title": "Государственный служащий", "holland_code": "ESA"},
    {"section": "Enterprising", "title": "Риелтор", "holland_code": "ESA"},
    {"section": "Enterprising", "title": "Event-менеджер", "holland_code": "ESA"},
    {"section": "Enterprising", "title": "Страховой агент", "holland_code": "ESC"},
    {"section": "Enterprising", "title": "PR-менеджер", "holland_code": "EAS"},
    {"section": "Enterprising", "title": "Управляющий отелем / рестораном", "holland_code": "ESR"},
    {"section": "Enterprising", "title": "Биржевой брокер", "holland_code": "ESI"},
    {"section": "Enterprising", "title": "Директор по логистике", "holland_code": "ESC"},
    {"section": "Enterprising", "title": "Бизнес-переводчик", "holland_code": "ESA"},

    # Conventional
    {"section": "Conventional", "title": "Бухгалтер", "holland_code": "CSE"},
    {"section": "Conventional", "title": "Налоговый консультант", "holland_code": "CES"},
    {"section": "Conventional", "title": "Финансовый аналитик", "holland_code": "CSI"},
    {"section": "Conventional", "title": "Аудитор", "holland_code": "CSE"},
    {"section": "Conventional", "title": "Специалист по таможенному делу", "holland_code": "CEI"},
    {"section": "Conventional", "title": "Секретарь-делопроизводитель", "holland_code": "ESC"},
    {"section": "Conventional", "title": "Специалист технической поддержки", "holland_code": "CSR"},
    {"section": "Conventional", "title": "Кредитный аналитик", "holland_code": "CES"},
    {"section": "Conventional", "title": "Специалист по кадровому делопроизводству", "holland_code": "ESC"},
    {"section": "Conventional", "title": "Архивариус", "holland_code": "CSE"},
    {"section": "Conventional", "title": "Специалист по стандартизации и сертификации", "holland_code": "CES"},
    {"section": "Conventional", "title": "Страховой андеррайтер", "holland_code": "CSE"},
    {"section": "Conventional", "title": "Специалист по закупкам", "holland_code": "CES"},
    {"section": "Conventional", "title": "Администратор баз данных", "holland_code": "CRI"},
]

assert len(PROFESSIONS) == len({p["title"] for p in PROFESSIONS}), "duplicate profession titles in PROFESSIONS"
