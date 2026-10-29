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
| GET | `/meta` | доска | этапы по порядку, тарифы и источники (с архивными), причины отказа |
| GET | `/staff` | владелец | сотрудники: владельцы, специалисты, отдел продаж (`{id, email, full_name, role, is_active, created_at, upcoming_meetings}`); приглашают через `/api/v1/admin/invitations` |
| POST | `/staff/{id}/active` | владелец | `{"active": false}` — «Отключить», `true` — «Включить» (§14) |
| POST | `/sources` | владелец | новый источник `{"name"}` (§5.1) |
| PATCH | `/sources/{id}` | владелец | `{"name"?, "active"?}` — переименовать, в архив (§5.1) |
| GET | `/dashboard?from=&to=` | владелец | дашборд владельца (§15) |
| GET | `/analytics/export?month=YYYY-MM` | владелец, РОП, маркетолог | .xlsx: воронка, источники, менеджеры, реклама (§16) |
| POST | `/tariffs` | владелец | новый тариф (§6.1) |
| PATCH | `/tariffs/{code}` | владелец | условия тарифа, архив (§6.1) |
| GET | `/deals?result=open\|won\|lost\|all` + фильтры §9 | доска | плитки доски (по умолчанию `open`) |
| GET | `/users` | продажи | сотрудники продаж для выбора исполнителя и фильтра |
| POST | `/deals` | продажи | новый лид |
| GET | `/parents?phone=` | продажи | поиск клиента по телефону (дубли) |
| GET | `/clients?q=` | продажи | база клиентов: дети, сделки, созвоны, оплачено (§12) |
| GET | `/deals/{id}` | продажи | карточка сделки с лентой |
| PATCH | `/deals/{id}` | продажи | поля родителя, ученика, квалификация, тариф, скидка, источник, ответственный |
| POST | `/deals/{id}/accept` | продажи | взять заявку из «Неразобранного»; владелец передаёт её `{"manager_id"}` (§5) |
| POST | `/deals/{id}/stage` | продажи | перенести на этап (`{"stage": "..."}`) |
| POST | `/deals/{id}/payment` | продажи | отметить оплату |
| DELETE | `/deals/{id}/payment` | РОП, владелец | отменить оплату |
| POST | `/deals/{id}/consent` | продажи | согласие родителя (`{"given": true}`) |
| POST | `/deals/{id}/close` | продажи | закрыть: `won` / `lost` с причиной |
| POST | `/deals/{id}/notes` | продажи | примечание в ленту |
| POST | `/deals/{id}/booking` | продажи | записать на созвон |
| POST | `/deals/{id}/invite` | продажи | новая ссылка-приглашение ученику (§13) |
| POST | `/deals/{id}/student` | РОП, владелец | привязать аккаунт ученика по почте (§13) |
| GET | `/meetings?from=&to=` | продажи | встречи на календаре (§10) |
| GET | `/meetings/{id}` | продажи | окно визита: карточка передачи и журнал |
| POST | `/meetings/{id}/status` | продажи | `confirmed`; `done`/`no_show` — только владелец |
| POST | `/meetings/{id}/cancel` | владелец, РОП; менеджер — первый созвон своей сделки | отменить с причиной |
| POST | `/meetings/{id}/reschedule` | владелец, РОП; менеджер — первый созвон своей сделки | перенести с причиной |
| POST | `/meetings/{id}/reschedule-request` | продажи | попросить владельца перенести → его задача |
| GET | `/tasks?scope=mine\|all&state=open\|done&deal_id=&assignee_id=` | продажи | задачи (§11) |
| POST | `/tasks` | продажи | поставить задачу |
| PATCH | `/tasks/{id}` | продажи | текст, срок, исполнитель |
| POST | `/tasks/{id}/done` | продажи | выполнить с результатом |

Изменяющие эндпоинты сделки возвращают **карточку сделки** целиком (§4),
встречи — окно визита (`MeetingDetail`), задачи — задачу (`TaskOut`).

## 3. Этапы и правила (ТЗ §3.3)

`unsorted` → `qualification` → `consultation` → `closing` (Дожим) → `invoice` →
`paid` → `diagnostics_done` → `review_done` → `report_published`.
«Разбор назначен» из ТЗ — не этап, а отметка на карточке (`review_start`): второй
созвон ставится с начала первого, до теста или после него.
Результат хранится отдельно: `open` / `won` / `lost`.

| Правило | `error_code` |
|---|---|
| Вернуть в «Неразобранное» нельзя | `stage_unsorted` |
| На `paid` — только отметкой оплаты | `stage_paid_via_payment` |
| `consultation` и дальше — только целевой лид | `deal_target_required` |
| Нецелевой не идёт дальше квалификации | `deal_non_target`, `deal_non_target_advanced` |
| `invoice` и дальше — нужен тариф | `deal_tariff_required` |
| Оплаченную нельзя вернуть до `paid` | `deal_paid_stage_back` |
| Этапы 7–10 вручную — только РОП/владелец (403), и только после оплаты; 7–8 ставятся и сами (§13) | `stage_after_sale_forbidden`, `deal_not_paid` |
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
  "source_id": "…", "source": "Instagram", "first_message": "Здравствуйте…",
  "meeting": {"id": "…", "type": "intro30", "status": "pending",
              "start": "…", "end": "…", "specialist": null},  // имя — только РОП/владельцу
  "student_account": {"linked": false, "email": null,
                      "invite_url": "https://…/student-invite#token=…", "invite_created_at": "…"},
  "events": [{"id": "…", "at": "…", "actor": {"id": "…", "name": "…"},
              "kind": "payment", "data": {"amount": 40000, "method": "cash"}, "text": null}],
  "created_at": "…"
}
```

`events` — лента, новые сверху. `kind`: `created`, `accepted`, `stage`
(`data.from`/`to`), `qualified`, `tariff`, `discount`, `payment`,
`payment_cancelled`, `consent`, `manager`, `closed`, `note` (`text`), `booked`,
`meeting_status` (`from`/`to`), `meeting_cancelled` (`text` — причина),
`meeting_moved` (`from`/`to`, `text` — причина), `reschedule_requested`,
`task` (`text`, `data.due_at`), `task_done` (`text` — результат), `invite`,
`student_linked` (`data.email`, `data.via`: `invite`/`owner`), `payment_check`.
У событий системы `actor` = `null`; автоматические `stage` и `closed` несут
`data.auto: true`.

`tasks` — задачи сделки: открытые по сроку, потом выполненные (`TaskOut`, §11).

Плитка доски (`DealCard`): `id, stage, result, parent_name, phone,
student_name, tariff_code, total, is_target, paid, consent, manager,
meeting_start, review_start, next_task_due, closed_at, created_at`. `next_task_due` — срок
ближайшей открытой задачи; `null` = «Нет задач», в прошлом — просрочено.
`source_id` — источник лида из справочника, `source` — его название. В карточке `stage_at` — когда сделка пришла на текущий этап.

## 5. Новый лид и дубли

```jsonc
POST /deals
{"parent": {"full_name": "Асель", "phone": "8 701 123 45 67"},
 "student": {"full_name": "Камила"}, "source_id": "…", "first_message": "…"}
```

Телефон нормализуется в `+7XXXXXXXXXX`. Если клиент с таким телефоном уже
есть → **409 `parent_exists`** с `parent_id` и `open_deal_id` в теле: UI
предлагает открыть его сделку или создать новую сделку этому клиенту —
`POST /deals {"parent_id": "…"}`.

**Принять заявку.** Менеджер берёт её себе (`POST /accept` без тела). Владелец
не менеджер: он обязан назвать, кому отдаёт, `{"manager_id"}` — активного
менеджера или РОП; без него `422 manager_required`, с неактивным —
`422 manager_not_found`. РОП берёт себе или отдаёт другому.

### 5.1. Источники

Источник выбирают из справочника (`meta.sources`, только `active`), а не пишут
текстом — иначе аналитика по источникам расползается на опечатки. Владелец
добавляет, переименовывает и архивирует их; удалить нельзя — архивный источник
остаётся у сделок, где он стоит. Дубль без учёта регистра — `409 source_exists`,
архивный или неизвестный в сделке — `422 source_not_found`.

## 6. Тариф, скидка, оплата

- `PATCH {"tariff_code": "testing"}` — цена копируется из прайса и дальше не
  меняется (ТЗ §3.7). `total = price − discount`.
- `PATCH {"discount": 5000}` — без лимита, пишется в журнал.
- `POST /payment {"amount": 40000, "method": "cash"|"transfer", "paid_at"?}` —
  нужны целевой лид и тариф; сделка переходит на `paid`. Повторная отметка,
  правка скидки/тарифа после оплаты и `DELETE /payment` — только РОП/владелец
  (`payment_change_forbidden`, `deal_paid_locked`). Отменить оплату, если
  клиент уже записан, нельзя (`payment_cancel_blocked`).

### 6.1. Прайс (ТЗ §3.7)

Тариф в `/meta`: `{code, name, price, description, psychologist_review, active}`.

`psychologist_review` — «Консультация и проверка отчёта психологом»: менеджер
записывает первый созвон (всегда 30 минут), второй — 60 минут, разбор
отчёта — назначает сам специалист (§13), и отчёт ждёт его проверки. `false` —
созвонов нет: записать сделку нельзя (`409 deal_no_meeting`), отчёт
публикуется сразу после теста. Как и цена, копируется в сделку при
выборе тарифа (`DealDetail.psychologist_review`, `null` — тарифа нет) и потом
не меняется. Сразу публикуется только отчёт ученика, привязанного к
оплаченной, не проигранной сделке с `false` (и ни к одной с `true`); без сделки,
без оплаты или если отчёт неполный — на проверку, как раньше. Публикация
сразу ставит «Отчёт опубликован» и «Успешно» (§13).
`/meta` отдаёт и архивные (`active: false`) — чтобы сделки с ними показывали
название; выбрать архивный тариф в сделке нельзя (`tariff_not_found`).

- `POST /tariffs {"name", "price", "description"?, "psychologist_review"?: true}` →
  201, `TariffItem`. Код тарифа выдаёт сервер.
- `PATCH /tariffs/{code}` — любые из `name`, `price`, `description` (`null` —
  очистить), `psychologist_review`, `active` (`false` — в архив). → `TariffItem`.

Только владелец (403 остальным). Удаления нет: на тариф ссылаются сделки.
Новая цена действует для сделок, где тариф выберут после изменения; в уже
выбранных цена не пересчитывается. Создание и изменения пишутся в журнал
(`crm.tariff_created`, `crm.tariff_changed`).

## 7. Закрытие

`POST /close {"result": "lost", "reason": "no_answer", "comment"?}` — причина
обязательна (`close_reason_required`); после оплаты — только РОП/владелец.
`{"result": "won"}` — только РОП/владелец, только оплаченная и только на этапе
«Отчёт опубликован» (`deal_win_forbidden`, `deal_not_paid`, `deal_win_too_early`):
обычно «Успешно» ставит публикация отчёта, вручную — если платформа не смогла. Закрытые уходят с доски
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

## 9. Поиск и фильтры (`GET /deals`)

Все параметры необязательны и складываются через «и»:

| Параметр | Значение |
|---|---|
| `q` | часть ФИО родителя или ученика, либо от 4 цифр телефона. Маркетологу не применяется |
| `stage` | этап |
| `tariff` | код тарифа |
| `manager` | id ответственного или `none` — без ответственного |
| `source_id` | источник |
| `paid` | `true` / `false` |
| `created_from`, `created_to` | дата создания (по Алматы), включительно |

Сохранённые фильтры хранит фронт.

## 10. Встречи и окно визита (ТЗ §3.9, §4.5)

`GET /meetings?from=YYYY-MM-DD&to=YYYY-MM-DD` (не длиннее 42 дней) — встречи
без отменённых: `id, deal_id, type, status, start, end, student_name,
parent_name, specialist, mine`. Менеджер видит все встречи, но чужие — как
«Занято»: `deal_id`, `student_name`, `parent_name` = `null`, `mine=false`, открыть
их нельзя (404); специалиста не видит никогда. РОП и владелец — все и с именем
специалиста.

`GET /meetings/{id}` (`MeetingDetail`) — то же плюс `handoff` (карточка
передачи), `cancel_reason`, `rescheduled_from_id` и `history` — журнал этой
встречи и тех, с которых её перенесли: `at, actor, actor_role, action
(meeting.status_changed | meeting.cancelled | meeting.rescheduled), before,
after, reason`.

Статусы: `pending` → `confirmed` (кто видит встречу) → `done` / `no_show`
(владелец или сам специалист и только после начала — иначе
`409 meeting_not_started`). Отмена и перенос — только владелец, только до
начала (`409 meeting_started`), причина 3–1000 символов. При отмене время
снова свободно. Перенос отменяет встречу и создаёт новую с той же карточкой
передачи: тот же специалист, если он свободен в новое время, иначе по общему
правилу; ответ — **новая** встреча. Время занято → `409 slot_taken`, старая
встреча остаётся как была.

Менеджер не переносит сам: `POST /meetings/{id}/reschedule-request`
`{"comment": "…"}` ставит задачу `reschedule` владельцу (самому раннему
активному) со ссылкой на сделку; срок — через 2 часа, но не позже начала созвона.

Специалист в Profy отмечает статус своей встречи:
`POST /api/v1/scheduling/specialists/me/meetings/{id}/status` с тем же телом.

### 10.1. Перенос и отмена

До начала созвона и всегда с причиной. Владелец и РОП — любой созвон;
менеджер — первый созвон своей сделки; специалист в Profile — свои созвоны
(`POST /api/v1/scheduling/specialists/me/meetings/{id}/reschedule|cancel`).
`MeetingDetail.can_move` — может ли текущий пользователь сделать это сейчас,
`call` — `first` / `second`.

Первый созвон, перенесённый из CRM, бронируется как новый: тот же специалист,
если свободен, иначе по общему правилу. Второй созвон и любой перенос
специалистом остаются у специалиста — любое время без наложений на его
созвоны. Новое время занято (`409 slot_taken`) — созвон остаётся как был.
Отмена первого созвона снимает со сделки специалиста до новой записи; отмена
второго — нет.

## 11. Задачи (ТЗ §3.11)

`TaskOut`: `id, deal_id, deal_title («Родитель · ученик»), type (call |
message | meeting | payment_check | reschedule | other), text, due_at,
done_at, result, assignee, created_by, created_at`.

`POST /tasks` `{deal_id?, type, text, due_at, assignee_id?}`. Без
`assignee_id` — себе. Менеджер ставит задачи только себе (`403
task_assign_forbidden`) и только по своим сделкам; РОП и владелец — любому из
продаж. Менеджер видит только свои задачи (`scope` игнорируется), РОП и
владелец — `scope=all`. Выполненную задачу не меняют и не выполняют повторно
(`409 task_already_done`). Напоминаний и автозадач пока нет.

## 12. Клиенты (`GET /clients?q=`)

`ClientRow`: `id, full_name, phone, city, students (имена детей), deals,
open_deal_id (открытая сделка или последняя), meetings_done, meetings_total
(без отменённых), no_shows, paid_total`. `q` — часть ФИО или от 4 цифр
телефона. Менеджер видит клиентов своих сделок и «Неразобранного», до 500 строк.

## 13. Аккаунт ученика и этапы 7–10 (ТЗ §3.3, §4.4)

`student_account` в карточке: `linked`, `email` аккаунта Profile,
`invite_url` — открытая одноразовая ссылка (`null`, если её нет или ею уже
воспользовались), `invite_created_at`.

`POST /deals/{id}/invite` — только оплаченная (`409 deal_not_paid`) и не
закрытая сделка; при тарифе с консультацией психолога — только после записи
на созвон (`409 deal_not_booked`): ссылка несёт специалиста этого созвона. Каждый вызов делает новую ссылку, прежняя перестаёт работать.
Ссылка ведёт в Profile на `/student-invite#token=…`: ученик регистрируется или
входит, и Profile вызывает `POST /api/v1/student-invites/accept {"token"}`
(только аккаунт ученика — иначе `409 student_invite_students_only`; чужая,
отозванная или использованная ссылка — `404 student_invite_invalid`).

`POST /deals/{id}/student {"email"}` — РОП и владелец привязывают уже
существующий аккаунт ученика (`403 student_link_forbidden`,
`404 student_account_not_found`).

После привязки:
- специалист записанного созвона получает ученика в Profile (список, отчёты, очередь проверки);
- тест пройден → `diagnostics_done`; отчёт опубликован → `report_published` и `result: won`;
- этапы двигаются только вперёд, считаются тесты, пройденные после создания сделки;
- неоплаченная сделка не двигается, ответственному ставится одна задача `payment_check`;
- при привязке уже пройденный тест и опубликованный отчёт учитываются сразу.

**Второй созвон** (тариф с консультацией психолога) назначает сам специалист в
Profile, после начала первого, на любое время без наложений, 60 минут —
`GET/POST /api/v1/psychologist/students/{student_id}/second-meeting`
(`{"start"}` → `{first, second, can_schedule, blocker}`; `blocker`:
`no_consultation`, `first_not_booked`, `first_not_started`, `already_scheduled`;
ошибки `second_meeting_<blocker>`, `slot_taken`, `slot_in_past`,
`slot_misaligned`). Время занимается в расписании специалиста — CRM его больше
не предлагает. В ленте сделки — `booked` с `data.second: true`.

**Порядок шагов** при тарифе с консультацией (у тарифа без неё ограничений нет):
- тест открывается ученику с начала первого созвона: `GET /api/v1/assessment/availability`
  → `{open, opens_at}` (`opens_at` — начало первого созвона, `null` — ещё не записан);
  `POST /assessment/start` раньше — `409 test_after_first_call` (`opens_at` в ответе);
- отчёт психолог публикует с начала второго созвона: без него —
  `409 publish_second_call_missing`, до начала — `409 publish_second_call_not_started`
  (`second_call_start` в ответе). Править отчёт можно и раньше.

Второй созвон отмечен «Проведена» у специалиста → `review_done`; публикация
отчёта после разбора → `report_published` и `«Успешно»`. Тариф без созвонов
идёт с `diagnostics_done` сразу в `report_published`. Назначенный
второй созвон этап не двигает — в доске он `review_start` (начало, иначе `null`).

В карточке `meeting` — первый созвон (его записал менеджер), `meetings` — все
живые созвоны по времени.

**Регистрация только по приглашению** (`REGISTRATION_INVITE_ONLY`, по умолчанию
включено). Новый аккаунт ученика создаётся только с живой ссылкой:
`POST /auth/register` и `POST /auth/google` принимают `student_invite` (токен
из ссылки); без него или с отозванной/использованной ссылкой —
`403 registration_invite_only`. Вход в существующий аккаунт (пароль или
Google) и приглашения сотрудников не меняются. Ссылка считается использованной
после `POST /student-invites/accept`, который Profile вызывает после входа.

## 14. Отключение сотрудника

`POST /staff/{id}/active {"active": false}`. Отключённый не входит и не может
вызвать API (каждый запрос проверяет аккаунт). Специалист сразу пропадает из
свободного времени у менеджеров и из автоназначения; его слоты не удаляются и
вернутся после «Включить». Уже назначенные с ним созвоны остаются —
`upcoming_meetings` в `/staff` показывает, сколько их; владелец переносит или
отменяет их. Владельца отключить нельзя (`403 staff_owner_locked`). Открытые
сделки отключённого менеджера остаются за ним, пока владелец или РОП не сменят
ответственного.

## 15. Дашборд владельца (`GET /dashboard?from=&to=`)

Даты по Алматы, включительно, не больше года (`422 period_invalid`).

```jsonc
{"from": "2026-10-01", "to": "2026-10-31",
 "specialists": [{"id": "…", "name": "Айнура", "is_active": true,
   "free_hours": 12.5, "busy_hours": 6.0,   // открытые в периоде: ещё свободные и занятые созвонами
   "calls_done": 9, "no_shows": 1, "cancelled": 2,  // cancelled — отмены и переносы
   "revenue": 210000}],                     // оплаты в периоде по сделкам специалиста
 "issues": [{"meeting_id": "…", "deal_id": "…", "kind": "rescheduled", // no_show | cancelled | rescheduled
   "type": "intro30", "start": "…", "specialist": "Айнура", "student_name": "Камила",
   "reason": "Клиент попросил", "moved_to": "…"}],
 "payment_to_review": {"count": 4, "median_days": 3.5, "average_days": 4.1, "max_days": 8.0,
   "waiting": 2}}   // по разборам, проведённым в периоде; waiting — оплачены, разбора ещё не было
```

## 16. Выгрузка в Excel (`GET /analytics/export?month=2026-10`)

Когорта месяца, как на странице «Аналитика». Листы: «Воронка» (дошли до этапа,
% от лидов, конверсия с прошлого этапа), «Источники» и «Менеджеры» (лиды,
целевые, оплаты, конверсии, выручка, успешно, не реализовано, итог), «Реклама»
(пока по источникам; креативы — после подключения Meta). Маркетологу — без
листа «Менеджеры». Факт выгрузки пишется в журнал.
