"""Motivation value labels + driver phrases (KZ-307; started in KZ-305). Was
inline dicts in `app/services/motivation_content.py`.

Top-level keys: `labels` (admin/debug value name per category — raw scores are
never shown to the student), `drivers` (student-facing "что тебя драйвит"
phrases, feed the report narrative via `highlight_phrases`).
"""

RU = {
    "labels": {
        "interest": "Интерес к делу",
        "challenge": "Вызов и рост",
        "helping": "Польза другим",
        "freedom": "Свобода решений",
        "money": "Материальный результат",
        "recognition": "Признание",
        "stability": "Стабильность",
        "creation": "Создавать своё",
        "teamwork": "Команда",
    },
    "drivers": {
        "interest": "Заниматься тем, что по-настоящему интересно",
        "challenge": "Решать сложные задачи и расти",
        "helping": "Приносить пользу другим",
        "freedom": "Самому принимать решения",
        "money": "Получать хороший материальный результат",
        "recognition": "Быть признанным экспертом",
        "stability": "Иметь стабильность и предсказуемость",
        "creation": "Создавать что-то своё",
        "teamwork": "Работать в сильной команде",
    },
}

KK = {
    "labels": {
        "interest": "Іске деген қызығушылық",
        "challenge": "Сын-қатер мен өсу",
        "helping": "Басқаларға пайда",
        "freedom": "Шешім еркіндігі",
        "money": "Материалдық нәтиже",
        "recognition": "Мойындау",
        "stability": "Тұрақтылық",
        "creation": "Өз ісіңді жасау",
        "teamwork": "Команда",
    },
    "drivers": {
        "interest": "Шынымен қызық іспен айналысу",
        "challenge": "Күрделі міндеттерді шешіп, өсу",
        "helping": "Басқаларға пайда келтіру",
        "freedom": "Шешімді өзің қабылдау",
        "money": "Жақсы материалдық нәтиже алу",
        "recognition": "Ісінің шебері ретінде танылу",
        "stability": "Тұрақтылық пен болжамдылыққа ие болу",
        "creation": "Өзіндік бір нәрсе жасау",
        "teamwork": "Мықты командада жұмыс істеу",
    },
}
