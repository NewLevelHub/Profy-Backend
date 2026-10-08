"""Transactional-email strings — subject line + plain-text body (KZ-308).

Was Russian literals in `app/services/email_service.py`. The HTML bodies live
next to this as templates (`app/templates/email/<name>.html` and the `.kk.html`
sibling); only the subject and the plain-text alternative are here.

`{code}` / `{student_name}` are the placeholders — formatted at the call site
with `.format()`. The review-pending email goes to a psychologist, in that
psychologist's own `users.locale` (PRO-430). The staff invitation (PRO-461)
has no user yet, so its locale is `invitations.locale`; `{role}` there is one
of the `invitation_role_*` phrases.

Unlike the request-locale areas, the email locale is the *recipient's* stored
choice (`users.locale`) or the registration `Accept-Language` — both already
persisted through `KNOWN_LOCALES` — so `kk` is honored here before KZ-603.
"""

RU = {
    "verification_subject": "Твой код подтверждения — Profile",
    "verification_plain": "Твой код подтверждения: {code}\n\nКод действителен 15 минут.",
    "password_reset_subject": "Сброс пароля — Profile",
    "password_reset_plain": (
        "Твой код для сброса пароля: {code}\n\n"
        "Код действителен 15 минут.\n\n"
        "Если ты не запрашивал сброс пароля — проигнорируй это письмо."
    ),
    "review_pending_subject": "Новый отчёт ждёт проверки — Profile",
    "review_pending_plain": (
        "Ученик {student_name} завершил тест. Отчёт ждёт вашей проверки:\n"
        "{review_url}"
    ),
    "result_published_subject": "Твой результат готов — Profile",
    "result_published_plain": (
        "{student_name}, психолог проверил твой отчёт — он уже ждёт тебя в Profile:\n"
        "{results_url}"
    ),
    "result_published_fallback_name": "Привет",
    "invitation_subject": "Приглашение в Profile",
    "invitation_plain": (
        "Вас пригласили присоединиться к Profile {role}.\n\n"
        "Чтобы принять приглашение и завершить регистрацию, перейдите по ссылке:\n"
        "{invite_url}\n\n"
        "Ссылка действительна {hours} ч.\n\n"
        "Если вы не ждали приглашения — просто проигнорируйте это письмо."
    ),
    "invitation_role_psychologist": "в роли психолога",
    "invitation_role_admin": "в роли администратора",
}

KK = {
    "verification_subject": "Растау кодың — Profile",
    "verification_plain": "Растау кодың: {code}\n\nКод 15 минут жарамды.",
    "password_reset_subject": "Құпиясөзді қалпына келтіру — Profile",
    "password_reset_plain": (
        "Құпиясөзді қалпына келтіру кодың: {code}\n\n"
        "Код 15 минут жарамды.\n\n"
        "Егер сен құпиясөзді қалпына келтіруді сұрамасаң — бұл хатты елемей қой."
    ),
    "review_pending_subject": "Жаңа есеп тексеруді күтуде — Profile",
    "review_pending_plain": (
        "{student_name} оқушысы тестті аяқтады. Есеп сіздің тексеруіңізді күтуде:\n"
        "{review_url}"
    ),
    "result_published_subject": "Нәтижең дайын — Profile",
    "result_published_plain": (
        "{student_name}, психолог есебіңді тексерді — ол Profile платформасында сені күтіп тұр:\n"
        "{results_url}"
    ),
    "result_published_fallback_name": "Сәлем",
    "invitation_subject": "Profile платформасына шақыру",
    "invitation_plain": (
        "Сіз Profile платформасына {role} қосылуға шақырылдыңыз.\n\n"
        "Шақыруды қабылдап, тіркелуді аяқтау үшін сілтемеге өтіңіз:\n"
        "{invite_url}\n\n"
        "Сілтеме {hours} сағат жарамды.\n\n"
        "Егер шақыруды күтпеген болсаңыз — бұл хатты елемеңіз."
    ),
    "invitation_role_psychologist": "психолог ретінде",
    "invitation_role_admin": "әкімші ретінде",
}
