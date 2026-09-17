"""Transactional-email strings — subject line + plain-text body (KZ-308).

Was Russian literals in `app/services/email_service.py`. The HTML bodies live
next to this as templates (`app/templates/email/<name>.html` and the `.kk.html`
sibling); only the subject and the plain-text alternative are here.

`{code}` / `{student_name}` are the placeholders — formatted at the call site
with `.format()`. The review-pending email goes to a psychologist and is
sent in `ru` only (the psychologist cabinet is Russian, KZ-210); its `kk`
entries exist for catalog parity.

Unlike the request-locale areas, the email locale is the *recipient's* stored
choice (`users.locale`) or the registration `Accept-Language` — both already
persisted through `KNOWN_LOCALES` — so `kk` is honored here before KZ-603.
"""

RU = {
    "verification_subject": "Твой код подтверждения — Profy",
    "verification_plain": "Твой код подтверждения: {code}\n\nКод действителен 15 минут.",
    "password_reset_subject": "Сброс пароля — Profy",
    "password_reset_plain": (
        "Твой код для сброса пароля: {code}\n\n"
        "Код действителен 15 минут.\n\n"
        "Если ты не запрашивал сброс пароля — проигнорируй это письмо."
    ),
    "review_pending_subject": "Новый отчёт ждёт проверки — Profy",
    "review_pending_plain": (
        "Ученик {student_name} завершил тест. Отчёт ждёт вашей проверки:\n"
        "{review_url}"
    ),
    "result_published_subject": "Твой результат готов — Profy",
    "result_published_plain": (
        "{student_name}, психолог проверил твой отчёт — он уже ждёт тебя в Profy:\n"
        "{results_url}"
    ),
    "result_published_fallback_name": "Привет",
}

KK = {
    "verification_subject": "Растау кодың — Profy",
    "verification_plain": "Растау кодың: {code}\n\nКод 15 минут жарамды.",
    "password_reset_subject": "Құпиясөзді қалпына келтіру — Profy",
    "password_reset_plain": (
        "Құпиясөзді қалпына келтіру кодың: {code}\n\n"
        "Код 15 минут жарамды.\n\n"
        "Егер сен құпиясөзді қалпына келтіруді сұрамасаң — бұл хатты елемей қой."
    ),
    "review_pending_subject": "Жаңа есеп тексеруді күтуде — Profy",
    "review_pending_plain": (
        "{student_name} оқушысы тестті аяқтады. Есеп сіздің тексеруіңізді күтуде:\n"
        "{review_url}"
    ),
    "result_published_subject": "Нәтижең дайын — Profy",
    "result_published_plain": (
        "{student_name}, психолог есебіңді тексерді — ол Profy-де сені күтіп тұр:\n"
        "{results_url}"
    ),
    "result_published_fallback_name": "Сәлем",
}
