"""
MI (Multiple-Intelligences-style) methodology reference tables — junior's
(6-9) replacement for RIASEC, fixed by the model itself (8 categories), not
"question bank" content. See app/services/mi_service.py.
"""

# Russian labels — used server-side for the junior summary builder
# (report_service._build_junior_summary).
MI_LABELS: dict[str, str] = {
    "verbal": "Слова и истории",
    "logical": "Логика и счёт",
    "musical": "Музыка и ритм",
    "visual": "Картинки и образы",
    "bodily": "Движение и руки",
    "interpersonal": "Дружба и команда",
    "intrapersonal": "Своё мнение",
    "naturalistic": "Природа и животные",
}

# Kid-friendly clubs/activities per category — junior gets no professions
# (TZ_Profi.md §4.1), only "что стоит попробовать". Used to build
# `reinforce`/`compensate` in mi_service.development_plan.
MI_ACTIVITIES: dict[str, list[str]] = {
    "verbal": ["кружок чтения", "школьный театр", "сочинение сказок", "кружок иностранного языка"],
    "logical": ["шахматы", "конструктор LEGO", "кружок математики", "настольные игры-головоломки"],
    "musical": ["музыкальная школа", "хор", "кружок ритмики", "занятия на инструменте"],
    "visual": ["кружок рисования", "лепка", "мультипликация", "конструирование"],
    "bodily": ["спортивная секция", "танцы", "плавание", "гимнастика"],
    "interpersonal": ["командные игры", "кружок волонтёров", "детский театр", "скаутский клуб"],
    "intrapersonal": ["ведение дневника", "индивидуальные кружки по интересу", "настольные игры на одного"],
    "naturalistic": ["юннатский кружок", "живой уголок", "прогулки и наблюдение за природой", "мини-огород"],
}
