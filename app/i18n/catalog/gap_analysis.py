"""Gap-analysis comment strings (KZ-307). Was `comment=` literals in
`app/services/gap_analysis_service.py`. `kk` LLM-primary, native review pending.

NOT here: the `_*_KEYS` / `_*_TERMS` sets in gap_analysis_service — those match
Russian substrings in backend requirement/artifact data, they are not UI copy
(same rule as the frontend KZ-206 "backend data" literals).

`exam_grade_time` carries a `{grade}` placeholder — formatted at the call site.
"""

RU = {
    "gpa_no_data": "Нет данных о среднем балле",
    "lang_cert_found": "Языковой сертификат обнаружен в достижениях",
    "lang_activity_found": "Обнаружены языковые курсы или активности в профиле",
    "lang_no_data": "Нет данных об уровне языка",
    "exam_result_found": "Результат экзамена обнаружен в профиле",
    "exam_grade_time": "{grade} класс — есть время подготовиться к экзаменам",
    "exam_no_data": "Нет данных о результатах экзаменов",
    "portfolio_ready": "Есть достижения или профессиональный опыт — портфолио готово",
    "portfolio_starter": "Есть хобби, клубы или спорт — можно оформить в портфолио",
    "portfolio_none": "Нет портфолио, достижений или профессионального опыта",
    "not_enough_data": "Недостаточно данных для оценки",
}

KK = {
    "gpa_no_data": "Орта балл туралы дерек жоқ",
    "lang_cert_found": "Жетістіктерден тіл сертификаты табылды",
    "lang_activity_found": "Профильден тіл курстары немесе белсенді әрекеттер табылды",
    "lang_no_data": "Тіл деңгейі туралы дерек жоқ",
    "exam_result_found": "Профильден емтихан нәтижесі табылды",
    "exam_grade_time": "{grade}-сынып — емтихандарға дайындалуға уақыт бар",
    "exam_no_data": "Емтихан нәтижелері туралы дерек жоқ",
    "portfolio_ready": "Жетістіктер немесе кәсіби тәжірибе бар — портфолио дайын",
    "portfolio_starter": "Хобби, клубтар не спорт бар — портфолиоға рәсімдеуге болады",
    "portfolio_none": "Портфолио, жетістіктер не кәсіби тәжірибе жоқ",
    "not_enough_data": "Бағалауға дерек жеткіліксіз",
}
