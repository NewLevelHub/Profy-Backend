# CRM API — контракт для фронтенда (Profy-CRM)

**Статус: реализовано на ветке `pro-crm-deals-booking` — 2026-10-21.** Код:
`app/routers/crm.py`, `app/services/crm/deals.py`, `app/services/scheduling/booking.py`,
`app/schemas/crm.py`, `app/models/crm.py`; тесты — `tests/integration/test_crm_deals.py`.
Основание — ТЗ CRM Profile v4.1, §2, §3.2–3.10.

Объём этого этапа: доска сделок с **ручным** перемещением и запись на созвон
в общее расписание. Интеграций нет (WhatsApp, Meta, Telegram): лиды
заводятся вручную, послепродажные этапы 7–10 двигают РОП и владелец, пока
их не начнут ставить события платформы.

Префикс — `/api/v1/crm`, auth — JWT Bearer. Ошибки — `{detail, error_code}`
(как везде, `app/errors.py`); UI строит текст по `error_code`. Время — UTC
ISO-8601.

## 1. Роли

| Роль | Доска | Карточка, изменения | Особенности |
|---|---|---|---|
| `sales_manager` | свои сделки + «Неразобранное» | свои; чужая → **404** | ставит этапы 1–5, отмечает оплату один раз, записывает на созвон; имя специалиста не видит |
| `sales_head` | все | все | плюс этапы 7–10, правка оплаты/скидки после оплаты, смена ответственного, «Успешно», закрытие оплаченной |
| `owner` | все | все | как `sales_head` |
| `marketer` | все, **без ПДн** (`parent_name`, `phone`, `student_name` = null) | **403** | только смотрит доску |
| остальные | 403 | 403 | |

## 2. Эндпоинты

| Method | Path | Кто | Назначение |
|---|---|---|---|
| GET | `/meta` | доска | этапы по порядку, тарифы, причины отказа |
| GET | `/deals?result=open\|won\|lost\|all` | доска | плитки доски (по умолчанию `open`) |
| POST | `/deals` | продажи | новый лид |
| GET | `/parents?phone=` | продажи | поиск клиента по телефону (дубли) |
| GET | `/deals/{id}` | продажи | карточка сделки с лентой |
| PATCH | `/deals/{id}` | продажи | поля родителя, ученика, квалификация, тариф, скидка, источник, ответственный |
| POST | `/deals/{id}/accept` | продажи | взять заявку из «Неразобранного» |
| POST | `/deals/{id}/stage` | продажи | перенести на этап (`{"stage": "..."}`) |
| POST | `/deals/{id}/payment` | продажи | отметить оплату |
| DELETE | `/deals/{id}/payment` | РОП, владелец | отменить оплату |
| POST | `/deals/{id}/consent` | продажи | согласие родителя (`{"given": true}`) |
| POST | `/deals/{id}/close` | продажи | закрыть: `won` / `lost` с причиной |
| POST | `/deals/{id}/notes` | продажи | примечание в ленту |
| POST | `/deals/{id}/booking` | продажи | записать на созвон |

Все изменяющие эндпоинты возвращают **карточку сделки** целиком (§4).

## 3. Этапы и правила (ТЗ §3.3)

`unsorted` → `qualification` → `consultation` → `closing` (Дожим) → `invoice` →
`paid` → `diagnostics_done` → `report_published` → `review_scheduled` → `review_done`.
Результат хранится отдельно: `open` / `won` / `lost`.

| Правило | `error_code` |
|---|---|
| Вернуть в «Неразобранное» нельзя | `stage_unsorted` |
| На `paid` — только отметкой оплаты | `stage_paid_via_payment` |
| `consultation` и дальше — только целевой лид | `deal_target_required` |
| Нецелевой не идёт дальше квалификации | `deal_non_target`, `deal_non_target_advanced` |
| `invoice` и дальше — нужен тариф | `deal_tariff_required` |
| Оплаченную нельзя вернуть до `paid` | `deal_paid_stage_back` |
| Этапы 7–10 — только РОП/владелец (403), и только после оплаты | `stage_after_sale_forbidden`, `deal_not_paid` |
| Менеджер меняет только принятую сделку | `deal_not_accepted` |
| Закрытая (`lost`) не меняется | `deal_closed` |

Новый лид: от менеджера — сразу `qualification` и он ответственный; от
РОП/владельца — в `unsorted` без ответственного.

## 4. Карточка сделки (`DealDetail`)

```jsonc
{
  "id": "…", "stage": "invoice", "result": "open",
  "lost_reason": null, "close_comment": null, "closed_at": null,
  "parent": {"id": "…", "full_name": "Асель Нурланова", "phone": "+77011234567",
             "email": null, "city": null, "consent": true, "consent_at": "…"},
  "student": {"id": "…", "full_name": "Камила", "age": 15, "gender": "female", "grade": 9,
              "city": null, "study_language": "ru", "russian_level": "fluent"},
  "manager": {"id": "…", "name": "Айгерим"},
  "is_target": true, "non_target_reason": null,
  "tariff_code": "testing", "price": 45000, "discount": 5000, "total": 40000,
  "paid_amount": null, "paid_at": null, "payment_method": null,
  "source": "Instagram", "first_message": "Здравствуйте…",
  "meeting": {"id": "…", "type": "intro30", "status": "pending",
              "start": "…", "end": "…", "specialist": null},  // имя — только РОП/владельцу
  "events": [{"id": "…", "at": "…", "actor": {"id": "…", "name": "…"},
              "kind": "payment", "data": {"amount": 40000, "method": "cash"}, "text": null}],
  "created_at": "…"
}
```

`events` — лента, новые сверху. `kind`: `created`, `accepted`, `stage`
(`data.from`/`to`), `qualified`, `tariff`, `discount`, `payment`,
`payment_cancelled`, `consent`, `manager`, `closed`, `note` (`text`), `booked`.

Плитка доски (`DealCard`): `id, stage, result, parent_name, phone,
student_name, tariff_code, total, is_target, paid, consent, manager,
meeting_start, closed_at, created_at`.

## 5. Новый лид и дубли

```jsonc
POST /deals
{"parent": {"full_name": "Асель", "phone": "8 701 123 45 67"},
 "student": {"full_name": "Камила"}, "source": "Instagram", "first_message": "…"}
```

Телефон нормализуется в `+7XXXXXXXXXX`. Если клиент с таким телефоном уже
есть → **409 `parent_exists`** с `parent_id` и `open_deal_id` в теле: UI
предлагает открыть его сделку или создать новую сделку этому клиенту —
`POST /deals {"parent_id": "…"}`.

## 6. Тариф, скидка, оплата

- `PATCH {"tariff_code": "testing"}` — цена копируется из прайса и дальше не
  меняется (ТЗ §3.7). `total = price − discount`.
- `PATCH {"discount": 5000}` — без лимита, пишется в журнал.
- `POST /payment {"amount": 40000, "method": "cash"|"transfer", "paid_at"?}` —
  нужны целевой лид и тариф; сделка переходит на `paid`. Повторная отметка,
  правка скидки/тарифа после оплаты и `DELETE /payment` — только РОП/владелец
  (`payment_change_forbidden`, `deal_paid_locked`). Отменить оплату, если
  клиент уже записан, нельзя (`payment_cancel_blocked`).

## 7. Закрытие

`POST /close {"result": "lost", "reason": "no_answer", "comment"?}` — причина
обязательна (`close_reason_required`); после оплаты — только РОП/владелец.
`{"result": "won"}` — только РОП/владелец и только оплаченная
(`deal_win_forbidden`, `deal_not_paid`). Закрытые уходят с доски
(`?result=lost|won|all`, чтобы увидеть).

Причины: `non_target`, `refused`, `no_answer`, `duplicate`, `cancelled`,
`no_show`, `refund`, `other`.

## 8. Запись на созвон (ТЗ §3.9–3.10)

```jsonc
POST /deals/{id}/booking
{
  "start": "2026-10-28T05:00:00Z",
  "handoff": {
    "student_name": "Камила Нурланова", "age": 15, "gender": "female", "grade": 9,
    "study_language": "ru", "russian_level": "fluent",
    "family_request": "Выбор профиля в 10 классе",
    "parent_participates": true, "contact": "parent", "contact_phone": "+77011234567",
    "manager_comment": null
  }
}
```

- Длительность берётся из тарифа: «Тестирование» и «Пакет» → вступительный
  30 мин (`intro30`), «Консультация» → 60 мин (`main60`). Свободное время
  для выбора — `GET /api/v1/scheduling/free?duration=30|60`.
- Условия: оплачено, целевой, есть согласие (`deal_not_paid`,
  `deal_target_required`, `consent_required`); одна активная встреча на
  сделку (`deal_already_booked`); карточка передачи — все поля, кроме
  комментария (иначе 422).
- Специалиста выбирает система: свободен на всё окно, меньше встреч на этой
  неделе → меньше сегодня → случайно. Слоты блокируются атомарно: при гонке
  проходит одна запись, вторая получает **409 `slot_taken`** — UI просит
  выбрать другое время.
- Слоты специалиста становятся `booked`, в `/free` их больше нет; специалист
  видит встречу и карточку передачи (`GET /api/v1/scheduling/specialists/me/meetings`).
- Уведомлений нет (Telegram/WhatsApp — вне текущего объёма).
