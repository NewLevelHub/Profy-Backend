# Roadmap API — контракт для фронтенда

Обновлено: 2026-08-07. Полностью переписано под RIASEC-движок — предыдущая
версия этого файла описывала контракт для старого 24-осевого движка
(`profession_options`, `subjects_now`, `POST /roadmap/directions` во
множественном числе), который в коде больше не существует. Всё ниже
проверено прямым чтением текущего кода (`app/routers/`, `app/schemas/`,
`app/services/roadmap_builder.py`) и реальным деплоем в dev-окружении.

**Правка того же дня (Область 9 — глубина текста + Big Five/мотивация в
промптах):** JSON-форма ответов **не изменилась** — ни новых, ни
переименованных, ни удалённых полей. Изменилось наполнение двух полей:

- `RoadmapTask.description` (goal roadmap, п.2) — раньше почти всегда
  `null`, теперь обязательный элемент JSON-схемы для модели и обычно
  заполнен (несколько предложений, не одна общая фраза), если LLM доступна.
  Тип поля как был `str | null`, так и остался — `null` по-прежнему
  возможен при шаблонном фолбэке (LLM недоступна), фронт должен продолжать
  обрабатывать оба случая.
- `DirectionRoadmapResponse.target.why` / `growth_focus.evidence` /
  `stages[].steps[].description` (direction roadmap, п.3) — контент стал
  честнее и глубже: `evidence` больше не может содержать процент/балл
  (только тип/черта словами — сам факт не показа чисел ребёнку не менялся,
  просто раньше промпт сам об этом просил, теперь это исправлено),
  `why`/`description` теперь могут опираться на стиль личности и мотивацию
  ученика (новый безопасный слой данных), когда это реально относится к
  делу. Форма (ключи, типы) та же самая, верстать заново не нужно.

---

## 0. Общий флоу — от регистрации до роадмапа

```
POST /api/v1/auth/register → /verify-email → /login   (получаем access_token)
POST /api/v1/profile                                   (создать профиль ребёнка)
POST /api/v1/profile/artifacts                          (опционально, хобби/достижения)
POST /api/v1/assessment/start                            {"goal": "..."}
  ↓
GET  /api/v1/assessment/{id}/questions                   (junior: MI + Big Five;
                                                           middle/senior: RIASEC + Big Five)
GET  /api/v1/assessment/{id}/pairs                       (junior: Big Five; middle: RIASEC + Big Five)
  ↓
POST /api/v1/assessment/{id}/answers
POST /api/v1/assessment/{id}/pair-answers
  ↓ motivation зависит от возраста:
junior/middle:
  GET  /api/v1/assessment/{id}/motivation-pairs
  POST /api/v1/assessment/{id}/motivation-pair-answers
senior:
  GET  /api/v1/assessment/{id}/motivation-triplets
  POST /api/v1/assessment/{id}/motivation-answers
  ↓ последний обязательный submit переводит Assessment в completed,
    только когда закрыты Likert/pairs и возрастной motivation-трек
  ↓
POST /api/v1/result/generate                              {"assessment_id"}  → отчёт
  ↓
POST /api/v1/roadmap/generate                              → общий план (доступен всегда)
  ИЛИ, для глубокого плана по направлению:
GET  /api/v1/inquiry/{id}/directions/{slug}/questions
POST /api/v1/inquiry/{id}/directions/{slug}/verdict
POST /api/v1/roadmap/direction                             → план по направлению
```

Все запросы ниже требуют `Authorization: Bearer <access_token>`, кроме
`/auth/*`.

---

## 1. Предпосылки для роадмапа

**Критично**: без `POST /result/generate` роадмап сгенерируется пустышкой —
код это не блокирует, просто у `AnalysisResult` нет строки, и весь
персонализирующий сигнал (MI для junior или RIASEC для middle/senior,
Big Five, мотивация, а для RIASEC также топ направлений и сильные/слабые
стороны) будет пустым. Всегда вызывать `/result/generate` до роадмапа.

Для **direction roadmap** дополнительно обязателен пройденный AI-опрос по
конкретному направлению (`/inquiry/.../verdict`) — без него 400.

---

## 2. Goal roadmap — общий план, без выбора направления

### Сгенерировать / перегенерировать

```
POST /api/v1/roadmap/generate
Content-Type: application/json

{
  "assessment_id": "uuid",
  "program_id": "uuid | null"    // опционально; имеет смысл только для goal=university —
                                  // включает гэп-анализ по конкретной программе вуза
}
```

Доступен для **любого возраста и любой цели** сразу после `/result/generate`
— никаких дополнительных гейтов. При недоступной LLM — детерминированный
шаблонный план (не ошибка, деградация).

### Получить сохранённый

```
GET /api/v1/roadmap/{assessment_id}
```

### Форма ответа — `RoadmapResponse`

```jsonc
{
  "id": "uuid",
  "assessment_id": "uuid",
  "goal": "explore",                 // explore | profession | university | unsure
  "milestones": [
    {
      "horizon": "month_1",          // month_1 | months_3 | months_6 | year_1 | until_goal
      "title": "Первый шаг: исследование возможностей",
      "tasks": [
        {
          "text": "Узнай подробнее о направлении «...»",
          "description": "Посмотри 2-3 коротких видео о том, чем занимается специалист в этой сфере — обрати внимание, какие задачи повторяются чаще всего. Через неделю сможешь своими словами объяснить, чем этот человек занят в течение дня.",
          // теперь обычно заполнено (несколько предложений по делу, не общая фраза) —
          // null остаётся только при шаблонном фолбэке, когда LLM недоступна
          "category": "explore",
          "priority": 1,
          "resources": []             // всегда [] — каталога курсов/книг пока нет
        }
      ]
    }
    // ... ещё 4 горизонта, всегда ровно 5, в этом порядке
  ]
}
```

**404**, если план ещё не генерировался (`GET` без предварительного `POST`).

---

## 3. Direction roadmap — глубокий план по одному направлению

### Сгенерировать / перегенерировать (и подтвердить направление)

```
POST /api/v1/roadmap/direction
Content-Type: application/json

{
  "assessment_id": "uuid",
  "direction_slug": "razrabotchik-programmnogo-obespecheniya"
}
```

Вызов **сам подтверждает направление** — выставляет
`Assessment.selected_direction_slug`. Отдельного шага "подтвердить" нет.

**Гейты, в порядке проверки:**

| Условие | Ответ |
|---|---|
| Нет `Assessment`/доступа | 404 / 403 |
| Возраст — junior (6-9 лет) | 403 «Эта возможность доступна с 10 лет» |
| Нет пройденного AI-опроса по этому `slug` (`DirectionInquiry`) | 400 «Сначала пройди опрос по этому направлению» |
| LLM недоступна / не смогла построить валидный план за 2 попытки | 503 «ИИ временно недоступен, попробуй ещё раз» |

Цель `university` **тоже** проходит через этот эндпоинт (не исключение
больше) — получает тот же план плюс блок `university_requirements` с
реальными фактами по вузам.

### Получить сохранённый

```
GET /api/v1/roadmap/{assessment_id}/directions/{slug}
```

### Форма ответа — `DirectionRoadmapResponse`

```jsonc
{
  "id": "uuid",
  "assessment_id": "uuid",
  "direction_slug": "razrabotchik-programmnogo-obespecheniya",
  "direction_name": "Разработчик программного обеспечения",

  "target": {
    "role": "Backend-разработчик",
    "why": "Сильная логика и опыт участия в олимпиадах по программированию...",
    "horizon_years": 5
  },

  "growth_focus": {
    "weakness": "Работа в команде над чужим кодом, а не только над своими проектами",
    "why_it_matters": "В реальной разработке большая часть работы — это доработка чужого кода",
    "evidence": "В опросе по направлению ты не согласился с утверждением '...'"
  },

  "stages": [
    {
      "horizon": "months_3",         // months_3 | months_6 | months_9 | months_12 — ровно 4
      "title": "Базовые знания",
      "outcome": "Разберёшься в основах на уровне простых проектов",
      "steps": [
        {
          "text": "Изучи основы Arduino",
          "description": "Пройди вводный курс... Готово, когда сможешь сам...",
          "track": "profile",         // profile | growth | integration
          "category": "skill",        // knowledge|skill|practice|project|portfolio|soft_skill|subject|community|exam|university
          "priority": 1,
          "resources": []
        }
      ],
      "integration_project": null     // строка, только начиная с months_9, иначе null
    }
    // ещё 3 этапа, всегда ровно 4
  ],

  "skills_to_build": ["Работа с Arduino", "Программирование"],
  "subjects_to_focus": ["Математика", "Информатика"],

  "university_track": {
    "specialties": ["Информационные системы"],
    "prepare": ["Портфолио проектов на GitHub", "Профильная математика"]
  },

  "university_requirements": [
    // ВСЕГДА [] для goal != university.
    // Для goal == university — реальные факты по программам, привязанным
    // к этому направлению (Program.profession_slugs), без участия LLM.
    {
      "program_name": "Компьютерные науки (бакалавр)",
      "university_name": "Nazarbayev University",
      "city": "Астана",
      "exams": ["ЕНТ", "SAT"],
      "application_deadline": "2026-02-28",   // null = нет данных, НЕ "не требуется"
      "grants": [
        { "name": "Президентская стипендия", "amount": "100%", "conditions": "Конкурс по ЕНТ" }
      ],
      "language_level": "IELTS 6.5",           // null = нет данных
      "portfolio_needed": true,                 // true/false — подтверждённый факт; null = нет данных
      "required_documents": ["Мотивационное эссе"]  // null = нет данных; [] = подтверждено "ничего доп. не нужно"
    }
  ]
}
```

**Важное правило по `university_requirements[].*`** (унаследовано от общей
дисциплины проекта): `null` ≠ «не требуется». `null` = «данных пока нет».
Если бэкенд явно знает факт — вернётся конкретное значение, в том числе
`false`/`[]`. Рендерить нужно три состояния, не два (см. таблицу):

| Значение | Что показывать |
|---|---|
| `null` | «нет данных» / не показывать блок |
| `false` / `[]` | «не требуется» — подтверждённый факт |
| значение / непустой список | сам факт |

---

## 4. Ошибки, общие для обоих эндпоинтов

| Код | Когда | Тело |
|---|---|---|
| 401 | нет/невалидный токен | стандартный FastAPI auth error |
| 403 | `assessment_id` принадлежит другому пользователю | `{"detail": "Access denied"}` |
| 404 | `assessment_id` не найден, или `GET` без предварительного `POST` | `{"detail": "..."}` |
| 400 | direction roadmap без пройденного `DirectionInquiry` | `{"detail": "Сначала пройди опрос по этому направлению"}` |
| 403 | direction roadmap для junior | `{"detail": "Эта возможность доступна с 10 лет"}` |
| 503 | LLM недоступна / не собрала валидный план (только direction roadmap — у goal roadmap есть шаблонный фолбэк, там 503 не бывает) | `{"detail": "ИИ временно недоступен, попробуй ещё раз"}` |

---

## 5. Поведение по возрасту/цели — сводка для фронта

Assessment flow до генерации результата:

| | junior (6-9) | middle (10-13) | senior (14-18) |
|---|---|---|---|
| Interest instrument | MI | RIASEC | RIASEC |
| Обычные вопросы | MI + Big Five | RIASEC + Big Five | RIASEC + Big Five |
| Question pairs | Big Five | RIASEC + Big Five | не используются |
| Motivation GET | `/motivation-pairs` | `/motivation-pairs` | `/motivation-triplets` |
| Motivation POST | `/motivation-pair-answers` | `/motivation-pair-answers` | `/motivation-answers` |
| Result careers | всегда `[]` | RIASEC matches | RIASEC matches |

Фронт не должен отправлять junior/middle ответы в triplet endpoint или
senior ответы в pair endpoint. Выходной мотивационный блок результата при
этом един для всех возрастов (`motivation_highlights`).

Roadmap flow:

| | junior (6-9) | middle (10-13) | senior (14-18) |
|---|---|---|---|
| Goal roadmap | ✅ все цели | ✅ все цели | ✅ все цели |
| Direction roadmap | ❌ 403 всегда | ✅ (после опроса) | ✅ (после опроса) |
| `goal=university` в direction roadmap | — (недоступен по возрасту) | ✅ (получает `university_requirements`) | ✅ |

Для junior реализуемый на фронте план — только `GET/POST /roadmap/generate`
и `/roadmap/{id}`; кнопку/экран «глубокий план по направлению» для этого
возраста показывать не нужно — эндпоинт всё равно ответит 403.

---

## 6. Что ещё не реализовано (не блокирует вёрстку, но контента не будет)

- `RoadmapTask.resources` / `RoadmapStep.resources` — всегда `[]` везде,
  каталога курсов/книг/кружков нет.
- Нет отдельного поля «варианты профессий с обоснованием» (`profession_options`
  из старой версии этого контракта) — список направлений с match_score
  сейчас отдаётся только внутри `/result` (`AnalysisResultResponse.careers`),
  не внутри роадмапа.
- Три «корзины» вузов (амбициозные/реалистичные/запасные) и дата
  обновления/источник на каждое поле `university_requirements` — не
  реализовано, весь список площадка отдаёт плоско.
