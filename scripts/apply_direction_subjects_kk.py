#!/usr/bin/env python
"""
KZ-504: Apply Kazakh translations for `subjects_to_develop` in
`direction_content_review_kk.json`.

`subjects_to_develop` entries are short school-subject names — many are
spelled identically in ru and kk (математика, физика, биология, ...), so they
cannot pass the fuzzy Kazakh-character check in
`apply_catalog_descriptions_kk.py`. This script instead applies a small,
hand-reviewed ru->kk dictionary, positionally, per direction. Idempotent.

Run from the repo root (no DB needed):
    python scripts/apply_direction_subjects_kk.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
RU_FILE = HERE / "direction_content_review.json"
KK_FILE = HERE / "direction_content_review_kk.json"

# Canonical ru -> kk map for every distinct `subjects_to_develop` value.
# Keep keys byte-exact with the ru source (incl. case and parentheticals).
SUBJECTS_KK: dict[str, str] = {
    "ИЗО": "Бейнелеу өнері",
    "Иностранный язык": "Шет тілі",
    "Информатика": "Информатика",
    "Математика": "Математика",
    "Обществознание": "Қоғамтану",
    "Русский/казахский язык": "Орыс/қазақ тілі",
    "Физика": "Физика",
    "Черчение": "Сызу",
    "английский язык": "ағылшын тілі",
    "биология": "биология",
    "география": "география",
    "изобразительное искусство": "бейнелеу өнері",
    "изобразительное искусство (ИЗО)": "бейнелеу өнері",
    "иностранный язык": "шет тілі",
    "информатика": "информатика",
    "информатика (графические редакторы)": "информатика (графикалық редакторлар)",
    "информатика (для работы с цифровыми инструментами)": "информатика (цифрлық құралдармен жұмыс істеу үшін)",
    "искусство": "өнер",
    "история": "тарих",
    "литература": "әдебиет",
    "литература (для развития креативности и вдохновения)": "әдебиет (шығармашылық пен шабытты дамыту үшін)",
    "математика": "математика",
    "математика (для понимания пропорций и перспективы)": "математика (пропорциялар мен перспективаны түсіну үшін)",
    "музыка": "музыка",
    "обществознание": "қоғамтану",
    "психология": "психология",
    "русский язык": "орыс тілі",
    "русский/казахский язык": "орыс/қазақ тілі",
    "русский/казахский язык (для написания текстов и описаний)": "орыс/қазақ тілі (мәтіндер мен сипаттамалар жазу үшін)",
    "социология": "әлеуметтану",
    "технология": "технология",
    "физика": "физика",
    "физика (оптика)": "физика (оптика)",
    "физическая культура": "дене шынықтыру",
    "физкультура": "дене шынықтыру",
    "химия": "химия",
    "черчение": "сызу",
    "экология": "экология",
    "экономика": "экономика",
}


def main() -> None:
    ru = json.loads(RU_FILE.read_text(encoding="utf-8"))
    kk = json.loads(KK_FILE.read_text(encoding="utf-8"))
    ru_by_slug = {d["slug"]: d for d in ru}

    missing: set[str] = set()
    changed = 0
    for entry in kk:
        src = ru_by_slug.get(entry["slug"])
        if not src:
            continue
        new_list = []
        for item in src.get("subjects_to_develop", []) or []:
            tr = SUBJECTS_KK.get(item)
            if tr is None:
                missing.add(item)
                tr = item
            new_list.append(tr)
        if entry.get("subjects_to_develop") != new_list:
            entry["subjects_to_develop"] = new_list
            changed += 1

    if missing:
        raise SystemExit(
            "Unmapped subjects_to_develop values (add to SUBJECTS_KK): "
            + ", ".join(sorted(missing))
        )

    KK_FILE.write_text(
        json.dumps(kk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Applied kk subjects_to_develop to {changed} directions.")


if __name__ == "__main__":
    main()
