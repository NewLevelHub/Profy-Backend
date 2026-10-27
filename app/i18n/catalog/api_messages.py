"""User-facing authentication acknowledgements. RU preserves the original wording,
including legacy English responses."""

RU = {
    "password_reset_completed": "Password has been reset successfully.",
    "password_reset_requested": "If an account exists, a reset code has been sent.",
    "verification_code_sent": "Код отправлен на почту",
    "crm_task_payment_check": "Ученик прошёл диагностику, а сделка не оплачена — проверьте оплату",
}

# Kazakh copy; keep the same acknowledgement regardless of account existence.
KK = {
    "password_reset_completed": "Құпиясөз сәтті қалпына келтірілді.",
    "password_reset_requested": "Егер тіркелгі бар болса, құпиясөзді қалпына келтіру коды жіберілді.",
    "verification_code_sent": "Код электрондық поштаға жіберілді",
    "crm_task_payment_check": "Оқушы диагностикадан өтті, бірақ мәміле төленбеген — төлемді тексеріңіз",
}
