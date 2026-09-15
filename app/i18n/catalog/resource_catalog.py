"""Roadmap "Дополнительный источник" resource catalog (KZ-307). Was
`RESOURCE_CATALOG` in `app/data/resource_catalog.py`.

`url` is shared across locales. `title` is a proper name (course/channel/tool/
org) — kept verbatim, not transliterated (KZ-501 rule for institution names).
`kind` is a short category word and IS translated. So a `kk` entry differs from
its `ru` twin only in `kind`.

NOT here: `CATEGORY_KEYWORDS` in `app/data/resource_catalog.py` — those match
Russian substrings in direction text, not UI copy (roadmap generation is
`ru`-locked until KZ-401/403).
"""

RU = {
    "catalog": {
        "tech": [
            {"title": "«Поколение Python»", "kind": "курс", "url": "https://stepik.org/course/58852"},
            {"title": "Алгоритмы: теория и практика. Структуры данных", "kind": "курс", "url": "https://stepik.org/course/1547"},
            {"title": "Wokwi — симулятор Arduino/ESP32", "kind": "инструмент", "url": "https://wokwi.com"},
            {"title": "Tinkercad Circuits", "kind": "инструмент", "url": "https://www.tinkercad.com/circuits"},
            {"title": "E-Olymp — задачник по программированию", "kind": "задачник", "url": "https://www.eolymp.com/ru/"},
        ],
        "creative_design": [
            {"title": "Азбука Рисования", "kind": "видео", "url": "https://www.youtube.com/@AzbukaR"},
            {"title": "SketchUp для начинающих", "kind": "видео", "url": "https://www.youtube.com/watch?v=XJU9WBLsx_M"},
            {"title": "Behance — портфолио", "kind": "платформа", "url": "https://www.behance.net"},
            {"title": "Tilda Publishing", "kind": "инструмент", "url": "https://tilda.cc/ru/"},
        ],
        "medicine": [
            {"title": "Анатомия человека. ЕГЭ/ОГЭ по биологии", "kind": "курс", "url": "https://stepik.org/course/209034"},
            {"title": "PhET — химические симуляции", "kind": "инструмент", "url": "https://phet.colorado.edu/ru/simulations/filter?subjects=chemistry"},
            {"title": "«Химия вокруг нас»", "kind": "курс", "url": "https://www.lektorium.tv/chemistry"},
            {"title": "QazVolunteer.kz", "kind": "платформа", "url": "https://qazvolunteer.kz"},
            {"title": "Красный Полумесяц Казахстана — волонтёрство", "kind": "организация", "url": "https://redcrescent.kz/ru/volonterstvo"},
        ],
        "business": [
            {"title": "Fingramota.kz", "kind": "портал", "url": "https://fingramota.kz/ru/qarjy-quests/list"},
            {"title": "Business Model Canvas", "kind": "шаблон", "url": "https://miro.com/ru/templates/business-model-canvas/"},
            {"title": "Canvanizer", "kind": "инструмент", "url": "https://canvanizer.com"},
        ],
        "humanities": [
            {"title": "Журналистика и медиаграмотность", "kind": "курс", "url": "https://stepik.org/course/81"},
            {"title": "«Секреты хороших текстов»", "kind": "курс", "url": "https://stepik.org/course/59247"},
            {"title": "Психология саморазвития", "kind": "курс", "url": "https://stepik.org/course/71738"},
            {"title": "Общая психология (курс лекций МГУ)", "kind": "видео", "url": "https://www.youtube.com/playlist?list=PLt3fgqeygGTVk5khY228EBHujarUgyLfv"},
        ],
        "law": [
            {"title": "Әділет — база НПА Казахстана", "kind": "база данных", "url": "https://adilet.zan.kz"},
        ],
        "sport": [
            {"title": "Национальный Олимпийский Комитет РК", "kind": "организация", "url": "https://olympic.kz/ru"},
        ],
        "science": [
            {"title": "Республиканский центр «Дарын»", "kind": "организация", "url": "https://daryn.kz"},
            {"title": "CyberLeninka", "kind": "библиотека", "url": "https://cyberleninka.ru"},
            {"title": "Google Академия", "kind": "поиск", "url": "https://scholar.google.com"},
        ],
    },
}

_KK_KIND = {
    "курс": "курс",
    "инструмент": "құрал",
    "задачник": "есептер жинағы",
    "видео": "видео",
    "платформа": "платформа",
    "портал": "портал",
    "шаблон": "үлгі",
    "организация": "ұйым",
    "база данных": "деректер қоры",
    "библиотека": "кітапхана",
    "поиск": "іздеу жүйесі",
}

KK = {
    "catalog": {
        cat: [
            {"title": r["title"], "kind": _KK_KIND[r["kind"]], "url": r["url"]}
            for r in entries
        ]
        for cat, entries in RU["catalog"].items()
    },
}
