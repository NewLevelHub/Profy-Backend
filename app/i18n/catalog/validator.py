"""Per-locale catalog for report narrative validator fix instructions (KZ-402)."""
from __future__ import annotations

RU: dict[str, str] = {
    "correction_header": "Твой предыдущий ответ не прошёл проверку. Конкретные проблемы:\n",
    "correction_footer": (
        "\n\nПришли новый полный JSON-ответ по той же схеме, который "
        "исправляет именно эти проблемы — не меняй остальное без необходимости."
    ),
    "LANGUAGE_MISMATCH": (
        "Ответ дан не на том языке. Перепиши весь ответ полностью на требуемом языке."
    ),
    "career_narrative_evidence": (
        "У карточки {detail!r} в career_narrative пустой или неверный "
        "evidence_ids. Добавь туда хотя бы один реальный source_id с "
        "source_type \"riasec_category\" из каталога — или, если ни один не "
        "подходит по смыслу, убери эту карточку совсем."
    ),
    "strength_card_not_candidate": (
        "Карточка strength_cards с title {detail!r} ссылается не ровно на одного "
        "кандидата из каталога strength_candidates. У каждой карточки "
        "evidence_ids = [source_id одного кандидата] — никаких riasec/personality/"
        "motivation/thinking_style и никаких других id."
    ),
    "strength_card_count": (
        "Неверное число карточек strength_cards ({detail}). Нужно ровно по одной "
        "карточке на каждого кандидата из каталога strength_candidates — "
        "не добавляй новых и не пропускай ни одного."
    ),
    "strength_card_iq_label": (
        "В карточке strength_cards {detail!r} есть ярлык про интеллект/IQ или "
        "одарённость. Опиши наблюдение по типу заданий («в таких заданиях у тебя "
        "получалось лучше всего»), без оценки ума и сравнения с другими."
    ),
    "strength_card_interest_as_ability": (
        "Карточка strength_cards {detail!r} опирается на кандидата с basis "
        "\"interest\", но описывает его как доказанное умение. Перепиши как интерес, "
        "который стоит проверить на практике: без «умеешь», «у тебя получается», "
        "«способности», «талант»."
    ),
    "strength_card_explanation_changed": (
        "В карточке strength_cards {detail!r} изменён description. Скопируй "
        "description соответствующего strength_candidate дословно; менять можно только title."
    ),
    "strength_card_duplicate_evidence": (
        "Source_id {detail!r} процитирован больше чем в одной карточке "
        "strength_cards — какой-то один факт пересказан 2-3 разными "
        "карточками. Оставь этот source_id только в одной карточке, а "
        "остальные карточки с ним убери (не увеличивай их число сверх "
        "количества уникальных фактов)."
    ),
    "thinking_style_count": (
        "Неверное число карточек thinking_style_notes ({detail}). Должна быть "
        "РОВНО ОДНА карточка на ВСЕ evidence с source_type \"thinking_style\" "
        "вместе (даже если таких evidence два — не делай две отдельные "
        "карточки, объедини их в одну), и ноль карточек, если такого evidence "
        "нет вообще."
    ),
    "thinking_style_incomplete": (
        "Карточка thinking_style_notes не ссылается на все нужные evidence "
        "({detail}). Добавь в её evidence_ids source_id каждого сигнала "
        "thinking_style из каталога — сейчас в ней не хватает одного."
    ),
    "motivation_ungrounded": (
        "motivation_narrative.evidence_ids пуст, хотя в каталоге есть evidence "
        "с source_type \"motivation\". Добавь их source_id в evidence_ids."
    ),
    "source_id_leak": (
        "В видимом тексте (title/description) буквально встречается "
        "source_id {detail!r} — так писать нельзя, это внутренний "
        "идентификатор, а не часть текста для ребёнка. Убери его из текста "
        "полностью (не заменяй похожей фразой в скобках) — ссылка на этот "
        "факт должна быть только в поле evidence_ids этой же карточки."
    ),
    "summary_wrong_length": (
        "summary состоит из неверного числа предложений ({detail}). "
        "Перепиши summary так, чтобы в нём было РОВНО 5-6 полных предложений, "
        "и каждое добавляло новое содержание, а не повторяло другое (не "
        "используй фразу про «карту возможностей» — см. следующее правило)."
    ),
    "summary_duplicates_disclaimer": (
        "summary содержит фразу {detail!r} — это дублирует отдельный "
        "disclaimer, который и так показывается рядом с summary на странице. "
        "Убери это предложение целиком и замени его предложением с новым "
        "содержанием (например практичный совет, на что обратить внимание "
        "дальше в отчёте)."
    ),
    "final_analysis_too_short": (
        "final_analysis состоит из недостаточного числа предложений "
        "({detail}). Должно быть минимум 3 предложения, связывающих минимум "
        "два разных раздела отчёта между собой (например интересы + "
        "характер, или стиль мышления + мотивация) — не пересказ одного "
        "раздела."
    ),
    "final_analysis_duplicates_disclaimer": (
        "final_analysis содержит фразу {detail!r} — это дублирует "
        "disclaimer. Убери это предложение и замени его мыслью о том, как "
        "разделы отчёта связаны между собой."
    ),
    "final_analysis_length": (
        "final_analysis слишком длинный или слишком короткий ({detail}). "
        "Должно быть 3-5 содержательных предложений, не больше."
    ),
}

KK: dict[str, str] = {
    "correction_header": "Алдыңғы жауабың тексеруден өтпеді. Нақты анықталған мәселелер:\n",
    "correction_footer": (
        "\n\nДәл осы мәселелерді түзететін жаңа толық JSON-жауапты сол сұлба "
        "бойынша жібер — қажеттіліксіз қалған бөлімдерді өзгертпе."
    ),
    "LANGUAGE_MISMATCH": (
        "Жауап орыс тілінде берілген. Барлық мәтінді тек қазақ тілінде толық қайта жаз "
        "(қазақ әріптерін ә, ғ, қ, ң, ө, ұ, ү, һ, і міндетті түрде қолдан)."
    ),
    "career_narrative_evidence": (
        "career_narrative ішіндегі {detail!r} карточкасында evidence_ids бос немесе қате. "
        "Оған каталогтан source_type \"riasec_category\" бар кемінде бір нақты source_id қос "
        "— немесе ешқайсысы сәйкес келмесе, бұл карточканы мүлде алып таста."
    ),
    "strength_card_not_candidate": (
        "strength_cards ішіндегі title={detail!r} карточкасы strength_candidates "
        "каталогындағы дәл бір үміткерге сілтеме жасамайды. Әр карточканың evidence_ids "
        "мәні = [бір үміткердің source_id] — riasec/personality/motivation/thinking_style "
        "және басқа id қолданба."
    ),
    "strength_card_count": (
        "strength_cards карточкаларының саны қате ({detail}). strength_candidates "
        "каталогындағы әр үміткерге дәл бір карточка жаса — жаңасын қоспа, ешқайсысын түсірме."
    ),
    "strength_card_iq_label": (
        "strength_cards ішіндегі {detail!r} карточкасында интеллект/IQ не дарындылық туралы "
        "белгі бар. Бақылауды тапсырма түрі бойынша сипатта («мұндай тапсырмаларда нәтижең "
        "ең жақсы болды»), ақылды бағаламай және басқалармен салыстырмай."
    ),
    "strength_card_interest_as_ability": (
        "strength_cards ішіндегі {detail!r} карточкасы basis=\"interest\" үміткеріне "
        "сүйенеді, бірақ оны дәлелденген дағды ретінде сипаттайды. Оны іс жүзінде тексеруге "
        "тұрарлық қызығушылық ретінде қайта жаз: «білесің», «қолыңнан келеді», «қабілет», "
        "«дарын» сөздерінсіз."
    ),
    "strength_card_explanation_changed": (
        "strength_cards ішіндегі {detail!r} карточкасының description мәтіні өзгертілген. "
        "Тиісті strength_candidate description мәтінін сөзбе-сөз көшір; тек title өзгертуге болады."
    ),
    "strength_card_duplicate_evidence": (
        "Source_id {detail!r} strength_cards ішінде бірнеше карточкада қолданылған — "
        "бір факт 2-3 түрлі карточкада қайталанып тұр. Бұл source_id-ді тек бір карточкада қалдыр, "
        "ал оны қайталайтын қалған карточкаларды алып таста."
    ),
    "thinking_style_count": (
        "thinking_style_notes карточкаларының саны қате ({detail}). source_type=\"thinking_style\" "
        "бар БАРЛЫҚ деректерге ТЕК БІР карточка болуы тиіс (тіпті осындай екі дерек болса да — бөлек "
        "жасамай, бір карточкаға біріктір), ал егер ондай дерек жоқ болса, нөл карточка болуы керек."
    ),
    "thinking_style_incomplete": (
        "thinking_style_notes карточкасы барлық қажетті деректерге сілтеме жасамайды ({detail}). "
        "Каталогтағы thinking_style типті әрбір сигналдың source_id мәнін оның evidence_ids өрісіне қос."
    ),
    "motivation_ungrounded": (
        "Каталогта source_type=\"motivation\" бар деректер бола тұра, motivation_narrative.evidence_ids бос. "
        "Олардың source_id мәндерін evidence_ids ішіне қос."
    ),
    "source_id_leak": (
        "Көрінетін мәтінде (title/description) source_id {detail!r} жазылып кеткен — бұл ішкі "
        "сәйкестендіргіш, оны оқушыға көрсетуге болмайды. Оны мәтіннен толық алып таста — "
        "сілтеме тек карточканың evidence_ids өрісінде сақталуы тиіс."
    ),
    "summary_wrong_length": (
        "summary қате сөйлем санынан тұрады ({detail}). summary-ді дәл 5-6 толық сөйлем болатындай "
        "етіп қайта жаз, әр сөйлем жаңа мазмұн қосуы керек."
    ),
    "summary_duplicates_disclaimer": (
        "summary ішінде {detail!r} тіркесі бар — бұл беттегі бөлек disclaimer мәтінін қайталайды. "
        "Бұл сөйлемді алып тастап, орнына жаңа мағына беретін сөйлем жаз."
    ),
    "final_analysis_too_short": (
        "final_analysis тым аз сөйлемнен тұрады ({detail}). Есептің кемінде екі түрлі бөлімін бір-бірімен "
        "байланыстыратын кем дегенде 3 сөйлем болуы қажет."
    ),
    "final_analysis_duplicates_disclaimer": (
        "final_analysis ішінде {detail!r} тіркесі бар — бұл disclaimer-ді қайталайды. "
        "Бұл сөйлемді өшіріп, оның орнына есеп бөлімдерінің өзара байланысы туралы ой жаз."
    ),
    "final_analysis_length": (
        "final_analysis тым ұзын немесе тым қысқа ({detail}). Ол 3-5 мағыналы сөйлемнен тұруы керек."
    ),
}
