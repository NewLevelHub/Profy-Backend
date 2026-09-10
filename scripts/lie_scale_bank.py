"""
MC-SDS content bank — pure content, no logic.

Marlowe-Crowne Social Desirability Scale, Russian 20-item adaptation by
Yu. L. Khanin ("Шкала мотивации одобрения" / ШМО). Part of the protocol-
validity module (epic PRO-282, phase 1; PRO-296).

These items are mixed into the Likert battery indistinguishably from Big Five
items (ТестЛжи.md §3.4): same scale, interleaved, no section header, no
warning screen. At scoring time (PRO-299) each Likert answer is folded to a
binary agree/disagree by the middle-option rule (see
docs/psych/psych-block-spec.md §A3) and matched against `keyed` — the
socially-desirable pole. Sum of matches = raw SD score, 0-20.

`keyed`:
  "agree"    — a folded "agree"    (верно / да)  answer scores 1 point
  "disagree" — a folded "disagree" (неверно/нет) answer scores 1 point

────────────────────────────────────────────────────────────────────────────
SOURCE STATUS — text and key verified against a printed reference (PRO-294).

Reference text: Марищук В. Л. и др. "Методики психодиагностики в спорте." —
М.: Просвещение, 1984 (canonical reprint of the primary source: Ханин Ю. Л.
"Шкала Марлоу-Крауна для исследования мотивации одобрения: методическое
письмо." — Л.: ЛНИИФК, 1976). 20 items, 11 direct / 9 reverse; the key below
matches this reference byte-for-byte.

PRO-294 also corrected four items that had drifted to the widespread corrupted
web copies (used for corporate HR): item 6 ("что-то делать", not "какое-то
дело"), item 12 (comma placement), item 16 ("что с собой взять"), item 18
("с вопросами", NOT "с просьбами" — the web version silently changes the
meaning). Do not "fix" these back to the online phrasing.

Still open (needs de visu library check, does not block use): exact edition
year (1974 vs 1976) and page numbers in the Raygorodsky / Fetiskin reprints;
a psychologist read-through for teenage phrasing.

Full item table, key rationale, thresholds, middle-option rule and the
interleave rule: docs/psych/psych-block-spec.md §A
────────────────────────────────────────────────────────────────────────────

To change: edit ITEMS and re-run scripts/seed_lie_scale_questions.py (PRO-297).
"""

ITEMS: list[dict] = [
    {"key": "mc_sds_01", "keyed": "agree",    "text": "Я внимательно читаю каждую книгу, прежде чем вернуть её в библиотеку."},
    {"key": "mc_sds_02", "keyed": "agree",    "text": "Я не испытываю колебаний, когда кому-нибудь нужно помочь в беде."},
    {"key": "mc_sds_03", "keyed": "agree",    "text": "Я всегда внимательно слежу за тем, как я одет."},
    {"key": "mc_sds_04", "keyed": "agree",    "text": "Дома я веду себя за столом так же, как в столовой."},
    {"key": "mc_sds_05", "keyed": "agree",    "text": "Я никогда ни к кому не испытывал антипатии."},
    {"key": "mc_sds_06", "keyed": "disagree", "text": "Был случай, когда я бросил что-то делать, потому что не был уверен в своих силах."},
    {"key": "mc_sds_07", "keyed": "disagree", "text": "Иногда я люблю позлословить об отсутствующих."},
    {"key": "mc_sds_08", "keyed": "agree",    "text": "Я всегда внимательно слушаю собеседника, кто бы он ни был."},
    {"key": "mc_sds_09", "keyed": "disagree", "text": "Был случай, когда я придумал вескую причину, чтобы оправдаться."},
    {"key": "mc_sds_10", "keyed": "disagree", "text": "Случалось, я пользовался оплошностью человека."},
    {"key": "mc_sds_11", "keyed": "agree",    "text": "Я всегда охотно признаю свои ошибки."},
    {"key": "mc_sds_12", "keyed": "disagree", "text": "Иногда вместо того, чтобы простить человека, я стараюсь отплатить ему тем же."},
    {"key": "mc_sds_13", "keyed": "disagree", "text": "Были случаи, когда я настаивал на том, чтобы делали по-моему."},
    {"key": "mc_sds_14", "keyed": "agree",    "text": "У меня не возникает внутреннего протеста, когда меня просят оказать услугу."},
    {"key": "mc_sds_15", "keyed": "agree",    "text": "У меня никогда не возникает досады, когда высказывают мнение, противоположное моему."},
    {"key": "mc_sds_16", "keyed": "agree",    "text": "Перед длительной поездкой я всегда тщательно продумываю, что с собой взять."},
    {"key": "mc_sds_17", "keyed": "disagree", "text": "Были случаи, когда я завидовал удаче других."},
    {"key": "mc_sds_18", "keyed": "disagree", "text": "Иногда меня раздражают люди, которые обращаются ко мне с вопросами."},
    {"key": "mc_sds_19", "keyed": "disagree", "text": "Когда у людей неприятности, я иногда думаю, что они получили по заслугам."},
    {"key": "mc_sds_20", "keyed": "agree",    "text": "Я никогда с улыбкой не говорил неприятных вещей."},
]

assert len(ITEMS) == 20, f"MC-SDS bank must hold 20 items, got {len(ITEMS)}"
assert len({i["key"] for i in ITEMS}) == 20, "MC-SDS item keys must be unique"
assert all(i["keyed"] in ("agree", "disagree") for i in ITEMS)
assert [i["key"] for i in ITEMS] == [f"mc_sds_{n:02d}" for n in range(1, 21)], (
    "MC-SDS keys must be the stable codes mc_sds_01 … mc_sds_20 in order"
)
# Sanity check on the reprinted key: direct (agree) vs reverse (disagree) split.
# 11 direct / 9 reverse in the commonly-cited version. PRO-294 confirms or fixes.
assert sum(1 for i in ITEMS if i["keyed"] == "agree") == 11
assert sum(1 for i in ITEMS if i["keyed"] == "disagree") == 9

# instrument / role / age_tier / locale / order — same shape the other
# scripts/*_bank.py files carry, so the PRO-297 seed can walk every question
# bank uniformly. `order` continues the RIASEC + Big Five + MI sequence and is
# never hardcoded (derived from their actual lengths). It is only a stable
# identifier: the runtime presentation position is decided by the interleave
# rule in docs/psych/psych-block-spec.md §A8 (implemented in PRO-298),
# not by this number.
from scripts.bigfive_question_bank import QUESTIONS as _BIGFIVE_QUESTIONS  # noqa: E402
from scripts.mi_question_bank import QUESTIONS as _MI_QUESTIONS  # noqa: E402
from scripts.riasec_question_bank import QUESTIONS as _RIASEC_QUESTIONS  # noqa: E402

_BASE = len(_RIASEC_QUESTIONS) + len(_BIGFIVE_QUESTIONS) + len(_MI_QUESTIONS)
for _i, _item in enumerate(ITEMS, start=_BASE + 1):
    _item["order"] = _i
    _item["instrument"] = "validity"
    _item["validity_role"] = "sd_key"
    # middle + senior, not junior. age_tier="middle" + age_tiers.visible_tiers
    # (junior ⊆ middle ⊆ senior) means junior never sees these; middle and
    # senior do. Junior validity items are a separate, deferred decision
    # (PRO-296 §3 — needs a psychologist, off by default).
    _item["age_tier"] = "middle"
    _item["locale"] = "ru"
