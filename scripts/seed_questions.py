"""
Seed script: populate the questions table.
Run inside Docker: docker-compose exec api python scripts/seed_questions.py
Idempotent: skips questions that already exist (matched by block + age_group + text).
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.question import Question, QuestionBlock
from app.models.profile import AgeGroup

# ---------------------------------------------------------------------------
# Question data
# Each entry: block, age_group, order, text, options
# options: list of {text, weights} — weights keys are career-category strings
# ---------------------------------------------------------------------------

QUESTIONS = [
    # =========================================================
    # BLOCK: interests
    # =========================================================

    # --- junior ---
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.junior, "order": 1,
        "text": "Что тебе больше всего нравится на уроках?",
        "options": [
            {"text": "Считать и решать задачки", "weights": {"science": 2, "technology": 1}},
            {"text": "Рисовать и мастерить", "weights": {"art": 2, "creative": 2}},
            {"text": "Бегать и играть в подвижные игры", "weights": {"sports": 2}},
            {"text": "Слушать истории и читать", "weights": {"humanitarian": 2}},
            {"text": "Изучать животных и растения", "weights": {"nature": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.junior, "order": 2,
        "text": "Чем ты занимаешься после школы?",
        "options": [
            {"text": "Играю в компьютер или собираю конструктор", "weights": {"technology": 2}},
            {"text": "Рисую, леплю или делаю поделки", "weights": {"art": 2, "creative": 2}},
            {"text": "Гуляю и играю с друзьями на улице", "weights": {"sports": 1, "social": 1}},
            {"text": "Читаю книги или смотрю мультфильмы", "weights": {"humanitarian": 2}},
            {"text": "Наблюдаю за животными или ухаживаю за растениями", "weights": {"nature": 2}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.junior, "order": 3,
        "text": "В какой кружок ты бы хотел записаться?",
        "options": [
            {"text": "Робототехника или программирование", "weights": {"technology": 2, "science": 1}},
            {"text": "Рисование или рукоделие", "weights": {"art": 2, "creative": 2}},
            {"text": "Спорт: футбол, плавание или гимнастика", "weights": {"sports": 2}},
            {"text": "Театр или хор", "weights": {"art": 1, "creative": 1, "social": 2}},
            {"text": "Юный натуралист или кружок по уходу за животными", "weights": {"nature": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.junior, "order": 4,
        "text": "Что тебе кажется самым интересным?",
        "options": [
            {"text": "Как работают компьютеры и роботы", "weights": {"technology": 2, "science": 1}},
            {"text": "Как рисуют мультфильмы и придумывают игры", "weights": {"art": 2, "creative": 2, "technology": 1}},
            {"text": "Рекорды и соревнования спортсменов", "weights": {"sports": 2}},
            {"text": "Истории о других странах и народах", "weights": {"humanitarian": 2}},
            {"text": "Животные и их жизнь в природе", "weights": {"nature": 2}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.junior, "order": 5,
        "text": "Что ты придумываешь сам?",
        "options": [
            {"text": "Игры на компьютере или поделки из конструктора", "weights": {"technology": 1, "creative": 2}},
            {"text": "Рисунки и поделки", "weights": {"art": 2, "creative": 2}},
            {"text": "Новые правила для игр во дворе", "weights": {"sports": 1, "social": 1}},
            {"text": "Истории и сказки", "weights": {"humanitarian": 2, "creative": 2}},
            {"text": "Опыты с природными материалами", "weights": {"nature": 2, "science": 2}},
        ],
    },

    # --- middle ---
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.middle, "order": 1,
        "text": "Какой урок нравится тебе больше всего?",
        "options": [
            {"text": "Математика, физика или информатика", "weights": {"science": 2, "technology": 1}},
            {"text": "Рисование, черчение или музыка", "weights": {"art": 2, "creative": 2}},
            {"text": "Физкультура", "weights": {"sports": 2}},
            {"text": "Литература, история или обществознание", "weights": {"humanitarian": 2, "social": 1}},
            {"text": "Биология или география", "weights": {"nature": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.middle, "order": 2,
        "text": "Чем ты занимаешься в свободное время?",
        "options": [
            {"text": "Программирую или изучаю технологии", "weights": {"technology": 2}},
            {"text": "Рисую, снимаю видео или занимаюсь музыкой", "weights": {"art": 2, "creative": 2}},
            {"text": "Тренируюсь или хожу на соревнования", "weights": {"sports": 2}},
            {"text": "Читаю или смотрю документальные фильмы", "weights": {"humanitarian": 2}},
            {"text": "Изучаю иностранные языки или культуры", "weights": {"humanitarian": 1, "social": 2}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.middle, "order": 3,
        "text": "Какой проект ты выбрал бы для школьного конкурса?",
        "options": [
            {"text": "Создать приложение или сайт", "weights": {"technology": 2, "creative": 1}},
            {"text": "Нарисовать серию иллюстраций или снять фильм", "weights": {"art": 2, "creative": 2}},
            {"text": "Организовать спортивный турнир", "weights": {"sports": 1, "social": 2}},
            {"text": "Исследовать историческое событие", "weights": {"humanitarian": 2, "science": 1}},
            {"text": "Изучить экологическую проблему", "weights": {"nature": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.middle, "order": 4,
        "text": "Что тебя больше всего вдохновляет?",
        "options": [
            {"text": "Изобретения и технологии будущего", "weights": {"technology": 2, "science": 1}},
            {"text": "Красота произведений искусства и дизайна", "weights": {"art": 2, "creative": 1}},
            {"text": "Достижения профессиональных спортсменов", "weights": {"sports": 2}},
            {"text": "Люди, которые меняют мир к лучшему", "weights": {"helping": 2, "humanitarian": 1}},
            {"text": "Открытия учёных и тайны природы", "weights": {"science": 2, "nature": 1}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.middle, "order": 5,
        "text": "Какой предмет ты хотел бы изучать глубже?",
        "options": [
            {"text": "Физику, химию или информатику", "weights": {"science": 2, "technology": 1}},
            {"text": "Историю, обществознание или психологию", "weights": {"humanitarian": 2, "social": 1}},
            {"text": "Иностранные языки", "weights": {"humanitarian": 1, "social": 2}},
            {"text": "Рисование, дизайн или музыку", "weights": {"art": 2, "creative": 2}},
            {"text": "Биологию или экологию", "weights": {"nature": 2, "science": 1}},
        ],
    },

    # --- senior ---
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.senior, "order": 1,
        "text": "Какая область знаний привлекает тебя больше всего?",
        "options": [
            {"text": "Технологии и программирование", "weights": {"technology": 2}},
            {"text": "Дизайн, искусство, музыка, кино", "weights": {"art": 2, "creative": 2}},
            {"text": "Медицина и биологические науки", "weights": {"science": 1, "helping": 2}},
            {"text": "Право, экономика и бизнес", "weights": {"humanitarian": 1, "business": 2}},
            {"text": "Философия, история, психология", "weights": {"humanitarian": 2, "social": 1}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.senior, "order": 2,
        "text": "Чем ты занимаешься с наибольшим удовольствием?",
        "options": [
            {"text": "Программирую или решаю технические задачи", "weights": {"technology": 2}},
            {"text": "Создаю: рисую, пишу, снимаю, занимаюсь музыкой", "weights": {"art": 2, "creative": 2}},
            {"text": "Занимаюсь спортом или фитнесом", "weights": {"sports": 2}},
            {"text": "Читаю или смотрю контент на умные темы", "weights": {"humanitarian": 2, "science": 1}},
            {"text": "Общаюсь и организую мероприятия", "weights": {"social": 2, "business": 1}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.senior, "order": 3,
        "text": "Если бы мог посещать любые лекции, что бы выбрал?",
        "options": [
            {"text": "Программирование и искусственный интеллект", "weights": {"technology": 2, "science": 1}},
            {"text": "Мастер-классы по дизайну и творчеству", "weights": {"art": 2, "creative": 2}},
            {"text": "Психологию и помощь людям", "weights": {"helping": 2, "social": 2}},
            {"text": "Историю, философию и культуру", "weights": {"humanitarian": 2}},
            {"text": "Предпринимательство и менеджмент", "weights": {"business": 2, "social": 1}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.senior, "order": 4,
        "text": "Какой тип задач тебе нравится?",
        "options": [
            {"text": "Технические задачи с точным ответом", "weights": {"technology": 2, "science": 2}},
            {"text": "Творческие задачи с открытым результатом", "weights": {"creative": 2, "art": 1}},
            {"text": "Задачи, требующие работы с людьми", "weights": {"helping": 2, "social": 2}},
            {"text": "Аналитические задачи: исследование, анализ данных", "weights": {"science": 2, "humanitarian": 1}},
            {"text": "Задачи по планированию и управлению", "weights": {"business": 2, "social": 1}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.senior, "order": 5,
        "text": "Чем бы ты занялся без материальных ограничений?",
        "options": [
            {"text": "Создавал бы технологии и программы", "weights": {"technology": 2, "creative": 1}},
            {"text": "Занимался бы творчеством: искусством, музыкой, кино", "weights": {"art": 2, "creative": 2}},
            {"text": "Помогал бы людям — медицина, психология, образование", "weights": {"helping": 2, "social": 1}},
            {"text": "Исследовал бы мир и культуры", "weights": {"humanitarian": 2, "nature": 1}},
            {"text": "Занимался бы наукой и делал открытия", "weights": {"science": 2}},
        ],
    },
    {
        "block": QuestionBlock.interests, "age_group": AgeGroup.senior, "order": 6,
        "text": "Что ты чаще всего изучаешь по своей инициативе?",
        "options": [
            {"text": "Туториалы по программированию и новым технологиям", "weights": {"technology": 2}},
            {"text": "Работы дизайнеров, художников, музыкантов", "weights": {"art": 2, "creative": 2}},
            {"text": "Психологию, социологию, поведение людей", "weights": {"social": 2, "humanitarian": 1}},
            {"text": "Науку: физику, биологию, астрономию", "weights": {"science": 2, "nature": 1}},
            {"text": "Бизнес-истории и истории успеха компаний", "weights": {"business": 2}},
        ],
    },

    # =========================================================
    # BLOCK: thinking
    # =========================================================

    # --- junior ---
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.junior, "order": 1,
        "text": "Когда нужно решить сложную задачу, что ты делаешь сначала?",
        "options": [
            {"text": "Думаю по шагам: сначала одно, потом другое", "weights": {"science": 2, "technology": 1}},
            {"text": "Придумываю что-то новое и необычное", "weights": {"creative": 2, "art": 1}},
            {"text": "Просто начинаю делать и разбираюсь по ходу", "weights": {"sports": 1, "technology": 1}},
            {"text": "Спрашиваю у друзей или взрослых", "weights": {"social": 1, "helping": 1}},
            {"text": "Слушаю своё чутьё", "weights": {"art": 1, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.junior, "order": 2,
        "text": "Что тебе легче?",
        "options": [
            {"text": "Посчитать или решить логическую задачку", "weights": {"science": 2, "technology": 1}},
            {"text": "Придумать и нарисовать что-то своё", "weights": {"art": 2, "creative": 2}},
            {"text": "Сделать что-то руками", "weights": {"technology": 1, "sports": 1, "creative": 1}},
            {"text": "Поговорить и помочь другу", "weights": {"social": 2, "helping": 2}},
            {"text": "Запомнить много интересных фактов", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.junior, "order": 3,
        "text": "Когда нужно объяснить что-то другу, ты...",
        "options": [
            {"text": "Рисуешь схему или считаешь на пальцах", "weights": {"science": 1, "technology": 1}},
            {"text": "Рассказываешь историю или придумываешь пример", "weights": {"creative": 2, "humanitarian": 2}},
            {"text": "Показываешь на деле: 'смотри, делай так'", "weights": {"sports": 1, "technology": 1}},
            {"text": "Говоришь терпеливо, пока не поймёт", "weights": {"helping": 2, "social": 2}},
            {"text": "Даёшь книгу или ссылку", "weights": {"science": 1, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.junior, "order": 4,
        "text": "Что тебе нравится больше: придумывать или выполнять?",
        "options": [
            {"text": "Оба одинаково: и думать, и делать", "weights": {"science": 1, "technology": 1, "creative": 1}},
            {"text": "Придумывать новые идеи", "weights": {"creative": 2, "art": 2}},
            {"text": "Выполнять — мне нравится видеть результат", "weights": {"technology": 2, "sports": 1}},
            {"text": "Помогать другим выполнять их идеи", "weights": {"helping": 2, "social": 2}},
            {"text": "Изучать и разбираться: почему и как это работает", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.junior, "order": 5,
        "text": "Ты склонен...",
        "options": [
            {"text": "Сначала всё продумать, потом действовать", "weights": {"science": 2, "business": 1}},
            {"text": "Действовать по наитию — так интереснее", "weights": {"creative": 2, "sports": 1}},
            {"text": "Делать несколько вещей сразу", "weights": {"social": 1, "business": 1}},
            {"text": "Слушать других и потом принимать решение", "weights": {"helping": 1, "social": 2}},
            {"text": "Пробовать разные подходы, пока не получится", "weights": {"technology": 1, "science": 1, "creative": 1}},
        ],
    },

    # --- middle ---
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.middle, "order": 1,
        "text": "Как тебе легче понять новую тему?",
        "options": [
            {"text": "Разобрать логику: почему и как это работает", "weights": {"science": 2, "technology": 1}},
            {"text": "Найти связь с чем-то творческим или красивым", "weights": {"art": 1, "creative": 2}},
            {"text": "Попробовать самому на практике", "weights": {"technology": 1, "sports": 1}},
            {"text": "Обсудить с кем-то: с учителем или другом", "weights": {"social": 2, "helping": 1}},
            {"text": "Прочитать много источников и составить свою картину", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.middle, "order": 2,
        "text": "Когда ты работаешь над проектом, тебе важнее...",
        "options": [
            {"text": "Чтобы всё было логично и структурировано", "weights": {"science": 2, "business": 1}},
            {"text": "Чтобы результат был красивым и необычным", "weights": {"art": 2, "creative": 2}},
            {"text": "Чтобы это было полезно для людей", "weights": {"helping": 2, "social": 1}},
            {"text": "Чтобы это было сделано правильно и точно", "weights": {"technology": 2, "science": 1}},
            {"text": "Чтобы процесс был интересным", "weights": {"creative": 1, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.middle, "order": 3,
        "text": "Когда сталкиваешься с трудной проблемой, ты...",
        "options": [
            {"text": "Ищешь закономерность и строишь алгоритм решения", "weights": {"science": 2, "technology": 2}},
            {"text": "Ищешь нестандартный, оригинальный подход", "weights": {"creative": 2, "art": 1}},
            {"text": "Спрашиваешь, как другие решали похожее", "weights": {"social": 1, "helping": 1}},
            {"text": "Пробуешь несколько вариантов и смотришь, что сработает", "weights": {"technology": 1, "sports": 1}},
            {"text": "Ищешь контекст: почему эта проблема вообще возникла", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.middle, "order": 4,
        "text": "Как ты принимаешь важные решения?",
        "options": [
            {"text": "Анализирую все варианты и выбираю лучший", "weights": {"science": 2, "business": 1}},
            {"text": "Слушаю своё внутреннее ощущение", "weights": {"art": 1, "humanitarian": 1}},
            {"text": "Спрашиваю мнение близких", "weights": {"social": 2, "helping": 1}},
            {"text": "Смотрю, что практичнее и эффективнее", "weights": {"technology": 2, "business": 1}},
            {"text": "Выбираю то, что соответствует моим ценностям", "weights": {"humanitarian": 2, "helping": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.middle, "order": 5,
        "text": "Что из этого ты делаешь лучше всего?",
        "options": [
            {"text": "Замечаю ошибки и нахожу точные решения", "weights": {"science": 2, "technology": 2}},
            {"text": "Придумываю необычные идеи", "weights": {"creative": 2, "art": 2}},
            {"text": "Понимаю людей и нахожу с ними общий язык", "weights": {"social": 2, "helping": 2}},
            {"text": "Быстро выполняю задачи, не теряя времени", "weights": {"sports": 1, "business": 1}},
            {"text": "Глубоко изучаю темы, которые интересны", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },

    # --- senior ---
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.senior, "order": 1,
        "text": "Как тебе проще всего обрабатывать новую информацию?",
        "options": [
            {"text": "Системно: строю структуру, выделяю главное", "weights": {"science": 2, "technology": 1}},
            {"text": "Ассоциативно: связываю с образами и идеями", "weights": {"creative": 2, "art": 1}},
            {"text": "Практически: сразу пробую применить", "weights": {"technology": 2, "sports": 1}},
            {"text": "Коллаборативно: обсуждаю с другими", "weights": {"social": 2, "helping": 1}},
            {"text": "Нарративно: рассказываю историю, чтобы понять", "weights": {"humanitarian": 2}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.senior, "order": 2,
        "text": "В какой роли ты наиболее эффективен?",
        "options": [
            {"text": "Аналитик: нахожу закономерности в данных", "weights": {"science": 2, "technology": 1}},
            {"text": "Генератор идей: предлагаю нестандартные решения", "weights": {"creative": 2, "art": 1}},
            {"text": "Исполнитель: довожу задачи до конца", "weights": {"technology": 2, "business": 1}},
            {"text": "Коммуникатор: связываю людей и идеи", "weights": {"social": 2, "helping": 1}},
            {"text": "Стратег: вижу картину в целом, планирую", "weights": {"business": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.senior, "order": 3,
        "text": "Когда проект идёт не по плану, ты...",
        "options": [
            {"text": "Перестраиваю план и ищу новое оптимальное решение", "weights": {"science": 2, "technology": 1}},
            {"text": "Нахожу это захватывающим — импровизирую", "weights": {"creative": 2, "art": 1}},
            {"text": "Сосредотачиваюсь на главном и действую", "weights": {"business": 2, "sports": 1}},
            {"text": "Обсуждаю с командой и ищем выход вместе", "weights": {"social": 2, "helping": 1}},
            {"text": "Ищу причину провала, чтобы больше не повторить", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.senior, "order": 4,
        "text": "Как ты обычно приходишь к лучшим идеям?",
        "options": [
            {"text": "В тихом месте, когда могу думать без помех", "weights": {"science": 2, "creative": 1}},
            {"text": "В процессе создания — идеи приходят на ходу", "weights": {"creative": 2, "art": 2}},
            {"text": "Во время движения: бег, прогулка, тренировка", "weights": {"sports": 1, "creative": 1}},
            {"text": "В разговоре с интересными людьми", "weights": {"social": 2, "humanitarian": 1}},
            {"text": "Когда читаю и изучаю что-то новое", "weights": {"science": 1, "humanitarian": 2}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.senior, "order": 5,
        "text": "Что лучше всего описывает твой стиль работы?",
        "options": [
            {"text": "Методичный: шаг за шагом, без спешки", "weights": {"science": 2, "technology": 1}},
            {"text": "Интуитивный: действую по ощущению, но попадаю в точку", "weights": {"creative": 2, "art": 1}},
            {"text": "Энергичный: делаю много всего параллельно", "weights": {"sports": 1, "social": 1, "business": 1}},
            {"text": "Людоориентированный: важно, как это влияет на других", "weights": {"helping": 2, "social": 2}},
            {"text": "Перфекционист: доделываю до идеального состояния", "weights": {"science": 2, "art": 1}},
        ],
    },
    {
        "block": QuestionBlock.thinking, "age_group": AgeGroup.senior, "order": 6,
        "text": "Чему ты больше доверяешь при решении сложных задач?",
        "options": [
            {"text": "Данным и логике", "weights": {"science": 2, "technology": 2}},
            {"text": "Интуиции и творческому чутью", "weights": {"creative": 2, "art": 2}},
            {"text": "Опыту и практике", "weights": {"technology": 2, "business": 1}},
            {"text": "Мнению экспертов и знающих людей", "weights": {"humanitarian": 1, "helping": 1}},
            {"text": "Своим ценностям и внутреннему компасу", "weights": {"humanitarian": 2, "social": 1}},
        ],
    },

    # =========================================================
    # BLOCK: personality
    # =========================================================

    # --- junior ---
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.junior, "order": 1,
        "text": "Ты больше любишь...",
        "options": [
            {"text": "Заниматься чем-то одному: строить, рисовать, читать", "weights": {"technology": 1, "art": 1, "science": 1}},
            {"text": "Играть и общаться с друзьями", "weights": {"social": 2}},
            {"text": "Быть лидером и предлагать, во что играть", "weights": {"social": 2, "business": 1}},
            {"text": "Помогать другим — делиться, объяснять", "weights": {"helping": 2, "social": 1}},
            {"text": "Придумывать что-то и показывать другим", "weights": {"creative": 2, "art": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.junior, "order": 2,
        "text": "Если в классе нужно сделать общий проект, ты...",
        "options": [
            {"text": "Предлагаешь идею и берёшь ответственность", "weights": {"social": 2, "business": 1}},
            {"text": "Делаешь свою часть аккуратно и хорошо", "weights": {"science": 1, "technology": 1}},
            {"text": "Помогаешь тем, у кого не получается", "weights": {"helping": 2, "social": 1}},
            {"text": "Придумываешь, как сделать красивее или интереснее", "weights": {"creative": 2, "art": 1}},
            {"text": "Предпочитаешь делать своё отдельно", "weights": {"technology": 1, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.junior, "order": 3,
        "text": "Когда у тебя хорошее настроение, ты...",
        "options": [
            {"text": "Хочешь побыть один и заняться любимым делом", "weights": {"technology": 1, "science": 1, "art": 1}},
            {"text": "Хочешь позвать друзей и поиграть вместе", "weights": {"social": 2}},
            {"text": "Предлагаешь всем что-то сделать вместе", "weights": {"social": 2, "business": 1}},
            {"text": "Хочешь помочь кому-нибудь или порадовать близких", "weights": {"helping": 2}},
            {"text": "Хочешь что-то создать: нарисовать, придумать", "weights": {"creative": 2, "art": 2}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.junior, "order": 4,
        "text": "Что тебе важнее всего в друзьях?",
        "options": [
            {"text": "Чтобы они были умными и интересными", "weights": {"science": 1, "humanitarian": 1}},
            {"text": "Чтобы было весело вместе", "weights": {"social": 2, "sports": 1}},
            {"text": "Чтобы они слушали и поддерживали", "weights": {"helping": 1, "social": 1}},
            {"text": "Чтобы они были честными и надёжными", "weights": {"humanitarian": 1, "helping": 1}},
            {"text": "Чтобы разделяли мои интересы", "weights": {"technology": 1, "creative": 1, "art": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.junior, "order": 5,
        "text": "Каким ты хочешь стать, когда вырастешь?",
        "options": [
            {"text": "Учёным или изобретателем", "weights": {"science": 2, "technology": 2}},
            {"text": "Художником, актёром или музыкантом", "weights": {"art": 2, "creative": 2}},
            {"text": "Известным спортсменом", "weights": {"sports": 2}},
            {"text": "Доктором или учителем", "weights": {"helping": 2, "social": 1}},
            {"text": "Предпринимателем или директором", "weights": {"business": 2, "social": 1}},
        ],
    },

    # --- middle ---
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.middle, "order": 1,
        "text": "Как бы ты себя описал в одном слове?",
        "options": [
            {"text": "Аналитик", "weights": {"science": 2, "technology": 1}},
            {"text": "Творец", "weights": {"creative": 2, "art": 2}},
            {"text": "Организатор", "weights": {"business": 2, "social": 1}},
            {"text": "Помощник", "weights": {"helping": 2, "social": 2}},
            {"text": "Исследователь", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.middle, "order": 2,
        "text": "В классе ты чаще всего...",
        "options": [
            {"text": "Предпочитаешь слушать и обдумывать", "weights": {"science": 1, "humanitarian": 1}},
            {"text": "Участвуешь в обсуждениях и высказываешься", "weights": {"social": 2, "humanitarian": 1}},
            {"text": "Берёшь инициативу при работе в группе", "weights": {"social": 2, "business": 2}},
            {"text": "Помогаешь одноклассникам, которым трудно", "weights": {"helping": 2, "social": 1}},
            {"text": "Предлагаешь нестандартные решения", "weights": {"creative": 2, "technology": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.middle, "order": 3,
        "text": "Что тебя лучше всего характеризует?",
        "options": [
            {"text": "Внимательный к деталям и точности", "weights": {"science": 2, "technology": 2}},
            {"text": "Оригинальный и непохожий на других", "weights": {"creative": 2, "art": 2}},
            {"text": "Общительный и умеющий договариваться", "weights": {"social": 2, "business": 1}},
            {"text": "Чуткий и внимательный к людям", "weights": {"helping": 2, "social": 1}},
            {"text": "Целеустремлённый и настойчивый", "weights": {"business": 1, "sports": 1, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.middle, "order": 4,
        "text": "Когда нужно принять важное решение, ты...",
        "options": [
            {"text": "Взвешиваешь все за и против", "weights": {"science": 2, "business": 1}},
            {"text": "Следуешь своей интуиции", "weights": {"art": 1, "creative": 1}},
            {"text": "Советуешься с теми, кому доверяешь", "weights": {"social": 2, "helping": 1}},
            {"text": "Делаешь то, что правильно с точки зрения ценностей", "weights": {"humanitarian": 2, "helping": 1}},
            {"text": "Выбираешь то, что принесёт лучший результат", "weights": {"business": 2, "technology": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.middle, "order": 5,
        "text": "Как ты обычно проводишь свободное время?",
        "options": [
            {"text": "Углубляюсь в любимое занятие в одиночестве", "weights": {"technology": 1, "science": 1, "art": 1}},
            {"text": "Тусуюсь с друзьями", "weights": {"social": 2}},
            {"text": "Организую активность для всех", "weights": {"social": 2, "business": 1}},
            {"text": "Помогаю кому-то или участвую в волонтёрстве", "weights": {"helping": 2, "social": 1}},
            {"text": "Занимаюсь чем-то творческим", "weights": {"creative": 2, "art": 2}},
        ],
    },

    # --- senior ---
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.senior, "order": 1,
        "text": "Как бы тебя описали люди, которые хорошо тебя знают?",
        "options": [
            {"text": "Логичный, системный, умный", "weights": {"science": 2, "technology": 1}},
            {"text": "Творческий, оригинальный, необычный", "weights": {"creative": 2, "art": 2}},
            {"text": "Лидер, организатор, инициативный", "weights": {"business": 2, "social": 2}},
            {"text": "Добрый, отзывчивый, умеющий слушать", "weights": {"helping": 2, "social": 1}},
            {"text": "Любознательный, глубокий, думающий", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.senior, "order": 2,
        "text": "В командной работе твоя естественная роль...",
        "options": [
            {"text": "Аналитик: ищу факты и строю логику", "weights": {"science": 2, "technology": 1}},
            {"text": "Генератор идей: предлагаю нестандартные решения", "weights": {"creative": 2, "art": 1}},
            {"text": "Лидер: беру на себя ответственность и организую", "weights": {"business": 2, "social": 2}},
            {"text": "Поддерживающий: слежу, чтобы у всех всё было хорошо", "weights": {"helping": 2, "social": 2}},
            {"text": "Эксперт: глубоко изучаю свою часть задачи", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.senior, "order": 3,
        "text": "Что тебя больше всего мотивирует?",
        "options": [
            {"text": "Сложные интеллектуальные вызовы", "weights": {"science": 2, "technology": 1}},
            {"text": "Возможность создавать что-то новое", "weights": {"creative": 2, "art": 2}},
            {"text": "Видеть, как моя работа влияет на других людей", "weights": {"helping": 2, "social": 2}},
            {"text": "Признание и уважение окружающих", "weights": {"social": 2, "business": 1}},
            {"text": "Достижение поставленных целей", "weights": {"business": 2, "sports": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.senior, "order": 4,
        "text": "Что происходит, когда ты устал или в стрессе?",
        "options": [
            {"text": "Нужно побыть в тишине и наедине с собой", "weights": {"technology": 1, "science": 1}},
            {"text": "Занимаюсь творчеством — это перезаряжает", "weights": {"art": 2, "creative": 2}},
            {"text": "Иду к людям, общение восстанавливает силы", "weights": {"social": 2, "helping": 1}},
            {"text": "Занимаюсь спортом или физической активностью", "weights": {"sports": 2}},
            {"text": "Читаю, смотрю фильмы, погружаюсь в другой мир", "weights": {"humanitarian": 2, "art": 1}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.senior, "order": 5,
        "text": "В чём ты ощущаешь себя сильнее всего?",
        "options": [
            {"text": "В логике, анализе данных, решении сложных задач", "weights": {"science": 2, "technology": 2}},
            {"text": "В генерации идей и нестандартном мышлении", "weights": {"creative": 2, "art": 2}},
            {"text": "В общении, переговорах, управлении людьми", "weights": {"social": 2, "business": 2}},
            {"text": "В понимании людей, эмпатии, поддержке", "weights": {"helping": 2, "social": 2}},
            {"text": "В глубоком исследовании тем, которые меня захватывают", "weights": {"science": 2, "humanitarian": 2}},
        ],
    },
    {
        "block": QuestionBlock.personality, "age_group": AgeGroup.senior, "order": 6,
        "text": "Как ты относишься к переменам и неопределённости?",
        "options": [
            {"text": "Люблю стабильность и чёткий план", "weights": {"science": 1, "business": 1}},
            {"text": "Обожаю перемены — каждый раз что-то новое", "weights": {"creative": 2, "sports": 1}},
            {"text": "Отношусь нейтрально — главное, чтобы были люди рядом", "weights": {"social": 2, "helping": 1}},
            {"text": "Принимаю как вызов и ищу возможности", "weights": {"business": 2, "technology": 1}},
            {"text": "Сначала тревожусь, потом адаптируюсь", "weights": {"humanitarian": 1, "science": 1}},
        ],
    },

    # =========================================================
    # BLOCK: motivation
    # =========================================================

    # --- junior ---
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.junior, "order": 1,
        "text": "Что делает тебя самым гордым?",
        "options": [
            {"text": "Когда решаю сложную задачу или задание", "weights": {"science": 2, "technology": 1}},
            {"text": "Когда создаю что-то красивое своими руками", "weights": {"art": 2, "creative": 2}},
            {"text": "Когда побеждаю в игре или соревновании", "weights": {"sports": 2, "business": 1}},
            {"text": "Когда помогаю другу или однокласснику", "weights": {"helping": 2, "social": 1}},
            {"text": "Когда узнаю что-то новое и интересное", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.junior, "order": 2,
        "text": "Когда ты стараешься больше всего?",
        "options": [
            {"text": "Когда задание интересное и непростое", "weights": {"science": 2, "technology": 1}},
            {"text": "Когда могу придумать что-то своё", "weights": {"creative": 2, "art": 1}},
            {"text": "Когда нужно победить или быть первым", "weights": {"sports": 2, "business": 1}},
            {"text": "Когда это нужно другим людям", "weights": {"helping": 2, "social": 1}},
            {"text": "Когда хочу стать лучше в чём-то", "weights": {"science": 1, "sports": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.junior, "order": 3,
        "text": "Что ты больше всего хочешь получить от учёбы?",
        "options": [
            {"text": "Знания, которые помогут решать задачи", "weights": {"science": 2, "technology": 1}},
            {"text": "Умение создавать красивые вещи", "weights": {"art": 2, "creative": 2}},
            {"text": "Быть лучшим в классе или школе", "weights": {"business": 1, "sports": 1}},
            {"text": "Научиться помогать другим людям", "weights": {"helping": 2, "social": 2}},
            {"text": "Узнавать интересные факты о мире", "weights": {"science": 1, "humanitarian": 2}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.junior, "order": 4,
        "text": "Что тебя расстраивает больше всего?",
        "options": [
            {"text": "Когда задание неинтересное или скучное", "weights": {"science": 1, "creative": 1}},
            {"text": "Когда нет возможности сделать что-то по-своему", "weights": {"creative": 2, "art": 1}},
            {"text": "Когда проигрываешь или совершаешь ошибку", "weights": {"sports": 1, "business": 1}},
            {"text": "Когда не можешь помочь тому, кому нужно", "weights": {"helping": 2, "social": 1}},
            {"text": "Когда не получается узнать что-то новое", "weights": {"science": 1, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.junior, "order": 5,
        "text": "Что ты хочешь, чтобы думали о тебе другие?",
        "options": [
            {"text": "Что я умный и способный", "weights": {"science": 2}},
            {"text": "Что я творческий и талантливый", "weights": {"art": 2, "creative": 2}},
            {"text": "Что я сильный и ловкий", "weights": {"sports": 2}},
            {"text": "Что я добрый и отзывчивый", "weights": {"helping": 2, "social": 2}},
            {"text": "Что я интересный и особенный", "weights": {"creative": 1, "humanitarian": 1}},
        ],
    },

    # --- middle ---
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.middle, "order": 1,
        "text": "Что лучше всего описывает твою главную цель?",
        "options": [
            {"text": "Стать экспертом в своей области", "weights": {"science": 2, "technology": 2}},
            {"text": "Создать что-то значимое: проект, произведение, продукт", "weights": {"creative": 2, "art": 1, "technology": 1}},
            {"text": "Добиться успеха и признания", "weights": {"business": 2, "social": 1}},
            {"text": "Помочь людям и сделать мир лучше", "weights": {"helping": 2, "social": 2}},
            {"text": "Постоянно развиваться и узнавать новое", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.middle, "order": 2,
        "text": "Что тебя заряжает энергией?",
        "options": [
            {"text": "Сложные задачи и интеллектуальные вызовы", "weights": {"science": 2, "technology": 1}},
            {"text": "Творческий процесс: придумывать, создавать", "weights": {"creative": 2, "art": 2}},
            {"text": "Соревнования и ощущение победы", "weights": {"sports": 2, "business": 1}},
            {"text": "Когда вижу, что помог кому-то", "weights": {"helping": 2, "social": 1}},
            {"text": "Новые знания и открытия", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.middle, "order": 3,
        "text": "Что важнее всего в будущей профессии?",
        "options": [
            {"text": "Интересные задачи и постоянное развитие", "weights": {"science": 2, "technology": 1}},
            {"text": "Возможность творить и самовыражаться", "weights": {"creative": 2, "art": 2}},
            {"text": "Высокий доход и карьерный рост", "weights": {"business": 2}},
            {"text": "Помощь людям и социальная значимость", "weights": {"helping": 2, "social": 2}},
            {"text": "Стабильность и уверенность в завтрашнем дне", "weights": {"helping": 1, "business": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.middle, "order": 4,
        "text": "Когда ты думаешь о будущем, что тебя беспокоит больше всего?",
        "options": [
            {"text": "Что не найду интересную работу", "weights": {"science": 1, "technology": 1}},
            {"text": "Что не смогу реализовать свой творческий потенциал", "weights": {"creative": 2, "art": 1}},
            {"text": "Что не добьюсь успеха и не буду обеспечен", "weights": {"business": 2}},
            {"text": "Что не смогу помочь людям, которые нуждаются", "weights": {"helping": 2, "social": 1}},
            {"text": "Что моя жизнь не будет иметь смысла", "weights": {"humanitarian": 2, "helping": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.middle, "order": 5,
        "text": "Что тебя мотивирует учиться лучше?",
        "options": [
            {"text": "Хочу понять, как устроен мир", "weights": {"science": 2, "technology": 1}},
            {"text": "Хочу развить свои творческие способности", "weights": {"creative": 2, "art": 2}},
            {"text": "Хочу добиться хороших результатов и оценок", "weights": {"business": 1, "sports": 1}},
            {"text": "Хочу быть полезным для общества", "weights": {"helping": 2, "social": 2}},
            {"text": "Мне просто нравится учиться и узнавать новое", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },

    # --- senior ---
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.senior, "order": 1,
        "text": "Что является для тебя главным источником смысла?",
        "options": [
            {"text": "Интеллектуальные достижения и профессионализм", "weights": {"science": 2, "technology": 1}},
            {"text": "Создание чего-то оригинального и красивого", "weights": {"creative": 2, "art": 2}},
            {"text": "Карьерный успех и материальное благополучие", "weights": {"business": 2}},
            {"text": "Помощь другим людям и вклад в общество", "weights": {"helping": 2, "social": 2}},
            {"text": "Саморазвитие, рост и новые открытия", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.senior, "order": 2,
        "text": "Какой тип признания тебе важнее?",
        "options": [
            {"text": "Признание экспертов и профессионалов в области", "weights": {"science": 2, "technology": 1}},
            {"text": "Признание твоего творческого таланта", "weights": {"art": 2, "creative": 2}},
            {"text": "Общественное признание и широкая известность", "weights": {"social": 2, "business": 1}},
            {"text": "Благодарность от людей, которым ты помог", "weights": {"helping": 2, "social": 1}},
            {"text": "Самопознание: признание самого себя", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.senior, "order": 3,
        "text": "Каким ты хочешь видеть себя через 10 лет?",
        "options": [
            {"text": "Ведущим специалистом в технологической сфере", "weights": {"technology": 2, "science": 1}},
            {"text": "Признанным художником, дизайнером или творческим деятелем", "weights": {"art": 2, "creative": 2}},
            {"text": "Успешным предпринимателем или топ-менеджером", "weights": {"business": 2, "social": 1}},
            {"text": "Профессионалом в сфере помощи людям", "weights": {"helping": 2, "social": 2}},
            {"text": "Исследователем или учёным, делающим открытия", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.senior, "order": 4,
        "text": "Что пугает тебя в профессиональном будущем?",
        "options": [
            {"text": "Что работа окажется монотонной и скучной", "weights": {"technology": 1, "creative": 1}},
            {"text": "Что не будет возможности самовыражаться", "weights": {"creative": 2, "art": 2}},
            {"text": "Что не будет финансовой стабильности", "weights": {"business": 2}},
            {"text": "Что я не буду нужен и полезен людям", "weights": {"helping": 2, "social": 1}},
            {"text": "Что я никогда не найду своё настоящее призвание", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.senior, "order": 5,
        "text": "Чем ты готов пожертвовать ради интересной работы?",
        "options": [
            {"text": "Высоким доходом — главное, чтобы было интересно", "weights": {"science": 2, "technology": 1, "art": 1}},
            {"text": "Стабильностью — ради творческой свободы", "weights": {"creative": 2, "art": 2}},
            {"text": "Временем — готов работать много, если дело нравится", "weights": {"business": 1, "helping": 1}},
            {"text": "Престижем — главное, приносить реальную пользу", "weights": {"helping": 2, "social": 2}},
            {"text": "Личным временем — ради профессионального роста", "weights": {"science": 2, "business": 1}},
        ],
    },
    {
        "block": QuestionBlock.motivation, "age_group": AgeGroup.senior, "order": 6,
        "text": "Что означает для тебя успех?",
        "options": [
            {"text": "Мастерство: стать лучшим в своём деле", "weights": {"science": 2, "technology": 1}},
            {"text": "Вклад: создать что-то, что останется после тебя", "weights": {"creative": 2, "art": 2}},
            {"text": "Влияние: изменить что-то в обществе к лучшему", "weights": {"social": 2, "helping": 2}},
            {"text": "Независимость: жить так, как я хочу", "weights": {"business": 2, "creative": 1}},
            {"text": "Самореализация: раскрыть весь свой потенциал", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },

    # =========================================================
    # BLOCK: academic
    # =========================================================

    # --- junior ---
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.junior, "order": 1,
        "text": "Какой урок ты больше всего любишь в школе?",
        "options": [
            {"text": "Математика: мне нравятся задачки и примеры", "weights": {"science": 2, "technology": 1}},
            {"text": "Рисование: люблю создавать красивые картинки", "weights": {"art": 2, "creative": 2}},
            {"text": "Физкультура: нравится двигаться и играть", "weights": {"sports": 2}},
            {"text": "Чтение или русский язык: нравятся слова и истории", "weights": {"humanitarian": 2}},
            {"text": "Природоведение: интересно всё о природе и животных", "weights": {"nature": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.junior, "order": 2,
        "text": "Что тебе легче всего даётся в школе?",
        "options": [
            {"text": "Считать и решать примеры", "weights": {"science": 2, "technology": 1}},
            {"text": "Рисовать и работать руками", "weights": {"art": 2, "creative": 2}},
            {"text": "Физические задания: быстро бегать, прыгать", "weights": {"sports": 2}},
            {"text": "Запоминать слова, читать и пересказывать", "weights": {"humanitarian": 2}},
            {"text": "Запоминать факты о природе и животных", "weights": {"nature": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.junior, "order": 3,
        "text": "Какое задание тебе больше всего понравилось бы?",
        "options": [
            {"text": "Решить сложный пример или головоломку", "weights": {"science": 2}},
            {"text": "Нарисовать плакат или сделать поделку", "weights": {"art": 2, "creative": 2}},
            {"text": "Провести спортивное соревнование", "weights": {"sports": 2, "social": 1}},
            {"text": "Написать сочинение или придумать рассказ", "weights": {"humanitarian": 2, "creative": 1}},
            {"text": "Провести простой опыт с растениями или водой", "weights": {"nature": 2, "science": 2}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.junior, "order": 4,
        "text": "Что тебе интереснее всего изучать?",
        "options": [
            {"text": "Цифры, формулы и закономерности", "weights": {"science": 2, "technology": 1}},
            {"text": "Как рисовать, лепить или конструировать", "weights": {"art": 2, "creative": 2}},
            {"text": "Спортивные правила и техники", "weights": {"sports": 2}},
            {"text": "Стихи, сказки и истории из жизни", "weights": {"humanitarian": 2}},
            {"text": "Откуда берётся дождь, почему растут деревья", "weights": {"nature": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.junior, "order": 5,
        "text": "Когда ты делаешь домашнее задание, что делаешь первым?",
        "options": [
            {"text": "Математику — она мне нравится", "weights": {"science": 2, "technology": 1}},
            {"text": "Рисую, если есть творческое задание", "weights": {"art": 2, "creative": 2}},
            {"text": "Не делаю сразу, сначала гуляю и двигаюсь", "weights": {"sports": 2}},
            {"text": "Чтение или письмо — они мне легко даются", "weights": {"humanitarian": 2}},
            {"text": "То задание, которое кажется самым интересным", "weights": {"science": 1, "creative": 1}},
        ],
    },

    # --- middle ---
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.middle, "order": 1,
        "text": "В каком предмете ты успеваешь лучше всего?",
        "options": [
            {"text": "Математика, физика или информатика", "weights": {"science": 2, "technology": 1}},
            {"text": "Изобразительное искусство или музыка", "weights": {"art": 2, "creative": 2}},
            {"text": "Физкультура", "weights": {"sports": 2}},
            {"text": "Русский язык, литература или история", "weights": {"humanitarian": 2}},
            {"text": "Биология, химия или география", "weights": {"nature": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.middle, "order": 2,
        "text": "Какой тип учебных заданий ты предпочитаешь?",
        "options": [
            {"text": "Задачи с чёткими условиями и правильным ответом", "weights": {"science": 2, "technology": 1}},
            {"text": "Творческие задания: эссе, рисунок, проект", "weights": {"creative": 2, "art": 1, "humanitarian": 1}},
            {"text": "Практические работы и опыты", "weights": {"science": 1, "nature": 1, "technology": 1}},
            {"text": "Групповые обсуждения и дискуссии", "weights": {"social": 2, "humanitarian": 1}},
            {"text": "Исследовательские задания: найти, изучить, сделать вывод", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.middle, "order": 3,
        "text": "Что из этого ты делаешь лучше всего?",
        "options": [
            {"text": "Решаю логические задачи и уравнения", "weights": {"science": 2, "technology": 2}},
            {"text": "Создаю творческие работы: сочинения, рисунки, поделки", "weights": {"creative": 2, "art": 2, "humanitarian": 1}},
            {"text": "Участвую в соревнованиях и показываю результат", "weights": {"sports": 2, "business": 1}},
            {"text": "Объясняю материал тем, кто не понял", "weights": {"helping": 2, "social": 1}},
            {"text": "Исследую и нахожу нестандартные решения", "weights": {"science": 2, "creative": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.middle, "order": 4,
        "text": "Если бы ты мог выбрать только одну группу предметов, что бы оставил?",
        "options": [
            {"text": "Математику и информатику", "weights": {"science": 2, "technology": 1}},
            {"text": "Уроки творчества: ИЗО, музыку, технологию", "weights": {"art": 2, "creative": 2}},
            {"text": "Физкультуру", "weights": {"sports": 2}},
            {"text": "Гуманитарные предметы: литературу, историю, языки", "weights": {"humanitarian": 2, "social": 1}},
            {"text": "Естественные науки: биологию, химию, физику", "weights": {"science": 2, "nature": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.middle, "order": 5,
        "text": "Что ты делаешь, когда не понимаешь новую тему?",
        "options": [
            {"text": "Ищу объяснение в интернете или учебнике сам", "weights": {"science": 1, "technology": 1}},
            {"text": "Нахожу связь с чем-то знакомым или творческим", "weights": {"creative": 1, "humanitarian": 1}},
            {"text": "Прошу учителя или одноклассника объяснить", "weights": {"helping": 1, "social": 2}},
            {"text": "Пробую решить на практике, методом проб и ошибок", "weights": {"technology": 1, "sports": 1}},
            {"text": "Углубляюсь, пока полностью не разберусь", "weights": {"science": 2}},
        ],
    },

    # --- senior ---
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.senior, "order": 1,
        "text": "В какой академической области ты ощущаешь себя наиболее сильным?",
        "options": [
            {"text": "Математика, физика, информатика", "weights": {"science": 2, "technology": 2}},
            {"text": "Творческие дисциплины: литература, ИЗО, музыка", "weights": {"art": 2, "creative": 2, "humanitarian": 1}},
            {"text": "Иностранные языки", "weights": {"humanitarian": 1, "social": 2}},
            {"text": "Общественные науки: история, обществознание, экономика", "weights": {"humanitarian": 2, "business": 1}},
            {"text": "Биология, химия, экология", "weights": {"nature": 2, "science": 1, "helping": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.senior, "order": 2,
        "text": "Как ты обычно готовишься к экзамену или контрольной?",
        "options": [
            {"text": "Систематически: делаю конспекты, решаю задачи", "weights": {"science": 2, "technology": 1}},
            {"text": "Нахожу интересные источники и читаю с удовольствием", "weights": {"humanitarian": 2, "creative": 1}},
            {"text": "Объясняю материал другим — так лучше запоминаю", "weights": {"helping": 2, "social": 2}},
            {"text": "Делаю майнд-карты и визуальные схемы", "weights": {"creative": 2, "art": 1}},
            {"text": "Откладываю на последний момент, но в итоге справляюсь", "weights": {"sports": 1, "business": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.senior, "order": 3,
        "text": "В каком формате тебе легче всего учиться?",
        "options": [
            {"text": "Читаю учебники, делаю задания самостоятельно", "weights": {"science": 2, "technology": 1}},
            {"text": "Смотрю видео, слушаю лекции", "weights": {"art": 1, "humanitarian": 1}},
            {"text": "Работаю в группе, обсуждаю с другими", "weights": {"social": 2, "helping": 1}},
            {"text": "Практикую: делаю проекты и реальные задачи", "weights": {"technology": 2, "creative": 1}},
            {"text": "Дискутирую: люблю отстаивать свою точку зрения", "weights": {"humanitarian": 2, "social": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.senior, "order": 4,
        "text": "Что для тебя сложнее всего в учёбе?",
        "options": [
            {"text": "Заучивать то, что кажется неважным", "weights": {"science": 1, "humanitarian": 1}},
            {"text": "Ограничения: делать строго по шаблону, без творчества", "weights": {"creative": 2, "art": 1}},
            {"text": "Работать в одиночестве без команды", "weights": {"social": 2, "helping": 1}},
            {"text": "Теоретические концепции без практического применения", "weights": {"technology": 2, "sports": 1}},
            {"text": "Оставаться мотивированным, если тема кажется скучной", "weights": {"business": 1, "sports": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.senior, "order": 5,
        "text": "Как ты относишься к ошибкам в учёбе?",
        "options": [
            {"text": "Вижу ошибку как задачу: нужно найти, где логика сломалась", "weights": {"science": 2, "technology": 1}},
            {"text": "Принимаю как часть творческого процесса", "weights": {"creative": 2, "art": 1}},
            {"text": "Расстраиваюсь, но стараюсь не зацикливаться", "weights": {"sports": 1, "helping": 1}},
            {"text": "Ищу обратную связь: прошу объяснить, где я был не прав", "weights": {"social": 1, "helping": 1}},
            {"text": "Анализирую контекст: почему это ошибка с точки зрения системы", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.academic, "age_group": AgeGroup.senior, "order": 6,
        "text": "Какой предмет ты бы изучал, даже если бы он не давал никаких преимуществ?",
        "options": [
            {"text": "Математику или программирование — мне это интересно само по себе", "weights": {"science": 2, "technology": 2}},
            {"text": "Изобразительное искусство, литературу или музыку", "weights": {"art": 2, "creative": 2}},
            {"text": "Психологию или социологию", "weights": {"social": 2, "helping": 2}},
            {"text": "Историю, философию или культурологию", "weights": {"humanitarian": 2}},
            {"text": "Биологию, химию или астрономию", "weights": {"nature": 2, "science": 2}},
        ],
    },

    # =========================================================
    # BLOCK: directions
    # =========================================================

    # --- junior ---
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.junior, "order": 1,
        "text": "Кем из этих людей ты бы хотел стать?",
        "options": [
            {"text": "Программистом или изобретателем роботов", "weights": {"technology": 2, "science": 1}},
            {"text": "Художником, аниматором или дизайнером", "weights": {"art": 2, "creative": 2}},
            {"text": "Спортсменом или тренером", "weights": {"sports": 2}},
            {"text": "Врачом или учителем", "weights": {"helping": 2, "social": 1}},
            {"text": "Директором или предпринимателем", "weights": {"business": 2, "social": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.junior, "order": 2,
        "text": "Что ты хотел бы делать на работе каждый день?",
        "options": [
            {"text": "Придумывать и создавать новые технологии", "weights": {"technology": 2, "science": 1}},
            {"text": "Рисовать, лепить или создавать красивые вещи", "weights": {"art": 2, "creative": 2}},
            {"text": "Тренироваться и участвовать в соревнованиях", "weights": {"sports": 2}},
            {"text": "Помогать людям, которым плохо", "weights": {"helping": 2, "social": 1}},
            {"text": "Организовывать дела и людей", "weights": {"business": 2, "social": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.junior, "order": 3,
        "text": "Какая профессия кажется тебе самой крутой?",
        "options": [
            {"text": "Астронавт или учёный", "weights": {"science": 2, "technology": 1}},
            {"text": "Аниматор или видеоблогер", "weights": {"art": 2, "creative": 2, "technology": 1}},
            {"text": "Профессиональный спортсмен", "weights": {"sports": 2}},
            {"text": "Ветеринар или детский врач", "weights": {"helping": 2, "nature": 1}},
            {"text": "Повар или кондитер", "weights": {"creative": 1, "helping": 1, "social": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.junior, "order": 4,
        "text": "Что ты хочешь изменить в мире, когда вырастешь?",
        "options": [
            {"text": "Создать умные машины, которые помогают людям", "weights": {"technology": 2, "helping": 1}},
            {"text": "Сделать мир красивее с помощью искусства", "weights": {"art": 2, "creative": 2}},
            {"text": "Чтобы все дети занимались спортом и были здоровы", "weights": {"sports": 2, "helping": 1}},
            {"text": "Чтобы все люди были здоровы и счастливы", "weights": {"helping": 2, "social": 2}},
            {"text": "Чтобы у всех было достаточно еды и денег", "weights": {"business": 1, "helping": 2}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.junior, "order": 5,
        "text": "Что из этого ты хотел бы попробовать прямо сейчас?",
        "options": [
            {"text": "Написать простую программу", "weights": {"technology": 2}},
            {"text": "Нарисовать иллюстрацию к своей истории", "weights": {"art": 2, "creative": 2, "humanitarian": 1}},
            {"text": "Научиться делать сложный спортивный трюк", "weights": {"sports": 2}},
            {"text": "Навестить кого-то или помочь соседу", "weights": {"helping": 2, "social": 1}},
            {"text": "Открыть маленький киоск или ярмарку в школе", "weights": {"business": 2, "social": 1}},
        ],
    },

    # --- middle ---
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.middle, "order": 1,
        "text": "В какой сфере ты видишь себя в будущем?",
        "options": [
            {"text": "IT, технологии, инженерия", "weights": {"technology": 2, "science": 1}},
            {"text": "Дизайн, медиа, творческие профессии", "weights": {"art": 2, "creative": 2}},
            {"text": "Медицина или психология", "weights": {"helping": 2, "science": 1}},
            {"text": "Бизнес, менеджмент или предпринимательство", "weights": {"business": 2, "social": 1}},
            {"text": "Образование, социальная сфера, НКО", "weights": {"helping": 2, "social": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.middle, "order": 2,
        "text": "Какая работа кажется тебе наиболее привлекательной?",
        "options": [
            {"text": "Разработчик программного обеспечения", "weights": {"technology": 2}},
            {"text": "Графический дизайнер или видеоблогер", "weights": {"art": 2, "creative": 2}},
            {"text": "Врач, медсестра или психолог", "weights": {"helping": 2, "social": 1}},
            {"text": "Юрист или политик", "weights": {"humanitarian": 2, "social": 1, "business": 1}},
            {"text": "Учёный или исследователь", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.middle, "order": 3,
        "text": "Какая задача тебе показалась бы самой интересной?",
        "options": [
            {"text": "Написать алгоритм или создать приложение", "weights": {"technology": 2}},
            {"text": "Разработать дизайн для нового продукта", "weights": {"art": 2, "creative": 2}},
            {"text": "Поставить диагноз пациенту и помочь ему выздороветь", "weights": {"helping": 2, "science": 1}},
            {"text": "Составить бизнес-план или выиграть дебаты", "weights": {"business": 2, "humanitarian": 1}},
            {"text": "Провести научное исследование и опубликовать результаты", "weights": {"science": 2, "technology": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.middle, "order": 4,
        "text": "Что из этого кажется тебе важнее для общества?",
        "options": [
            {"text": "Технологии, которые упрощают жизнь людям", "weights": {"technology": 2, "helping": 1}},
            {"text": "Искусство, которое вдохновляет и объединяет", "weights": {"art": 2, "creative": 1, "social": 1}},
            {"text": "Медицина и здоровье каждого человека", "weights": {"helping": 2, "science": 1}},
            {"text": "Справедливые законы и честный бизнес", "weights": {"humanitarian": 1, "business": 2}},
            {"text": "Образование и равные возможности для каждого", "weights": {"helping": 2, "social": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.middle, "order": 5,
        "text": "Каким специалистом ты хотел бы стать?",
        "options": [
            {"text": "Тем, кто создаёт умные системы и технологии", "weights": {"technology": 2, "science": 1}},
            {"text": "Тем, кто создаёт красивые и вдохновляющие вещи", "weights": {"art": 2, "creative": 2}},
            {"text": "Тем, кто помогает людям поправиться или чувствовать себя лучше", "weights": {"helping": 2, "social": 1}},
            {"text": "Тем, кто управляет компаниями и создаёт рабочие места", "weights": {"business": 2, "social": 1}},
            {"text": "Тем, кто обучает и передаёт знания другим", "weights": {"helping": 2, "humanitarian": 2, "social": 1}},
        ],
    },

    # --- senior ---
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.senior, "order": 1,
        "text": "В какой профессиональной области ты планируешь строить карьеру?",
        "options": [
            {"text": "IT, разработка ПО, Data Science, AI", "weights": {"technology": 2, "science": 1}},
            {"text": "Дизайн, медиа, кино, музыка, архитектура", "weights": {"art": 2, "creative": 2}},
            {"text": "Медицина, фармация, психология, социальная работа", "weights": {"helping": 2, "science": 1}},
            {"text": "Право, государственное управление, финансы", "weights": {"humanitarian": 1, "business": 2}},
            {"text": "Наука, исследования, академическая деятельность", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.senior, "order": 2,
        "text": "Что для тебя важнее в профессии?",
        "options": [
            {"text": "Технологическое влияние: масштаб и инновации", "weights": {"technology": 2}},
            {"text": "Творческая свобода и авторство", "weights": {"creative": 2, "art": 2}},
            {"text": "Прямая помощь людям", "weights": {"helping": 2, "social": 2}},
            {"text": "Статус, доход и карьерный рост", "weights": {"business": 2}},
            {"text": "Исследования и вклад в знания человечества", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.senior, "order": 3,
        "text": "Чем занимались бы твои идеальные рабочие дни?",
        "options": [
            {"text": "Решением сложных технических задач и написанием кода", "weights": {"technology": 2, "science": 1}},
            {"text": "Созданием визуальных или аудио продуктов", "weights": {"art": 2, "creative": 2}},
            {"text": "Консультациями, терапией, уходом за людьми", "weights": {"helping": 2, "social": 2}},
            {"text": "Переговорами, управлением, принятием решений", "weights": {"business": 2, "social": 1}},
            {"text": "Экспериментами, анализом данных, написанием статей", "weights": {"science": 2, "technology": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.senior, "order": 4,
        "text": "Кто из известных людей вдохновляет тебя профессионально?",
        "options": [
            {"text": "Маск, Торвальдс, Тьюринг — создатели технологий", "weights": {"technology": 2, "science": 1}},
            {"text": "Пикассо, Нолан, Кобейн — художники и творцы", "weights": {"art": 2, "creative": 2}},
            {"text": "Ганди, Тереза, Манделла — гуманисты и защитники", "weights": {"helping": 1, "humanitarian": 2, "social": 1}},
            {"text": "Безос, Зукерберг, Маск — предприниматели и лидеры", "weights": {"business": 2, "technology": 1}},
            {"text": "Кюри, Хокинг, Дарвин — исследователи и учёные", "weights": {"science": 2, "nature": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.senior, "order": 5,
        "text": "Какую профессию ты бы выбрал из этого списка?",
        "options": [
            {"text": "Инженер-программист или специалист по данным", "weights": {"technology": 2, "science": 1}},
            {"text": "UX/UI-дизайнер, режиссёр или архитектор", "weights": {"art": 2, "creative": 2, "technology": 1}},
            {"text": "Врач, психотерапевт или социальный работник", "weights": {"helping": 2, "science": 1}},
            {"text": "Инвестиционный аналитик или предприниматель", "weights": {"business": 2, "science": 1}},
            {"text": "Учёный, исследователь или преподаватель в вузе", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.directions, "age_group": AgeGroup.senior, "order": 6,
        "text": "Какая рабочая среда тебе ближе?",
        "options": [
            {"text": "Технологический стартап или IT-компания", "weights": {"technology": 2, "business": 1}},
            {"text": "Творческое агентство, студия или независимые проекты", "weights": {"art": 2, "creative": 2}},
            {"text": "Больница, клиника, НКО или школа", "weights": {"helping": 2, "social": 2}},
            {"text": "Корпорация, банк или государственная структура", "weights": {"business": 2, "humanitarian": 1}},
            {"text": "Университет, исследовательский институт или лаборатория", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },

    # =========================================================
    # BLOCK: goal_clarification
    # =========================================================

    # --- junior ---
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.junior, "order": 1,
        "text": "Что ты хочешь делать, когда закончишь школу?",
        "options": [
            {"text": "Учиться в университете и стать учёным или инженером", "weights": {"science": 2, "technology": 1}},
            {"text": "Учиться в творческом вузе или студии", "weights": {"art": 2, "creative": 2}},
            {"text": "Стать профессиональным спортсменом", "weights": {"sports": 2}},
            {"text": "Научиться помогать людям: стать врачом или учителем", "weights": {"helping": 2, "social": 1}},
            {"text": "Придумать своё дело и стать предпринимателем", "weights": {"business": 2, "creative": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.junior, "order": 2,
        "text": "Что важнее для тебя в будущем?",
        "options": [
            {"text": "Иметь интересную и умную работу", "weights": {"science": 2, "technology": 1}},
            {"text": "Создавать что-то красивое", "weights": {"art": 2, "creative": 2}},
            {"text": "Быть здоровым и сильным", "weights": {"sports": 2}},
            {"text": "Помогать людям", "weights": {"helping": 2, "social": 2}},
            {"text": "Зарабатывать много денег", "weights": {"business": 2}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.junior, "order": 3,
        "text": "Какое будущее кажется тебе самым интересным?",
        "options": [
            {"text": "Работать с компьютерами и технологиями", "weights": {"technology": 2}},
            {"text": "Заниматься любимым творчеством", "weights": {"art": 2, "creative": 2}},
            {"text": "Участвовать в соревнованиях и добиваться рекордов", "weights": {"sports": 2}},
            {"text": "Заботиться о больных или маленьких детях", "weights": {"helping": 2, "social": 1}},
            {"text": "Путешествовать и изучать разные страны", "weights": {"humanitarian": 2, "social": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.junior, "order": 4,
        "text": "Если бы у тебя было волшебство, что ты бы сделал для мира?",
        "options": [
            {"text": "Создал бы умных роботов, которые помогают людям", "weights": {"technology": 2, "helping": 1}},
            {"text": "Сделал бы мир красивее: больше музеев, картин, музыки", "weights": {"art": 2, "creative": 2}},
            {"text": "Сделал бы так, чтобы все занимались спортом", "weights": {"sports": 2, "helping": 1}},
            {"text": "Вылечил бы все болезни", "weights": {"helping": 2, "science": 1}},
            {"text": "Помог бы всем людям стать счастливыми", "weights": {"helping": 2, "social": 2}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.junior, "order": 5,
        "text": "О чём ты думаешь, когда мечтаешь о взрослой жизни?",
        "options": [
            {"text": "О том, как делаю крутые изобретения или пишу программы", "weights": {"technology": 2, "science": 1}},
            {"text": "О том, как рисую, снимаю кино или пою на сцене", "weights": {"art": 2, "creative": 2}},
            {"text": "О том, как выигрываю олимпиады или соревнования", "weights": {"sports": 2, "business": 1}},
            {"text": "О том, как лечу людей или учу детей", "weights": {"helping": 2, "social": 1}},
            {"text": "О том, как открываю свой бизнес или магазин", "weights": {"business": 2, "creative": 1}},
        ],
    },

    # --- middle ---
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.middle, "order": 1,
        "text": "Что для тебя важнее всего при выборе профессии?",
        "options": [
            {"text": "Интересные задачи и возможность развиваться", "weights": {"science": 2, "technology": 1}},
            {"text": "Возможность творить и самовыражаться", "weights": {"creative": 2, "art": 2}},
            {"text": "Помощь людям и социальная значимость", "weights": {"helping": 2, "social": 2}},
            {"text": "Хороший заработок и карьерные перспективы", "weights": {"business": 2}},
            {"text": "Стабильность и уверенность в завтрашнем дне", "weights": {"business": 1, "helping": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.middle, "order": 2,
        "text": "Ты уже знаешь, кем хочешь стать?",
        "options": [
            {"text": "Да, я хочу работать в сфере технологий", "weights": {"technology": 2, "science": 1}},
            {"text": "Да, я хочу связать жизнь с творчеством", "weights": {"art": 2, "creative": 2}},
            {"text": "Хочу помогать людям, но ещё не знаю как именно", "weights": {"helping": 2, "social": 1}},
            {"text": "Думаю о бизнесе или управлении", "weights": {"business": 2}},
            {"text": "Ещё не решил, хочу узнать больше о себе", "weights": {"humanitarian": 1, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.middle, "order": 3,
        "text": "Что бы ты хотел сделать после 9-го или 11-го класса?",
        "options": [
            {"text": "Поступить на техническую специальность", "weights": {"technology": 2, "science": 1}},
            {"text": "Поступить на творческую специальность", "weights": {"art": 2, "creative": 2}},
            {"text": "Поступить в медицинский или педагогический", "weights": {"helping": 2, "social": 1}},
            {"text": "Поступить на экономику, право или управление", "weights": {"business": 2, "humanitarian": 1}},
            {"text": "Сначала разобраться, чего хочу на самом деле", "weights": {"humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.middle, "order": 4,
        "text": "Как бы ты хотел, чтобы тебя помнили?",
        "options": [
            {"text": "Как человека, который изменил технологии", "weights": {"technology": 2}},
            {"text": "Как художника или творца", "weights": {"art": 2, "creative": 2}},
            {"text": "Как того, кто помогал другим", "weights": {"helping": 2, "social": 2}},
            {"text": "Как успешного человека, который добился многого", "weights": {"business": 2}},
            {"text": "Как мудрого и думающего человека", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.middle, "order": 5,
        "text": "Что сейчас мешает принять решение о будущей профессии?",
        "options": [
            {"text": "Мне нравится несколько технических направлений", "weights": {"technology": 1, "science": 1}},
            {"text": "Мне нравится всё творческое, но непонятно, на чём сосредоточиться", "weights": {"art": 1, "creative": 1}},
            {"text": "Не знаю, где именно лучше всего помогать людям", "weights": {"helping": 1, "social": 1}},
            {"text": "Неуверен, получится ли достаточно зарабатывать", "weights": {"business": 2}},
            {"text": "Я ещё не знаю, чем именно хочу заниматься в жизни", "weights": {"humanitarian": 1}},
        ],
    },

    # --- senior ---
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.senior, "order": 1,
        "text": "Какой главный вопрос ты решаешь при выборе пути?",
        "options": [
            {"text": "Где я буду наиболее эффективен как специалист?", "weights": {"technology": 1, "science": 1}},
            {"text": "Где смогу реализовать свой творческий потенциал?", "weights": {"creative": 2, "art": 2}},
            {"text": "Где смогу приносить максимальную пользу людям?", "weights": {"helping": 2, "social": 2}},
            {"text": "Где меня ждут лучшие карьерные и финансовые перспективы?", "weights": {"business": 2}},
            {"text": "Что мне действительно интересно изучать и делать?", "weights": {"science": 1, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.senior, "order": 2,
        "text": "После школы ты планируешь...",
        "options": [
            {"text": "Поступить в технический университет (IT, физтех, политех)", "weights": {"technology": 2, "science": 1}},
            {"text": "Поступить в творческий вуз или художественное училище", "weights": {"art": 2, "creative": 2}},
            {"text": "Поступить в медицинский, педагогический или социальный", "weights": {"helping": 2, "social": 1}},
            {"text": "Поступить на экономику, право или управление", "weights": {"business": 2, "humanitarian": 1}},
            {"text": "Ещё не решил / рассматриваю несколько вариантов", "weights": {"humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.senior, "order": 3,
        "text": "Что будет главным в твоей жизни через 5 лет?",
        "options": [
            {"text": "Учёба в сильном техническом университете", "weights": {"technology": 2, "science": 1}},
            {"text": "Развитие творческих навыков и создание портфолио", "weights": {"art": 2, "creative": 2}},
            {"text": "Профессиональная практика в сфере помощи людям", "weights": {"helping": 2, "social": 1}},
            {"text": "Первые шаги в карьере и бизнесе", "weights": {"business": 2}},
            {"text": "Путешествия, опыт и поиск своего пути", "weights": {"humanitarian": 2, "social": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.senior, "order": 4,
        "text": "Что влияет на твой выбор профессии больше всего?",
        "options": [
            {"text": "Мои способности и интерес к конкретной области", "weights": {"science": 1, "technology": 1}},
            {"text": "Возможность реализовать творческий потенциал", "weights": {"creative": 2, "art": 1}},
            {"text": "Желание помогать людям и делать добро", "weights": {"helping": 2, "social": 2}},
            {"text": "Перспективы заработка и карьерного роста", "weights": {"business": 2}},
            {"text": "Советы родителей или значимых для меня людей", "weights": {"humanitarian": 1, "social": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.senior, "order": 5,
        "text": "Если бы не думал о деньгах и мнении других, что выбрал бы?",
        "options": [
            {"text": "Разработка технологий или научные исследования", "weights": {"technology": 2, "science": 2}},
            {"text": "Творческая профессия: художник, музыкант, режиссёр", "weights": {"art": 2, "creative": 2}},
            {"text": "Работа с людьми: психолог, врач, педагог", "weights": {"helping": 2, "social": 2}},
            {"text": "Собственный бизнес или социальный проект", "weights": {"business": 2, "social": 1}},
            {"text": "Путешествия, исследование мира, писательство", "weights": {"humanitarian": 2, "nature": 1}},
        ],
    },
    {
        "block": QuestionBlock.goal_clarification, "age_group": AgeGroup.senior, "order": 6,
        "text": "Как ты относишься к выбору профессии прямо сейчас?",
        "options": [
            {"text": "Я знаю, чего хочу, и уже действую в этом направлении", "weights": {"technology": 1, "science": 1, "business": 1}},
            {"text": "У меня есть творческое направление, которому я следую", "weights": {"creative": 2, "art": 2}},
            {"text": "Я ориентируюсь на помощь людям, ищу конкретный путь", "weights": {"helping": 2, "social": 1}},
            {"text": "Я думаю прагматично: хочу хорошую карьеру и доход", "weights": {"business": 2}},
            {"text": "Я всё ещё исследую свои интересы и возможности", "weights": {"humanitarian": 1, "science": 1}},
        ],
    },

    # =========================================================
    # BLOCK: university (senior only, 8 questions)
    # =========================================================

    {
        "block": QuestionBlock.university, "age_group": AgeGroup.senior, "order": 1,
        "text": "Какое направление учёбы тебе ближе?",
        "options": [
            {"text": "Точные и технические науки (математика, физика, IT)", "weights": {"technology": 2, "science": 2}},
            {"text": "Гуманитарные науки (история, языки, психология)", "weights": {"humanitarian": 2, "social": 1}},
            {"text": "Медицинские и биологические науки", "weights": {"helping": 2, "science": 1, "nature": 1}},
            {"text": "Юридические и экономические науки", "weights": {"business": 2, "humanitarian": 1}},
            {"text": "Творческие специальности (дизайн, кино, музыка)", "weights": {"art": 2, "creative": 2}},
        ],
    },
    {
        "block": QuestionBlock.university, "age_group": AgeGroup.senior, "order": 2,
        "text": "Какой тип университета тебя привлекает?",
        "options": [
            {"text": "Технический университет или политехнический институт", "weights": {"technology": 2, "science": 1}},
            {"text": "Университет искусств, культуры или медиа", "weights": {"art": 2, "creative": 2}},
            {"text": "Медицинский или фармацевтический университет", "weights": {"helping": 2, "science": 1}},
            {"text": "Юридический или экономический университет", "weights": {"business": 2, "humanitarian": 1}},
            {"text": "Классический университет с широким профилем", "weights": {"humanitarian": 2, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.university, "age_group": AgeGroup.senior, "order": 3,
        "text": "Что тебе важнее при выборе специальности?",
        "options": [
            {"text": "Востребованность на рынке труда и высокий заработок", "weights": {"business": 2, "technology": 1}},
            {"text": "Возможность заниматься любимым делом", "weights": {"creative": 2, "art": 1}},
            {"text": "Польза для общества и людей", "weights": {"helping": 2, "social": 2}},
            {"text": "Интересность и глубина предмета изучения", "weights": {"science": 2, "humanitarian": 1}},
            {"text": "Соответствие моим способностям и сильным сторонам", "weights": {"technology": 1, "science": 1}},
        ],
    },
    {
        "block": QuestionBlock.university, "age_group": AgeGroup.senior, "order": 4,
        "text": "Что стало главным при выборе вуза?",
        "options": [
            {"text": "Рейтинг и качество технической подготовки", "weights": {"technology": 2, "science": 1}},
            {"text": "Творческая среда и известные преподаватели", "weights": {"art": 2, "creative": 2}},
            {"text": "Специализация на медицине, психологии или педагогике", "weights": {"helping": 2, "social": 1}},
            {"text": "Связи с бизнесом, юриспруденцией или государством", "weights": {"business": 2, "humanitarian": 1}},
            {"text": "Исследовательские возможности и научная база", "weights": {"science": 2, "humanitarian": 1}},
        ],
    },
    {
        "block": QuestionBlock.university, "age_group": AgeGroup.senior, "order": 5,
        "text": "Как ты представляешь студенческую жизнь?",
        "options": [
            {"text": "Хакатоны, технические проекты, стартапы", "weights": {"technology": 2}},
            {"text": "Выставки, перформансы, творческие коллаборации", "weights": {"art": 2, "creative": 2}},
            {"text": "Практика в клиниках, работа с людьми, волонтёрство", "weights": {"helping": 2, "social": 2}},
            {"text": "Дебаты, кейс-чемпионаты, стажировки в компаниях", "weights": {"business": 2, "social": 1}},
            {"text": "Конференции, лаборатории, научные экспедиции", "weights": {"science": 2, "nature": 1}},
        ],
    },
    {
        "block": QuestionBlock.university, "age_group": AgeGroup.senior, "order": 6,
        "text": "Где ты хотел бы работать после университета?",
        "options": [
            {"text": "В технологической компании или стартапе", "weights": {"technology": 2, "business": 1}},
            {"text": "В творческой студии, агентстве или как фрилансер", "weights": {"art": 2, "creative": 2}},
            {"text": "В больнице, школе, социальной службе или НКО", "weights": {"helping": 2, "social": 2}},
            {"text": "В банке, юридической фирме или госструктуре", "weights": {"business": 2, "humanitarian": 1}},
            {"text": "В университете, исследовательском институте или лаборатории", "weights": {"science": 2, "technology": 1}},
        ],
    },
    {
        "block": QuestionBlock.university, "age_group": AgeGroup.senior, "order": 7,
        "text": "Что важнее: диплом или реальные навыки?",
        "options": [
            {"text": "Важнее навыки — в IT это особенно важно", "weights": {"technology": 2}},
            {"text": "Важно и то, и другое — творческий портфолио + образование", "weights": {"art": 1, "creative": 2}},
            {"text": "Важен диплом — в медицине или праве без него нельзя", "weights": {"helping": 1, "business": 1, "humanitarian": 1}},
            {"text": "Важнее связи и реальный опыт в индустрии", "weights": {"business": 2, "social": 1}},
            {"text": "Важна глубина знаний, которую даёт классическое образование", "weights": {"science": 2, "humanitarian": 2}},
        ],
    },
    {
        "block": QuestionBlock.university, "age_group": AgeGroup.senior, "order": 8,
        "text": "Если бы нужно было выбрать прямо сейчас, ты выбрал бы...",
        "options": [
            {"text": "Технический вуз с высокой зарплатой после выпуска", "weights": {"technology": 2, "business": 1}},
            {"text": "Творческий вуз с возможностью заниматься любимым делом", "weights": {"art": 2, "creative": 2}},
            {"text": "Медицинский или педагогический — чтобы помогать людям", "weights": {"helping": 2, "social": 2}},
            {"text": "Юридический или экономический — для карьеры и влияния", "weights": {"business": 2, "humanitarian": 1}},
            {"text": "Классический исследовательский университет", "weights": {"science": 2, "humanitarian": 2}},
        ],
    },
]


async def main() -> None:
    async with async_session() as db:
        inserted = 0
        skipped = 0

        for q in QUESTIONS:
            result = await db.execute(
                select(Question).where(
                    Question.block == q["block"],
                    Question.age_group == q["age_group"],
                    Question.text == q["text"],
                )
            )
            if result.scalar_one_or_none() is not None:
                skipped += 1
                continue

            db.add(Question(
                block=q["block"],
                age_group=q["age_group"],
                text=q["text"],
                options=q["options"],
                order=q["order"],
            ))
            inserted += 1

        await db.commit()
        print(f"Done. Inserted: {inserted}, skipped (already exist): {skipped}")
        print(f"Total questions in data: {len(QUESTIONS)}")


if __name__ == "__main__":
    asyncio.run(main())
