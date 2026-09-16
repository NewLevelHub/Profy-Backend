"""PRO-338 Ф2.2 — full content bank for the Belbin BTRSPI ("Кто вы в
организации") ipsative test: 7 sections x 8 statements = 56 items, each
tagged with the one of 8 team roles it scores toward.

Source: docs/psych/belbin-content-sources.md (Ф2.1 research, closed
2026-09-16) — item text is psytests.org's own wording (explicit product
decision to use it as the reference translation "по вопросам в принципе"),
the letter->role key is cross-verified against two further independent
sources (fnpr.ru, abmgroup.ru) that agree on it verbatim. That research also
found and corrected 2 mislabeled roles in the ticket's own "known" sections
II/III (see that file's "Найдена ошибка" section) — this bank uses the
corrected roles, not the ticket text's original labels.

Role codes are Latin snake_case (`ROLES` keys below), not the spec's own
Cyrillic single-letter shorthand (И/П/Ф/...) — same principle as
`professional_types_bank.py`'s `practical`/`technical`/... scale keys, and
explicitly expected by `app/models/belbin_run.py` (Ф2.3)'s own docstring,
written before this file existed.

Unlike every other `scripts/*_bank.py` in this codebase, Belbin is NOT
Question-model content — Ф0.2 deliberately gave it no QuestionInstrument
member (ipsative point-allocation doesn't fit the Likert/pair shape), and it
has no `seed_*_questions.py` counterpart. This module is imported directly
by whatever reads it (the future submit endpoint of Ф2.4, `belbin_runs`
model of Ф2.3, frontend-facing content endpoint), not resynced into a table.

Shape consumed by `app.services.ipsative_battery` (Ф0.6):
  - `validate_allocation(allocation, expected_items=SECTIONS[i]["items" ids], total=BLOCK_TOTAL)`
  - `aggregate_by_key(allocations, item_to_key_map=ITEM_ROLE)` -> role totals
"""

# 8 team roles, Latin code -> full Russian name (for FE labels /
# TeamRoleSection, Ф2.7). Order here matches the canonical column order used
# throughout the source research doc's key table (И П Ф М Р О К Д).
ROLES: dict[str, str] = {
    "implementer": "Исполнитель",
    "coordinator": "Председатель",
    "shaper": "Формирователь",
    "plant": "Мыслитель",
    "resource_investigator": "Разведчик",
    "evaluator": "Оценщик",
    "team_worker": "Коллективист",
    "finisher": "Доводчик",
}

# Fixed instruction text, verbatim from the spec (Ф2.2 ticket).
INSTRUCTION: str = (
    "Опросник состоит из 7 разделов. В каждом разделе необходимо "
    "распределить ровно 10 баллов между 8 утверждениями пропорционально "
    "тому, насколько они отражают ваше типичное поведение. Можно "
    "распределить баллы, например, как 5/3/2, или отдать все 10 баллов "
    "одному утверждению."
)

BLOCK_TOTAL = 10  # points to distribute per section
TOTAL = 70  # BLOCK_TOTAL * 7 sections — sanity-checked below, not hardcoded twice


# Each section: roman numeral, title (psytests.org wording), and 8
# (text, role) pairs in psytests.org's own a-h order. item ids are built as
# f"{section}{1-based index}" (e.g. "I1".."I8", "VII1".."VII8") below.
_SECTIONS_RAW: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "I", "Чем я могу помочь команде",
        [
            ("Я думаю, что могу быстро выявлять и использовать новые возможности.", "resource_investigator"),
            ("Я могу успешно работать с разными типами людей.", "team_worker"),
            ("Разработка идей является моим естественным достоинством.", "plant"),
            ("Я обладаю способностью находить в других людях такие качества, которые могут быть полезны для всей группы.", "coordinator"),
            ("Моя способность доводить дело до завершения во многом определяет мою личную эффективность.", "finisher"),
            ("Я готов смириться с временной непопулярностью, если это положительно повлияет на результаты работы команды.", "shaper"),
            ("Я быстро понимаю, что надо делать в хорошо знакомой мне ситуации.", "implementer"),
            ("Я могу предложить набор разумных вариантов действий без предубеждений и пристрастий.", "evaluator"),
        ],
    ),
    (
        "II", "Если с точки зрения командной работы у меня есть недостатки, то они таковы",
        [
            ("Я не успокоюсь до тех пор, пока не пойму, что рабочие встречи команды хорошо организованы, подготовлены и проводятся правильно.", "implementer"),
            ("Я благосклонен к людям, выдвигающим оригинальные предложения.", "coordinator"),
            ("Я страдаю многословием, когда группа обсуждает новые идеи.", "resource_investigator"),
            ("Моя страсть возражать по любому поводу мешает мне присоединиться к моим коллегам.", "evaluator"),
            ("Я иногда кажусь человеком авторитарным, стремящимся повлиять на других людей.", "shaper"),
            ("Мне трудно проявить инициативу, потому что я поддаюсь настроению, установившемуся в группе.", "team_worker"),
            ("Я углубляюсь в свои размышления до такой степени, что теряю контроль над тем, что происходит.", "plant"),
            ("Мои коллеги считают, что я слишком волнуюсь из-за мелочей и опасений, что дела могут пойти не так, как надо.", "finisher"),
        ],
    ),
    (
        "III", "Когда я работаю над проектом вместе с другими людьми",
        [
            ("Я могу влиять на коллег без давления на них.", "coordinator"),
            ("Моя врожденная осмотрительность позволяет мне предотвращать небрежности, ошибки и упущения.", "finisher"),
            ("Я готов потребовать от коллег четкости, чтобы время не уходило впустую и участники совещания не отклонялись от главной темы.", "shaper"),
            ("Меня можно признать человеком, способным придумать что-нибудь оригинальное.", "plant"),
            ("Я всегда готов поддержать предложение, полезное для команды.", "team_worker"),
            ("Я интересуюсь новейшими идеями и разработками.", "resource_investigator"),
            ("Я думаю, что моя способность к холодному расчету находит поддержку у других людей.", "evaluator"),
            ("На меня можно положиться при организации важной работы.", "implementer"),
        ],
    ),
    (
        "IV", "Мое отношение к командной работе проявляется в следующем",
        [
            ("Я стремлюсь хорошо знать своих коллег.", "team_worker"),
            ("Я неохотно обмениваюсь мнениями с другими людьми и свое особое мнение держу при себе.", "shaper"),
            ("Я нахожу убедительные аргументы при необходимости отвергнуть пустые аргументы.", "evaluator"),
            ("Я думаю, что у меня есть талант организатора планомерной работы.", "implementer"),
            ("Я склонен отвергать очевидное и предлагать неожиданное.", "plant"),
            ("Я проявляю высокую требовательность к себе при выполнении командной роли, которую на меня возлагают.", "finisher"),
            ("Я готов самостоятельно осуществлять контакты за пределами группы.", "resource_investigator"),
            ("Я интересуюсь различными точками зрения, но принятое решение выполняю без колебаний.", "coordinator"),
        ],
    ),
    (
        "V", "Я получаю удовлетворение от работы, потому что",
        [
            ("Мне нравится анализировать сложные ситуации и взвешивать всевозможные варианты.", "evaluator"),
            ("Мне интересно находить решения различных проблем.", "implementer"),
            ("Мне нравится осознавать, что я стимулирую хорошие рабочие взаимоотношения.", "team_worker"),
            ("Я оказываю существенное влияние на процесс принятия решений.", "shaper"),
            ("Я умею находить людей, которые могут предложить что-нибудь новое.", "resource_investigator"),
            ("Я способен убедить людей в необходимости тех или иных действий.", "coordinator"),
            ("Я чувствую, когда мне необходимо полностью сосредоточиться на поставленной задаче.", "finisher"),
            ("Я люблю деятельность, которая развивает мое воображение.", "plant"),
        ],
    ),
    (
        "VI", "Если мне вместе с группой незнакомых людей неожиданно поручат трудную задачу, которую надо выполнить быстро",
        [
            ("Я предпочел бы уединиться и хорошо обдумать ситуацию, прежде чем разработать план действий.", "plant"),
            ("Я готов работать с человеком, который проявил позитивный подход к делу, каким бы трудным этот человек ни казался.", "team_worker"),
            ("Я попытался бы разделить общую задачу на ряд мелких и установил бы, какой вклад в решение задачи могут внести конкретные члены команды.", "coordinator"),
            ("Моя врожденная обязательность помогает мне контролировать сроки выполнения задания.", "finisher"),
            ("Я способен сохранять невозмутимость и думать по существу.", "evaluator"),
            ("Я могу следовать к намеченной цели, несмотря ни на какое давление.", "implementer"),
            ("Я готов взять на себя роль ведущего, если чувствую, что группа не продвигается в решении задачи.", "shaper"),
            ("Я начну дискуссию, чтобы стимулировать коллег на новые мысли и привести группу в движение.", "resource_investigator"),
        ],
    ),
    (
        "VII", "Проблемы, которые я должен преодолеть, работая в группе",
        [
            ("Я склонен к раздражительности по отношению к тем, кто мешает группе продвигаться к цели.", "shaper"),
            ("Я могу вызвать критику со стороны коллег из-за моего увлечения анализом проблем и недостаточно развитой интуиции.", "evaluator"),
            ("Мое стремление задать правильный ход работе может привести к задержке выполнения задачи.", "finisher"),
            ("Я быстро теряю интерес к делу и надеюсь на кого-нибудь из команды, кто заменит меня.", "resource_investigator"),
            ("Мне трудно начать работу, пока я полностью не пойму цели этой работы.", "implementer"),
            ("Мне не всегда удается объяснить сложные идеи, которые рождает мой разум.", "plant"),
            ("Я сознаю необходимость поручать другим сделать то, что сам сделать не мог.", "coordinator"),
            ("Я становлюсь нерешительным, когда сталкиваюсь с сильным сопротивлением.", "team_worker"),
        ],
    ),
]

assert len(_SECTIONS_RAW) == 7, f"Belbin must have exactly 7 sections, got {len(_SECTIONS_RAW)}"
assert TOTAL == BLOCK_TOTAL * len(_SECTIONS_RAW)

SECTIONS: list[dict] = []
ITEM_ROLE: dict[str, str] = {}

for _section, _title, _statements in _SECTIONS_RAW:
    assert len(_statements) == 8, f"section {_section} must have exactly 8 items, got {len(_statements)}"
    _items = []
    for _i, (_text, _role) in enumerate(_statements, start=1):
        assert _role in ROLES, f"section {_section} item {_i}: unknown role {_role!r}"
        _item_id = f"{_section}{_i}"
        _items.append({"id": _item_id, "text": _text, "role": _role})
        ITEM_ROLE[_item_id] = _role
    # Every section's 8 items must cover all 8 roles exactly once — a
    # Belbin design invariant (each block is a full permutation of roles),
    # not just an accident of this particular content.
    assert {item["role"] for item in _items} == set(ROLES), (
        f"section {_section} must cover every role exactly once, got {[item['role'] for item in _items]}"
    )
    SECTIONS.append({"section": _section, "title": _title, "items": _items})

assert len(ITEM_ROLE) == 56, f"expected 56 unique item ids across all sections, got {len(ITEM_ROLE)}"
