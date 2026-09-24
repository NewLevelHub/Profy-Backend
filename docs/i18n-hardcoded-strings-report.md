# Отчёт об извлечении пользовательских строк в i18n

Дата: 2026-09-24. Стек: FastAPI / Python; существующий каталог `app/i18n/catalog`, функция `key(area, key, locale=...)`. Язык по умолчанию — `ru`, второй язык — `kk`.

Заменена **391 строка в 49 файлах кода**. Добавлено **287 ключей в 6 файлах каталогов**; ещё 2 ключа повторно использованы из существующего `result_v2`. В `app/i18n/catalog/__init__.py` зарегистрированы новые разделы.

## Совместимость и границы изменений

- Исходные значения `RU` сохранены побайтно, включая существующие английские сообщения. Они не переведены на русский заново, чтобы не менять ответы API.
- `error_code`, HTTP-статусы, заголовки и структура JSON не изменены. Машинные маркеры `google_account:` и `email_not_verified:` остались в коде. Старый аргумент `locale="ru"` у вызовов `key(...)` сохранён для совместимости исходников, но при наличии `Accept-Language` выбирается активная локаль запроса.
- Сообщения регистрации и сброса пароля получают казахский перевод; регистрация использует уже переданный параметр `locale`, ответы сброса — локаль запроса.
- Для всех 287 извлечённых ключей добавлены отдельные значения `ru` и `kk`; плейсхолдеры полностью совпадают. Переводы для ошибок, уведомлений, отчёта и CSV заданы явно; для роадмапа и RIASEC добавлены казахские варианты с сохранением динамических параметров.
- Админские тексты и CSV-подписи по-прежнему вызываются в админском контексте, но словари теперь содержат обе локали; переключение происходит через общий `key(...)` без изменения бизнес-логики.
- Не изменены условия, алгоритмы, порядок операторов, имена переменных, сигнатуры, модели БД, запросы SQL, ключи кэша, технические коды, логи, промпты LLM и контент банков/сидов. Внутренние исключения сброса пароля оставлены: роутер перехватывает их и возвращает отдельное сообщение.
- Пользовательские незакоммиченные изменения в других документах и `scripts/seed_test_users.py` не затронуты.

## Проверка

Проверки выполнены в Python 3.11 из образа проекта, с исходниками только для чтения и отдельными временными PostgreSQL/Redis. Рабочая БД и Redis приложения не использовались.

- Целевой набор: **168 passed**.
- Расширенный набор: **861 passed, 13 failed**, включая **17 успешных новых регрессионных проверок**.
- Все **13 сбоев воспроизведены на исходном коде до правок** в том же окружении (контрольный прогон: 13 failed, 1 passed). Регрессий локализации среди них нет; полный набор не является зелёным.
- 10 сбоев в `tests/unit/test_validity_service.py`: фикстура вставляет вопросы с уже занятыми `(instrument, order)` в заполненную сидами БД (`uq_questions_instrument_order`).
- `test_translation_keeps_psychologist_edits_outside_the_narrative` и `test_edit_history_moves_with_the_row_under_review` в `tests/integration/test_review_gate_locales.py`: существующий PATCH получает 422 вместо ожидаемого 200.
- `test_publish_is_irreversible_and_notifies_student` в `tests/integration/test_psychologist_review.py`: мок ожидает вызов письма без `results_url`, тогда как текущая реализация передаёт этот параметр. Вызов письма не менялся.

Расширенный набор включал весь `tests/unit`, `tests/guard` и интеграционные модули `test_error_locale`, `test_email_locale`, `test_user_locale`, `test_result_locale`, `test_review_gate_locales`, `test_content_locale`, `test_admin_content_validation`, `test_admin_user_provisioning`, `test_google_oauth_account_linking`, `test_profile_endpoints`, `test_goal_rules`, `test_astur_subtest_submit`, `test_belbin_submit`, `test_psychologist_review`.

AST всех 49 изменённых исходников сравнен с копией до правок: после обратной подстановки строк и f-шаблонов из `RU` и удаления добавленного импорта деревья совпадают полностью. Проверены значения всех 391 замен. Все Python-файлы `app/` компилируются; `git diff --check` проходит.

Регрессионные тесты добавлены в `tests/unit/test_extracted_i18n.py`: параметры шаблонов, локаль HTTP-запроса и регистрации, одинаковый ответ для существующего/несуществующего аккаунта, стабильность вложенных ошибок, динамические параметры валидации и метаданные задач роадмапа.

## Файлы локализации и добавленные ключи

### `app/i18n/catalog/admin_export.py` — 53 ключа

`account_active`, `age_group`, `age_group_junior`, `age_group_middle`, `age_group_senior`, `answer_score`, `answer_words`, `answered_at`, `answered_questions`, `assessment_count`, `city`, `completed_at`, `email_verified`, `goal`, `goal_explore`, `goal_profession`, `goal_university`, `goal_unsure`, `grade`, `has_profile`, `has_roadmap`, `instrument`, `instrument_mi`, `interest_instrument`, `last_active_at`, `latest_goal`, `latest_status`, `least_category`, `least_selected`, `metric`, `most_category`, `most_selected`, `name`, `no`, `question`, `question_number`, `registered_at`, `role`, `role_admin`, `role_psychologist`, `role_student`, `scale`, `scale_code`, `started_at`, `status`, `status_completed`, `status_in_progress`, `total_questions`, `triplet_number`, `unselected`, `unselected_category`, `value`, `yes`.

### `app/i18n/catalog/api_errors.py` — 94 ключа

`access_denied`, `admin_access_required`, `admission_goal_not_allowed_for_middle`, `ai_unavailable`, `allocation_items_mismatch`, `allocation_negative_values`, `allocation_total_mismatch`, `assessment_is_not_completed_yet`, `assessment_not_completed`, `assessment_not_found`, `assessment_results_unavailable`, `assignment_already_exists`, `assignment_not_found`, `astur_item_keys_mismatch`, `astur_subtest_not_found`, `certificate_score_out_of_range`, `credentials_not_validated`, `direction_inquiry_not_completed`, `direction_not_found`, `direction_not_in_results`, `duplicate_triplet_category`, `elapsed_ms_lability_only`, `email_already_exists`, `email_already_verified`, `empty_personality_note`, `export_too_large`, `feature_requires_age_10`, `field_cannot_be_null`, `field_not_locked`, `field_not_overridden`, `field_requires_locale`, `gap_analysis_report_required`, `gap_analysis_senior_only`, `goal_change_limit_reached`, `goal_not_allowed_for_junior`, `google_email_not_verified`, `google_token_missing_email_claim`, `inquiry_answer_count_mismatch`, `inquiry_answer_invalid`, `inquiry_questions_not_generated`, `insufficient_role`, `invalid_admin_sort_field`, `invalid_credentials`, `invalid_google_token`, `invalid_or_expired_code`, `invalid_psychologist_role`, `invalid_sort_field`, `invalid_student_role`, `invalid_verification_code`, `lability_elapsed_ms_required`, `localized_fields_require_locale`, `most_and_least_must_differ`, `motivation_pair_not_found`, `motivation_statement_not_found`, `no_active_assessment_found`, `no_active_verification_code`, `note_not_found`, `null_fields`, `pair_not_found`, `password_digit_required`, `password_letter_required`, `profile_already_exists_for_this_user`, `profile_not_found`, `program_direction_mismatch`, `program_does_not_belong_to_this_direction`, `program_has_no_direction`, `program_not_found`, `psychologist_not_found`, `question_id_not_found`, `question_not_found`, `question_not_in_pair`, `question_pair_not_found`, `question_type_required`, `rate_limit_exceeded`, `report_locale_not_generated`, `report_not_found`, `report_pending_review`, `result_is_already_published`, `result_not_found`, `roadmap_not_found`, `run_not_found_or_already_finished`, `statement_does_not_belong_to_this_triplet`, `student_access_required`, `student_not_found`, `student_registration_required`, `university_not_found`, `unknown_pair`, `unknown_personality_traits`, `unknown_result_codes`, `unknown_triplet`, `unsupported_locale`, `user_not_found`, `verification_code_expired`, `verification_resend_too_soon`.

### `app/i18n/catalog/api_messages.py` — 3 ключа

`password_reset_completed`, `password_reset_requested`, `verification_code_sent`.

### `app/i18n/catalog/report_copy.py` — 7 ключей

`belbin_methodological_note`, `closing_bridge_fallback`, `deleted_question`, `interest_map_note_fallback`, `personality_note_fallback`, `student_fallback_name`, `unnamed_student`.

### `app/i18n/catalog/riasec_explanations.py` — 39 ключей

`a_high_follows`, `a_high_means`, `a_low_follows`, `a_low_means`, `a_medium_follows`, `a_medium_means`, `c_high_follows`, `c_high_means`, `c_low_follows`, `c_low_means`, `c_medium_follows`, `c_medium_means`, `combination_high`, `combination_low`, `combination_medium`, `e_high_follows`, `e_high_means`, `e_low_follows`, `e_low_means`, `e_medium_follows`, `e_medium_means`, `i_high_follows`, `i_high_means`, `i_low_follows`, `i_low_means`, `i_medium_follows`, `i_medium_means`, `r_high_follows`, `r_high_means`, `r_low_follows`, `r_low_means`, `r_medium_follows`, `r_medium_means`, `s_high_follows`, `s_high_means`, `s_low_follows`, `s_low_means`, `s_medium_follows`, `s_medium_means`.

### `app/i18n/catalog/roadmap.py` — 91 ключ

`explore_ask_about_next_level`, `explore_collect_feedback`, `explore_compare_impressions`, `explore_create_original_work`, `explore_direction_benefit`, `explore_direction_why`, `explore_discuss_impressions`, `explore_discuss_next_year`, `explore_discuss_plans`, `explore_fallback_benefit`, `explore_fallback_why`, `explore_find_community`, `explore_find_mentor`, `explore_find_regular_activity`, `explore_focus`, `explore_learn_direction`, `explore_learning_paths`, `explore_list_skills`, `explore_month_1_outcome`, `explore_month_1_title`, `explore_months_3_outcome`, `explore_months_3_title`, `explore_months_6_outcome`, `explore_months_6_title`, `explore_note_difficulties`, `explore_plan_next_year`, `explore_plan_own_attempt`, `explore_practice_regularly`, `explore_present_work`, `explore_try_another_format`, `explore_until_goal_outcome`, `explore_until_goal_title`, `explore_write_goals`, `explore_year_1_outcome`, `explore_year_1_title`, `fallback_basic_skills`, `fallback_direction`, `fallback_interest_area`, `fallback_key_skills`, `profession_career_counselling`, `profession_career_goals`, `profession_choose_careers`, `profession_day_in_life`, `profession_expand_portfolio`, `profession_find_internship`, `profession_find_mentor`, `profession_find_practice`, `profession_first_job`, `profession_first_portfolio`, `profession_first_project`, `profession_focus`, `profession_list_skills`, `profession_month_1_outcome`, `profession_month_1_title`, `profession_months_3_outcome`, `profession_months_3_title`, `profession_months_6_outcome`, `profession_months_6_title`, `profession_online_course`, `profession_study_basics`, `profession_training_program`, `profession_until_goal_title`, `profession_year_1_title`, `university_accept_offer`, `university_admission_documents`, `university_backup_choices`, `university_close_requirement`, `university_collect_documents`, `university_continue_requirement`, `university_deadline_reminders`, `university_entrance_tests`, `university_exam_courses`, `university_find_deadlines`, `university_focus`, `university_list_documents`, `university_month_1_outcome`, `university_month_1_title`, `university_months_3_outcome`, `university_months_3_title`, `university_months_6_outcome`, `university_months_6_title`, `university_prepare_exams`, `university_scholarships`, `university_start_portfolio`, `university_study_requirements`, `university_submit_application`, `university_until_goal_outcome`, `university_until_goal_title`, `university_write_essay`, `university_year_1_outcome`, `university_year_1_title`.

Повторно использованы без изменения каталога: `result_v2.disclaimer`, `result_v2.exploration_note`. Файл регистрации разделов: `app/i18n/catalog/__init__.py`.

## Изменённые файлы кода и заменённые строки

Номера указаны как «до → после». Динамические значения в `{скобках}` передаются в `.format(...)` из прежних выражений. Полные ключи записаны как `раздел.ключ`.

### `app/dependencies.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 45 → 46 | `api_errors.credentials_not_validated` | Could not validate credentials |
| 119 → 120 | `api_errors.admin_access_required` | Admin access required |
| 134 → 135 | `api_errors.student_access_required` | Student access required |
| 144 → 145 | `api_errors.insufficient_role` | Insufficient role |

### `app/routers/admin.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 266 → 267 | `api_errors.user_not_found` | User not found |
| 278 → 279 | `api_errors.assessment_not_found` | Assessment not found |
| 290 → 291 | `api_errors.assessment_not_found` | Assessment not found |
| 410 → 411 | `api_errors.university_not_found` | University not found |
| 436 → 437 | `api_errors.program_not_found` | Program not found |
| 489 → 490 | `api_errors.question_not_found` | Question not found |
| 544 → 545 | `api_errors.question_pair_not_found` | Question pair not found |
| 602 → 603 | `api_errors.motivation_statement_not_found` | Motivation statement not found |
| 657 → 658 | `api_errors.motivation_pair_not_found` | Motivation pair not found |
| 711 → 712 | `api_errors.direction_not_found` | Direction not found |

### `app/routers/artifacts.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 17 → 18 | `api_errors.profile_not_found` | Profile not found |

### `app/routers/assessment.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 22 → 23 | `api_errors.profile_not_found` | Profile not found |
| 44 → 45 | `api_errors.no_active_assessment_found` | No active assessment found |

### `app/routers/astur.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 47 → 48 | `api_errors.assessment_not_found` | Assessment not found |
| 51 → 52 | `api_errors.access_denied` | Access denied |

### `app/routers/auth.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 61 → 62 | `api_errors.rate_limit_exceeded` | Too many requests. Please try again later. |
| 125 → 126 | `api_errors.verification_resend_too_soon` | Please wait 60 seconds before requesting a new code |
| 174 → 175 | `api_messages.password_reset_requested` | If an account exists, a reset code has been sent. |
| 185 → 186 | `api_errors.invalid_or_expired_code` | Invalid or expired code |
| 197 → 198 | `api_errors.invalid_or_expired_code` | Invalid or expired code |
| 198 → 199 | `api_messages.password_reset_completed` | Password has been reset successfully. |

### `app/routers/belbin.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 60 → 61 | `api_errors.assessment_not_found` | Assessment not found |
| 64 → 65 | `api_errors.access_denied` | Access denied |

### `app/routers/certificates.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 17 → 18 | `api_errors.profile_not_found` | Profile not found |

### `app/routers/direction_inquiry.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 32 → 33 | `api_errors.assessment_not_found` | Assessment not found |
| 35 → 36 | `api_errors.access_denied` | Access denied |

### `app/routers/directions.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 21 → 22 | `api_errors.direction_not_found` | Direction not found |

### `app/routers/extended_blocks.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 40 → 42 | `api_errors.assessment_not_found` | Assessment not found |
| 42 → 44 | `api_errors.access_denied` | Access denied |

### `app/routers/motivation.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 28 → 29 | `api_errors.profile_not_found` | Profile not found |
| 45 → 46 | `api_errors.assessment_not_found` | Assessment not found |
| 49 → 50 | `api_errors.access_denied` | Access denied |

### `app/routers/motivation_pairs.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 26 → 27 | `api_errors.profile_not_found` | Profile not found |
| 43 → 44 | `api_errors.assessment_not_found` | Assessment not found |
| 47 → 48 | `api_errors.access_denied` | Access denied |

### `app/routers/profile.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 90 → 91 | `api_errors.profile_not_found` | Profile not found |

### `app/routers/psychoemotional.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 35 → 36 | `api_errors.assessment_not_found` | Assessment not found |
| 39 → 40 | `api_errors.access_denied` | Access denied |
| 82 → 83 | `api_errors.run_not_found_or_already_finished` | Run not found or already finished |

### `app/routers/question_pairs.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 26 → 27 | `api_errors.profile_not_found` | Profile not found |
| 43 → 44 | `api_errors.assessment_not_found` | Assessment not found |
| 47 → 48 | `api_errors.access_denied` | Access denied |

### `app/routers/questions.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 31 → 32 | `api_errors.assessment_not_found` | Assessment not found |
| 35 → 36 | `api_errors.access_denied` | Access denied |

### `app/routers/result.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 44 → 45 | `api_errors.assessment_not_found` | Assessment not found |
| 49 → 50 | `api_errors.access_denied` | Access denied |
| 84 → 85 | `api_errors.report_not_found` | Report not found |
| 97 → 98 | `api_errors.report_locale_not_generated` | Отчёт на выбранном языке ещё не создан |
| 100 → 101 | `api_errors.report_not_found` | Report not found |

### `app/routers/roadmap.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 42 → 43 | `api_errors.assessment_not_found` | Assessment not found |
| 45 → 46 | `api_errors.access_denied` | Access denied |
| 77 → 78 | `api_errors.program_not_found` | Program not found |
| 82 → 83 | `api_errors.program_does_not_belong_to_this_direction` | Program does not belong to this direction |
| 113 → 114 | `api_errors.roadmap_not_found` | Roadmap not found |
| 126 → 127 | `api_errors.roadmap_not_found` | Roadmap not found |

### `app/routers/university.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 137 → 138 | `api_errors.profile_not_found` | Profile not found |
| 142 → 143 | `api_errors.gap_analysis_senior_only` | Gap analysis is only available for senior age group |
| 155 → 156 | `api_errors.assessment_not_found` | Assessment not found |
| 160 → 161 | `api_errors.assessment_is_not_completed_yet` | Assessment is not completed yet |
| 187 → 188 | `api_errors.gap_analysis_report_required` | Generate a report for this assessment before running gap analysis |
| 197 → 198 | `api_errors.program_direction_mismatch` | This program's direction does not match your assessment results |

### `app/schemas/admin.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 126 → 127 | `api_errors.student_registration_required` | Use /auth/register to create student accounts |

### `app/schemas/auth.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 18 → 19 | `api_errors.password_letter_required` | Password must contain at least one letter |
| 20 → 21 | `api_errors.password_digit_required` | Password must contain at least one digit |
| 97 → 98 | `api_errors.unsupported_locale` | locale must be one of {locales} |

### `app/schemas/certificate.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 24 → 25 | `api_errors.certificate_score_out_of_range` | score for {type} must be between {low} and {high} |

### `app/schemas/psychologist_result.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 104 → 106 | `api_errors.null_fields` | fields cannot be null: {fields} |

### `app/schemas/result_v2.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 33 → 36 | `result_v2.disclaimer` | Это не окончательный выбор, а карта возможных направлений — со временем картина может измениться, и это нормально. |
| 47 → 49 | `result_v2.exploration_note` | Не обязательно пробовать всё сразу — начни с того, что откликается больше всего. Даже маленький шаг сегодня помогает лучше понять, что тебе действительно нравится. |
| 59 → 59 | `report_copy.interest_map_note_fallback` | Карта показывает, какие сферы проявляются ярче, а какие — тише. Это не оценка, а просто снимок текущего состояния. |
| 66 → 65 | `report_copy.closing_bridge_fallback` | Каждый раздел этого отчёта — отдельный кусочек общей картины: не разрозненные факты, а разные стороны одного и того же человека. Используй их вместе, а не по одному, когда будешь решать, что попробовать дальше. |
| 77 → 73 | `report_copy.personality_note_fallback` | Каждая черта характера проявляется по-своему — вместе они складываются в общую картину того, как тебе комфортнее действовать и общаться. |

### `app/services/admin_content_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 75 → 76 | `api_errors.localized_fields_require_locale` | locale is required when editing a localized field: {fields} |
| 98 → 98 | `api_errors.field_not_overridden` | Field '{field}' is not overridden on this row |
| 124 → 124 | `api_errors.question_type_required` | {type_field} cannot be null on a {instrument} question — scoring groups responses by this field for every student. |
| 274 → 273 | `api_errors.question_not_found` | Question not found |
| 282 → 281 | `api_errors.question_not_found` | Question not found |
| 418 → 417 | `api_errors.question_pair_not_found` | Question pair not found |
| 428 → 427 | `api_errors.question_pair_not_found` | Question pair not found |
| 536 → 535 | `api_errors.duplicate_triplet_category` | Category '{new_category}' is already used by statement #{order} in triplet {triplet_index} — the three statements of a triplet must carry three different categories, or scoring cannot tell the picked motives apart. |
| 548 → 544 | `api_errors.motivation_statement_not_found` | Motivation statement not found |
| 554 → 550 | `api_errors.motivation_statement_not_found` | Motivation statement not found |
| 563 → 559 | `api_errors.motivation_statement_not_found` | Motivation statement not found |
| 645 → 641 | `api_errors.motivation_pair_not_found` | Motivation pair not found |
| 654 → 650 | `api_errors.motivation_pair_not_found` | Motivation pair not found |
| 814 → 810 | `api_errors.direction_not_found` | Direction not found |
| 824 → 820 | `api_errors.direction_not_found` | Direction not found |

### `app/services/admin_export_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 35 → 37 | `admin_export.yes` | да |
| 35 → 37 | `admin_export.no` | нет |
| 42 → 44 | `admin_export.age_group_junior` | 5–7 класс |
| 43 → 45 | `admin_export.age_group_middle` | 8–9 класс |
| 44 → 46 | `admin_export.age_group_senior` | 10–11 класс |
| 47 → 49 | `admin_export.goal_explore` | Исследовать |
| 48 → 50 | `admin_export.goal_profession` | Выбрать профессию |
| 49 → 51 | `admin_export.goal_university` | Поступить в вуз |
| 50 → 52 | `admin_export.goal_unsure` | Не уверен |
| 53 → 55 | `admin_export.status_in_progress` | В процессе |
| 54 → 56 | `admin_export.status_completed` | Завершён |
| 57 → 59 | `admin_export.role_student` | Ученик |
| 58 → 60 | `admin_export.role_admin` | Администратор |
| 59 → 61 | `admin_export.role_psychologist` | Психолог |
| 64 → 66 | `admin_export.instrument_mi` | Множественный интеллект |
| 97 → 99 | `admin_export.email_verified` | Почта подтверждена |
| 98 → 100 | `admin_export.account_active` | Аккаунт активен |
| 99 → 101 | `admin_export.role` | Роль |
| 100 → 102 | `admin_export.role_admin` | Администратор |
| 101 → 103 | `admin_export.registered_at` | Регистрация |
| 102 → 104 | `admin_export.last_active_at` | Последняя активность |
| 103 → 105 | `admin_export.has_profile` | Есть профиль |
| 104 → 106 | `admin_export.name` | Имя |
| 105 → 107 | `admin_export.age_group` | Класс (группа) |
| 106 → 108 | `admin_export.grade` | Класс |
| 107 → 109 | `admin_export.city` | Город |
| 108 → 110 | `admin_export.assessment_count` | Тестирований |
| 109 → 111 | `admin_export.latest_status` | Статус последнего |
| 110 → 112 | `admin_export.latest_goal` | Цель последнего |
| 111 → 113 | `admin_export.interest_instrument` | Инструмент интересов |
| 206 → 208 | `admin_export.metric` | Показатель |
| 206 → 208 | `admin_export.value` | Значение |
| 208 → 210 | `admin_export.name` | Имя |
| 209 → 211 | `admin_export.goal` | Цель |
| 210 → 212 | `admin_export.status` | Статус |
| 211 → 213 | `admin_export.started_at` | Начато |
| 212 → 214 | `admin_export.completed_at` | Завершено |
| 213 → 215 | `admin_export.answered_questions` | Отвечено вопросов |
| 214 → 216 | `admin_export.total_questions` | Всего вопросов |
| 215 → 217 | `admin_export.has_roadmap` | Есть роадмап |
| 242 → 244 | `admin_export.question_number` | № вопроса |
| 243 → 245 | `admin_export.instrument` | Инструмент |
| 244 → 246 | `admin_export.scale_code` | Код шкалы |
| 245 → 247 | `admin_export.scale` | Шкала |
| 246 → 248 | `admin_export.question` | Вопрос |
| 247 → 249 | `admin_export.answer_score` | Ответ (1-5) |
| 248 → 250 | `admin_export.answer_words` | Ответ словами |
| 249 → 251 | `admin_export.answered_at` | Время ответа |
| 278 → 280 | `admin_export.triplet_number` | № триплета |
| 279 → 281 | `admin_export.most_selected` | Выбрано как важное |
| 280 → 282 | `admin_export.most_category` | Категория важного |
| 281 → 283 | `admin_export.least_selected` | Выбрано как неважное |
| 282 → 284 | `admin_export.least_category` | Категория неважного |
| 283 → 285 | `admin_export.unselected` | Не выбрано |
| 284 → 286 | `admin_export.unselected_category` | Категория невыбранного |

### `app/services/admin_listing.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 57 → 60 | `api_errors.invalid_admin_sort_field` | Unknown sort field '{field}'. Sortable fields: {allowed_fields}. |

### `app/services/admin_lock.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 109 → 111 | `api_errors.field_requires_locale` | locale is required to edit {key} |
| 111 → 113 | `api_errors.field_cannot_be_null` | {key} cannot be null |
| 137 → 139 | `api_errors.field_cannot_be_null` | {key} cannot be null |

### `app/services/admin_psychologist_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 32 → 34 | `api_errors.psychologist_not_found` | Psychologist not found |
| 34 → 36 | `api_errors.invalid_psychologist_role` | psychologist_id must refer to a user with role=psychologist |
| 38 → 40 | `api_errors.student_not_found` | Student not found |
| 40 → 42 | `api_errors.invalid_student_role` | student_id must refer to a user with role=student |
| 49 → 51 | `api_errors.assignment_already_exists` | Assignment already exists |
| 122 → 124 | `api_errors.assignment_not_found` | Assignment not found |

### `app/services/admin_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 226 → 227 | `api_errors.export_too_large` | Export matches {total} users, exceeding the {export_max_rows}-row limit — narrow the search/age_group/status/goal filters first. |
| 424 → 424 | `api_errors.email_already_exists` | Email already exists |
| 483 → 483 | `report_copy.deleted_question` | Вопрос удалён |

### `app/services/admin_university_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 143 → 144 | `api_errors.university_not_found` | University not found |
| 168 → 169 | `api_errors.program_not_found` | Program not found |
| 190 → 191 | `api_errors.field_not_locked` | Field '{field}' is not locked on this row |
| 203 → 204 | `api_errors.university_not_found` | University not found |
| 215 → 216 | `api_errors.program_not_found` | Program not found |

### `app/services/assessment_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 65 → 66 | `api_errors.profile_not_found` | Profile not found |
| 137 → 138 | `api_errors.assessment_not_found` | Assessment not found |
| 140 → 141 | `api_errors.access_denied` | Access denied |
| 151 → 152 | `api_errors.question_id_not_found` | Question {question_id} not found |
| 221 → 222 | `api_errors.assessment_not_found` | Assessment not found |
| 224 → 225 | `api_errors.access_denied` | Access denied |
| 233 → 234 | `api_errors.goal_not_allowed_for_junior` | Для младшей возрастной группы доступна только цель 'исследовать себя' |
| 248 → 249 | `api_errors.admission_goal_not_allowed_for_middle` | Для учеников 5-8 классов поступление пока недоступно как цель |
| 258 → 259 | `api_errors.goal_change_limit_reached` | Достигнут лимит смены целей (максимум 3 раза) |

### `app/services/astur_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 107 → 109 | `api_errors.astur_subtest_not_found` | No such АСТУР subtest: {n} |
| 119 → 121 | `api_errors.astur_item_keys_mismatch` | {field_name} does not cover exactly this subtest's items |
| 203 → 205 | `api_errors.lability_elapsed_ms_required` | elapsed_ms is required for the lability subtest |
| 209 → 211 | `api_errors.elapsed_ms_lability_only` | elapsed_ms is only accepted for the lability subtest |

### `app/services/auth_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 65 → 66 | `api_errors.email_already_exists` | Email already exists |
| 84 → 85 | `api_messages.verification_code_sent` | Код отправлен на почту |
| 92 → 93 | `api_errors.invalid_credentials` | Invalid credentials |
| 98 → 99 | `api_errors.invalid_credentials` | Invalid credentials |
| 110 → 111 | `api_errors.user_not_found` | User not found |
| 124 → 125 | `api_errors.no_active_verification_code` | No active verification code |
| 132 → 133 | `api_errors.verification_code_expired` | Verification code expired |
| 135 → 136 | `api_errors.invalid_verification_code` | Invalid verification code |
| 149 → 150 | `api_errors.user_not_found` | User not found |
| 151 → 152 | `api_errors.email_already_verified` | Email already verified |

### `app/services/direction_inquiry_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 37 → 39 | `api_errors.ai_unavailable` | ИИ временно недоступен, попробуй ещё раз |
| 57 → 59 | `api_errors.assessment_not_found` | Assessment not found |
| 62 → 64 | `api_errors.feature_requires_age_10` | Эта возможность доступна с 10 лет |
| 68 → 70 | `api_errors.direction_not_in_results` | Это направление не входит в твои результаты |
| 72 → 74 | `api_errors.direction_not_found` | Direction not found |
| 122 → 124 | `api_errors.inquiry_questions_not_generated` | Сначала получи вопросы по направлению |
| 130 → 132 | `api_errors.inquiry_answer_count_mismatch` | Число ответов не совпадает с числом вопросов |
| 136 → 138 | `api_errors.inquiry_answer_invalid` | Некорректный ответ |

### `app/services/goal_overlay_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 183 → 184 | `api_errors.assessment_not_found` | Assessment not found |
| 198 → 199 | `api_errors.profile_not_found` | Profile not found |
| 247 → 248 | `api_errors.assessment_results_unavailable` | Не удалось получить результаты диагностики |

### `app/services/ipsative_battery.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 65 → 68 | `api_errors.allocation_items_mismatch` | Allocation does not cover exactly the expected items for this block |
| 75 → 78 | `api_errors.allocation_negative_values` | Allocation values must be >= 0 |
| 83 → 86 | `api_errors.allocation_total_mismatch` | Allocation must sum to exactly {total} points, got {actual_total} |

### `app/services/motivation_pair_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 90 → 92 | `api_errors.assessment_not_found` | Assessment not found |
| 92 → 94 | `api_errors.access_denied` | Access denied |
| 102 → 104 | `api_errors.unknown_pair` | Unknown pair {pair_index} |

### `app/services/motivation_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 91 → 93 | `api_errors.assessment_not_found` | Assessment not found |
| 93 → 95 | `api_errors.access_denied` | Access denied |
| 101 → 103 | `api_errors.unknown_triplet` | Unknown triplet {triplet_index} |
| 107 → 109 | `api_errors.statement_does_not_belong_to_this_triplet` | Statement does not belong to this triplet |
| 111 → 113 | `api_errors.most_and_least_must_differ` | most and least must differ |

### `app/services/new_tests_report_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 48 → 50 | `report_copy.belbin_methodological_note` | Методика Белбина изначально разработана для взрослых сотрудников в корпоративном контексте (18+). Результат школьника стоит трактовать с поправкой на возраст — это не формальное ограничение платформы, а методическая особенность источника. |

### `app/services/oauth_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 41 → 42 | `api_errors.invalid_google_token` | Invalid Google token |
| 44 → 45 | `api_errors.google_email_not_verified` | Google email not verified |
| 47 → 48 | `api_errors.google_token_missing_email_claim` | Google token missing email claim |

### `app/services/profile_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 30 → 31 | `api_errors.profile_already_exists_for_this_user` | Profile already exists for this user |
| 69 → 70 | `api_errors.profile_not_found` | Profile not found |

### `app/services/psychologist_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 126 → 128 | `api_errors.student_not_found` | Student not found |
| 147 → 149 | `api_errors.assessment_not_found` | Assessment not found |
| 159 → 161 | `api_errors.note_not_found` | Note not found |
| 237 → 239 | `api_errors.student_not_found` | Student not found |
| 311 → 313 | `api_errors.student_not_found` | Student not found |
| 337 → 339 | `api_errors.assessment_not_found` | Assessment not found |
| 449 → 451 | `api_errors.report_not_found` | Report not found |
| 464 → 466 | `report_copy.student_fallback_name` | Ученик |
| 617 → 619 | `api_errors.result_not_found` | Result not found |
| 663 → 665 | `api_errors.report_not_found` | Report not found |
| 716 → 718 | `api_errors.result_is_already_published` | Result is already published |
| 728 → 730 | `api_errors.unknown_personality_traits` | personality_notes: неизвестные черты {traits} |
| 731 → 733 | `api_errors.empty_personality_note` | personality_notes: текст не может быть пустым |
| 740 → 742 | `api_errors.unknown_result_codes` | {field}: unknown codes {codes}, allowed {allowed_codes} |
| 848 → 850 | `api_errors.result_not_found` | Result not found |
| 856 → 858 | `api_errors.result_is_already_published` | Result is already published |
| 927 → 929 | `report_copy.unnamed_student` | без имени |

### `app/services/question_pair_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 98 → 100 | `api_errors.assessment_not_found` | Assessment not found |
| 101 → 103 | `api_errors.access_denied` | Access denied |
| 117 → 119 | `api_errors.pair_not_found` | Pair {pair_index} not found |
| 122 → 124 | `api_errors.question_not_in_pair` | Question {picked_question_id} is not part of pair {pair_index} |

### `app/services/report_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 517 → 518 | `api_errors.assessment_not_completed` | Тест ещё не завершён — сначала ответь на все обязательные вопросы |
| 861 → 862 | `api_errors.assessment_not_found` | Assessment not found |
| 1226 → 1227 | `api_errors.report_pending_review` | Отчёт ещё не опубликован психологом |

### `app/services/riasec_explanations.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 19 → 22 | `riasec_explanations.r_high_means` | Тебе нравится, когда результат можно потрогать: собрать, починить, построить, вырастить. Дело становится понятным, когда делаешь его руками, а не читаешь о нём. |
| 21 → 23 | `riasec_explanations.r_high_follows` | Такой интерес держится долго. Он хорошо ложится на профессии, где работают с техникой, материалами, животными или на свежем воздухе — в мастерской, на производстве, в поле. |
| 25 → 26 | `riasec_explanations.r_medium_means` | Практические дела тебе в целом по душе: что-то починить или собрать бывает интересно, но не всякая работа руками увлекает. |
| 27 → 27 | `riasec_explanations.r_medium_follows` | Это не главный интерес, но хорошая опора: практическая сторона пригодится в любой профессии, где нужно довести дело до осязаемого результата. |
| 31 → 30 | `riasec_explanations.r_low_means` | Работа руками, техника и механизмы сейчас мало откликаются — в ответах про это чаще звучало «не нравится». |
| 33 → 31 | `riasec_explanations.r_low_follows` | Профессии, где весь день нужно работать с оборудованием или физически, скорее будут утомлять. Бытовые навыки при этом никуда не деваются — речь только о выборе основного дела. |
| 39 → 36 | `riasec_explanations.i_high_means` | Тебе интересно докапываться до сути: почему так устроено, откуда берётся, как это проверить. Сложные вопросы не пугают, а затягивают. |
| 41 → 37 | `riasec_explanations.i_high_follows` | Это основа для профессий, где нужно исследовать, анализировать и искать закономерности — в науке, медицине, IT, инженерии, аналитике. |
| 45 → 40 | `riasec_explanations.i_medium_means` | Разобраться, как всё устроено, тебе бывает интересно, но не всегда: одни вопросы цепляют, другие — нет. |
| 47 → 41 | `riasec_explanations.i_medium_follows` | Не ведущий интерес, но полезное дополнение: умение разбираться в причинах пригодится там, где нужно искать ошибку или принимать взвешенное решение. |
| 51 → 44 | `riasec_explanations.i_low_means` | Долго разбираться в теории, ставить эксперименты и копаться в отвлечённых вопросах сейчас не хочется. |
| 53 → 45 | `riasec_explanations.i_low_follows` | Профессии, где главное — исследования и научная работа, скорее покажутся скучными. Вероятно, тебе ближе дело, где результат виден сразу. |
| 59 → 50 | `riasec_explanations.a_high_means` | Тебе важно придумывать своё и выражать себя: рисовать, писать, фотографировать, создавать образ. Нравится свобода и возможность сделать не по шаблону. |
| 61 → 51 | `riasec_explanations.a_high_follows` | Подходят профессии, где ценятся вкус и оригинальность — дизайн, медиа, архитектура, сцена, мода. Стоит развивать то, в чём уже есть опыт. |
| 65 → 54 | `riasec_explanations.a_medium_means` | Творческие занятия тебе знакомы и бывают в радость, но не всегда: что-то откликается, что-то оставляет равнодушным. |
| 67 → 55 | `riasec_explanations.a_medium_follows` | Творческая жилка — хорошее дополнение к основной профессии: помогает находить нестандартные решения и красиво оформлять результат. |
| 71 → 58 | `riasec_explanations.a_low_means` | Свободное творчество — сочинять, фантазировать, выражать себя через искусство — сейчас мало откликается. |
| 73 → 59 | `riasec_explanations.a_low_follows` | Творчество может остаться хобби. Выбирать профессию, где оно главное, пока нет оснований — но интересы с возрастом меняются. |
| 79 → 64 | `riasec_explanations.s_high_means` | Тебе важно быть рядом с людьми: помогать, объяснять, поддерживать, работать в команде. Польза для других сама по себе приносит удовольствие. |
| 81 → 65 | `riasec_explanations.s_high_follows` | Подходят профессии, где главный результат — человеку стало лучше: обучение, медицина, психология, социальная работа, сервис. |
| 85 → 68 | `riasec_explanations.s_medium_means` | С людьми тебе в целом комфортно: помочь или поработать в команде — нормально, но это не то, что зажигает больше всего. |
| 87 → 69 | `riasec_explanations.s_medium_follows` | Умение ладить с людьми пригодится почти везде. Но работа, где общение — весь день и главное содержание, может утомлять. |
| 91 → 72 | `riasec_explanations.s_low_means` | Постоянно общаться, опекать и помогать другим сейчас не очень хочется — ближе дела, где можно сосредоточиться на своём. |
| 93 → 73 | `riasec_explanations.s_low_follows` | Профессии, где человек — главный предмет работы (учитель, врач, психолог), скорее будут утомлять. Лучше подойдёт дело с понятной задачей и меньшим числом контактов. |
| 99 → 78 | `riasec_explanations.e_high_means` | Тебе нравится вести за собой: принимать решения, убеждать, запускать проекты и добиваться результата. |
| 101 → 79 | `riasec_explanations.e_high_follows` | Подходят профессии, где нужно руководить, договариваться и отвечать за результат — управление, предпринимательство, продажи, право. |
| 105 → 82 | `riasec_explanations.e_medium_means` | Иногда тебе нравится брать инициативу и влиять на решения, но быть лидером всё время не обязательно. |
| 107 → 83 | `riasec_explanations.e_medium_follows` | Предприимчивость — плюс в любой профессии: пригодится, чтобы продвигать свои идеи и отвечать за небольшие проекты. |
| 111 → 86 | `riasec_explanations.e_low_means` | Убеждать, продавать и быть в центре внимания сейчас не хочется. |
| 112 → 87 | `riasec_explanations.e_low_follows` | Работа, где главное — продажи, переговоры и руководство людьми, скорее будет утомлять. Вероятно, тебе ближе роль специалиста, которого ценят за дело. |
| 118 → 92 | `riasec_explanations.c_high_means` | Тебе спокойно, когда всё разложено по местам: порядок, точность, понятные правила. Ты замечаешь ошибки в деталях и доводишь дело до аккуратного результата. |
| 120 → 93 | `riasec_explanations.c_high_follows` | Это опора для профессий, где работают с документами, данными и процессами — финансы, логистика, делопроизводство, контроль качества. И усилитель любого другого интереса. |
| 124 → 96 | `riasec_explanations.c_medium_means` | Порядок и чёткие правила тебе в целом по душе, но строгий регламент во всём — не обязательно. |
| 126 → 97 | `riasec_explanations.c_medium_follows` | Аккуратность пригодится в любой профессии, но работа, которая целиком состоит из инструкций и отчётов, может показаться скучной. |
| 130 → 100 | `riasec_explanations.c_low_means` | Строгие правила, однообразные процедуры и работа по инструкции сейчас не откликаются. |
| 131 → 101 | `riasec_explanations.c_low_follows` | Профессии, где день состоит из документов, таблиц и регламентов, скорее будут утомлять. Ближе дело, где есть свобода в том, как добиться результата. |
| 142 → 111 | `riasec_explanations.combination_high` | {a} и {b} — соседи на шестиугольнике: эти типы похожи, поэтому профиль цельный, и подходящие направления найти проще. |
| 147 → 115 | `riasec_explanations.combination_medium` | {a} и {b} стоят через угол: у них есть общее, но есть и заметные различия. Подойдут профессии, где нужны обе стороны. |
| 152 → 119 | `riasec_explanations.combination_low` | {a} и {b} — на противоположных углах шестиугольника. Это редкое сочетание: интересы тянут в разные стороны. Не противоречие, а подсказка — стоит искать профессии на стыке этих сфер. |

### `app/services/roadmap_builder.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 122 → 124 | `roadmap.explore_direction_why` | По результатам теста направление «{name}» — один из твоих самых сильных откликов. |
| 123 → 125 | `roadmap.explore_direction_benefit` | Развитие в «{name}» может привести к кружкам и конкурсам следующего уровня, а дальше — к профессиям в этой сфере. |
| 129 → 131 | `roadmap.fallback_interest_area` | интересующей сфере |
| 130 → 132 | `roadmap.explore_fallback_why` | Пока по тесту не выделилось одно явное направление — начни с общей разведки интересов. |
| 131 → 133 | `roadmap.explore_fallback_benefit` | Это поможет нащупать, какая сфера откликается сильнее всего. |
| 147 → 149 | `roadmap.explore_learn_direction` | Узнай подробнее о направлении «{label}»: посмотри видео, статьи или пробное занятие |
| 148 → 150 | `roadmap.explore_compare_impressions` | Сравни впечатления от попробованного и запиши, что понравилось больше всего |
| 149 → 151 | `roadmap.explore_discuss_impressions` | Обсуди с родителями или учителем, что из попробованного откликнулось сильнее |
| 150 → 152 | `roadmap.explore_try_another_format` | Найди ещё один формат по этому же направлению (видео другого автора, другой кружок) и сравни впечатления |
| 154 → 156 | `roadmap.explore_find_regular_activity` | Найди регулярный формат (кружок, секция, курс) по направлению «{label}» и сходи на первое занятие |
| 155 → 157 | `roadmap.explore_create_original_work` | Попробуй сделать что-то своё на основе того, что уже пробовал, а не по инструкции |
| 156 → 158 | `roadmap.explore_ask_about_next_level` | Уточни у руководителя кружка/секции, что нужно для более серьёзных занятий дальше |
| 157 → 159 | `roadmap.explore_plan_own_attempt` | Составь список того, что хочешь попробовать сделать сам(а) в следующий раз |
| 161 → 163 | `roadmap.explore_practice_regularly` | Занимайся направлением «{label}» регулярно (раз в неделю) и сделай небольшой проект руками |
| 162 → 164 | `roadmap.explore_find_mentor` | Найди наставника или ментора в выбранной сфере |
| 163 → 165 | `roadmap.explore_collect_feedback` | Покажи то, что сделал, кому-то ещё (семье, друзьям, руководителю кружка) и собери отклик |
| 164 → 166 | `roadmap.explore_note_difficulties` | Запиши, что даётся легко, а что пока сложно в этом направлении |
| 168 → 170 | `roadmap.explore_present_work` | Прими участие в конкурсе, соревновании или открытом показе по направлению «{label}» |
| 169 → 171 | `roadmap.explore_list_skills` | Составь список навыков, которые хочешь развить дальше в этой сфере |
| 170 → 172 | `roadmap.explore_find_community` | Найди профессиональное сообщество (онлайн или офлайн) по этой сфере |
| 171 → 173 | `roadmap.explore_discuss_next_year` | Обсуди с наставником или родителями цели на следующий год |
| 175 → 177 | `roadmap.explore_write_goals` | Сформулируй свои интересы и цели в этой сфере в письменном виде |
| 176 → 178 | `roadmap.explore_learning_paths` | Исследуй пути дальнейшего обучения и развития по выбранному направлению |
| 177 → 179 | `roadmap.explore_discuss_plans` | Обсуди планы с родителями, учителями или школьным куратором |
| 178 → 180 | `roadmap.explore_plan_next_year` | Составь план на следующий год с конкретными шагами и датами |
| 184 → 186 | `roadmap.explore_month_1_title` | Первые пробы |
| 185 → 187 | `roadmap.explore_month_1_outcome` | Понимание, откликается ли направление «{label}». |
| 190 → 192 | `roadmap.explore_months_3_title` | Регулярный формат |
| 191 → 193 | `roadmap.explore_months_3_outcome` | Первый регулярный формат занятий и самостоятельная попытка. |
| 196 → 198 | `roadmap.explore_months_6_title` | Углубление |
| 197 → 199 | `roadmap.explore_months_6_outcome` | Регулярные занятия и первый самостоятельный проект. |
| 202 → 204 | `roadmap.explore_year_1_title` | Предъявление результата |
| 203 → 205 | `roadmap.explore_year_1_outcome` | Первый публичный результат — участие в конкурсе, соревновании или показе. |
| 208 → 210 | `roadmap.explore_until_goal_title` | Чёткое видение будущего |
| 209 → 211 | `roadmap.explore_until_goal_outcome` | Чёткое представление о сфере и путях дальнейшего обучения. |
| 217 → 219 | `roadmap.fallback_direction` | выбранном направлении |
| 218 → 220 | `roadmap.fallback_key_skills` | ключевым навыкам |
| 219 → 221 | `roadmap.profession_study_basics` | Изучи базовые материалы по направлению |
| 224 → 226 | `roadmap.profession_month_1_title` | Изучить профессии по результатам |
| 225 → 227 | `roadmap.profession_month_1_outcome` | Сформированное понимание ключевых профессий в выбранной сфере. |
| 227 → 229 | `roadmap.profession_choose_careers` | Изучи профессии в сфере «{top_name}» и выбери 1–2 наиболее интересных |
| 228 → 230 | `roadmap.profession_day_in_life` | Посмотри «день из жизни» специалиста в «{top_name}» |
| 229 → 231 | `roadmap.profession_list_skills` | Составь список навыков, необходимых для работы в этой сфере |
| 234 → 236 | `roadmap.profession_months_3_title` | Начать развивать ключевые навыки |
| 235 → 237 | `roadmap.profession_months_3_outcome` | Освоение базовых теоретических и практических навыков. |
| 238 → 240 | `roadmap.profession_online_course` | Пройди онлайн-курс по {skill} |
| 238 → 240 | `roadmap.fallback_basic_skills` | базовым навыкам направления |
| 239 → 241 | `roadmap.profession_find_practice` | Найди учебные задачи или мини-проекты для практики |
| 244 → 246 | `roadmap.profession_months_6_title` | Первый практический опыт |
| 245 → 247 | `roadmap.profession_months_6_outcome` | Создание первого учебного проекта для портфолио. |
| 247 → 249 | `roadmap.profession_first_project` | Сделай первый учебный проект в сфере «{top_name}» |
| 248 → 250 | `roadmap.profession_find_internship` | Ищи возможности для волонтёрства или стажировки по теме |
| 249 → 251 | `roadmap.profession_first_portfolio` | Собери первое портфолио своих работ |
| 254 → 256 | `roadmap.profession_year_1_title` | Профессиональное позиционирование |
| 256 → 258 | `roadmap.profession_expand_portfolio` | Дополни портфолио 2–3 значимыми проектами |
| 257 → 259 | `roadmap.profession_career_goals` | Сформулируй карьерные цели на ближайшие 3–5 лет |
| 258 → 260 | `roadmap.profession_career_counselling` | Пройди профессиональную консультацию или карьерное тестирование |
| 263 → 265 | `roadmap.profession_until_goal_title` | Начало профессионального пути |
| 265 → 267 | `roadmap.profession_first_job` | Подготовь резюме и начни поиск первой работы или практики |
| 266 → 268 | `roadmap.profession_training_program` | Поступи на профессиональную программу обучения по направлению «{top_name}» |
| 267 → 269 | `roadmap.profession_find_mentor` | Найди ментора в выбранной сфере для карьерной поддержки |
| 278 → 280 | `roadmap.university_close_requirement` | Закрыть требование «{requirement}»: {comment} |
| 286 → 288 | `roadmap.university_study_requirements` | Изучи требования к поступлению в целевой университет |
| 287 → 289 | `roadmap.university_list_documents` | Составь список документов, необходимых для подачи заявки |
| 288 → 290 | `roadmap.university_find_deadlines` | Найди дедлайны подачи документов и запиши их |
| 295 → 297 | `roadmap.university_continue_requirement` | Продолжить работу над «{requirement}»: {comment} |
| 303 → 305 | `roadmap.university_prepare_exams` | Подготовься к сдаче вступительных экзаменов или тестов |
| 304 → 306 | `roadmap.university_exam_courses` | Запишись на курсы подготовки к экзаменам (при необходимости) |
| 305 → 307 | `roadmap.university_start_portfolio` | Начни собирать портфолио достижений |
| 311 → 313 | `roadmap.university_month_1_title` | Закрыть критические пробелы |
| 312 → 314 | `roadmap.university_month_1_outcome` | План закрытия критических пробелов для поступления. |
| 317 → 319 | `roadmap.university_months_3_title` | Устранить пробелы в процессе |
| 318 → 320 | `roadmap.university_months_3_outcome` | Устранение пробелов в знаниях и навыках для вуза. |
| 323 → 325 | `roadmap.university_months_6_title` | Подготовить документы к поступлению |
| 324 → 326 | `roadmap.university_months_6_outcome` | Собранный комплект документов и готовое эссе. |
| 326 → 328 | `roadmap.university_collect_documents` | Собери все необходимые документы для подачи заявки |
| 327 → 329 | `roadmap.university_write_essay` | Напиши мотивационное письмо или вступительное эссе |
| 328 → 330 | `roadmap.university_deadline_reminders` | Проверь дедлайны подачи документов и расставь напоминания |
| 333 → 335 | `roadmap.university_year_1_title` | Подать заявку |
| 334 → 336 | `roadmap.university_year_1_outcome` | Поданные заявления в выбранные вузы. |
| 336 → 338 | `roadmap.university_submit_application` | Отправь заявку на поступление в университет |
| 337 → 339 | `roadmap.university_scholarships` | Изучи возможности стипендий и грантов для поступающих |
| 338 → 340 | `roadmap.university_backup_choices` | Подготовь 2–3 запасных варианта университетов |
| 343 → 345 | `roadmap.university_until_goal_title` | Поступление |
| 344 → 346 | `roadmap.university_until_goal_outcome` | Успешное прохождение испытаний и зачисление. |
| 346 → 348 | `roadmap.university_entrance_tests` | Пройди вступительные испытания или собеседование |
| 347 → 349 | `roadmap.university_accept_offer` | Подпиши оферт о зачислении |
| 348 → 350 | `roadmap.university_admission_documents` | Оформи необходимые документы (виза, общежитие, регистрация) |
| 368 → 370 | `roadmap.university_focus` | Этот план сфокусирован на подготовке к поступлению в вуз: закрытии академических пробелов, сборе необходимых документов, подготовке к экзаменам и успешной подаче заявления. |
| 372 → 374 | `roadmap.profession_focus` | План ориентирован на развитие практических навыков в выбранной профессии, создание первого портфолио проектов и подготовку к старту в профессиональной среде. |
| 378 → 380 | `roadmap.explore_focus` | Судя по твоим ответам, у тебя есть явные интересы и сильные стороны — этот план поможет попробовать ведущие направления на практике и сделать осознанный выбор без давления и спешки. |
| 552 → 554 | `api_errors.assessment_not_found` | Assessment not found |
| 558 → 560 | `api_errors.profile_not_found` | Profile not found |
| 678 → 680 | `api_errors.ai_unavailable` | ИИ временно недоступен, попробуй ещё раз |
| 772 → 774 | `api_errors.program_not_found` | Program not found |
| 779 → 781 | `api_errors.program_does_not_belong_to_this_direction` | Program does not belong to this direction |
| 865 → 867 | `api_errors.assessment_not_found` | Assessment not found |
| 871 → 873 | `api_errors.profile_not_found` | Profile not found |
| 877 → 879 | `api_errors.feature_requires_age_10` | Эта возможность доступна с 10 лет |
| 888 → 890 | `api_errors.direction_inquiry_not_completed` | Сначала пройди опрос по этому направлению |
| 893 → 895 | `api_errors.direction_not_found` | Direction not found |
| 985 → 987 | `api_errors.assessment_not_found` | Assessment not found |
| 1046 → 1048 | `api_errors.assessment_not_found` | Assessment not found |
| 1052 → 1054 | `api_errors.profile_not_found` | Profile not found |
| 1058 → 1060 | `api_errors.feature_requires_age_10` | Эта возможность доступна с 10 лет |
| 1063 → 1065 | `api_errors.program_not_found` | Program not found |
| 1079 → 1081 | `api_errors.program_has_no_direction` | Эта программа не связана ни с одним направлением |
| 1084 → 1086 | `api_errors.direction_not_found` | Direction not found |
| 1094 → 1096 | `api_errors.assessment_not_found` | Assessment not found |

### `app/services/university_service.py`

| Строки | Ключ | Исходный текст / шаблон |
|---|---|---|
| 91 → 92 | `api_errors.invalid_sort_field` | Unknown sort field: {sort} |
| 219 → 220 | `api_errors.program_not_found` | Program not found |
| 418 → 419 | `api_errors.university_not_found` | University not found |
| 445 → 446 | `api_errors.university_not_found` | University not found |
