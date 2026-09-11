"""Transactional-email strings — subject line + plain-text body (KZ-308).

Was Russian literals in `app/services/email_service.py`. The HTML bodies live
next to this as templates (`app/templates/email/<name>.html` and the `.kk.html`
sibling); only the subject and the plain-text alternative are here.

`{code}` is the one placeholder — formatted at the call site with `.format()`.

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
}
