"""
MI (Multiple-Intelligences-style) methodology reference tables — junior's
(6-9) replacement for RIASEC, fixed by the model itself (8 categories), not
"question bank" content. See app/services/mi_service.py.
"""

# Russian labels — used server-side for junior interest_map/exploration
# content (report_v2_assembler.py) and MI evidence text (report_narrative_context.py).
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

# Short, human strength-observation sentence per MI category — richer than
# MI_LABELS' bare category name. Used as the evidence text for interest
# items feeding fallback strength cards (report_narrative_context.py);
# interest_map (all 8 spheres) uses the bare MI_LABELS name instead.
MI_STRENGTH_PHRASES: dict[str, str] = {
    "verbal": "Любишь слова и истории и умеешь ими увлечь",
    "logical": "Любишь находить закономерности и решать головоломки",
    "musical": "Тонко чувствуешь ритм и музыку",
    "visual": "Легко представляешь образы и картинки в голове",
    "bodily": "Учишься через движение и действие руками",
    "interpersonal": "Легко находишь общий язык и дружишь",
    "intrapersonal": "Хорошо понимаешь, что сам думаешь и чувствуешь",
    "naturalistic": "Замечаешь и любишь всё, что связано с природой",
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
