"""University-requirement labels (KZ-307). Was literals in
`app/services/university_requirements.py`. `kk` LLM-primary, native review pending.

`document_labels` — keyed by the raw requirement flag.
`admission_score_brief` is a template: `{specialty}` / `{quota}` / `{year}` /
`{score_range}` are data, filled at the call site.
"""

RU = {
    "document_labels": {
        "needs_essay": "Мотивационное эссе",
        "needs_recommendations": "Рекомендательные письма",
        "needs_interview": "Собеседование",
    },
    "admission_score_brief": "{specialty} ({quota}, {year}): проходной балл {score_range}",
}

KK = {
    "document_labels": {
        "needs_essay": "Мотивациялық эссе",
        "needs_recommendations": "Ұсыныс хаттары",
        "needs_interview": "Әңгімелесу",
    },
    "admission_score_brief": "{specialty} ({quota}, {year}): өту балы {score_range}",
}
