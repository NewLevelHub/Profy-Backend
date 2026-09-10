"""
Infrequency ("trap") content bank — pure content, no logic.

Attention checks for the protocol-validity module (epic PRO-282, phase 1;
PRO-296). **NOT a psychometric scale** (ТестЛжи.md §3.5,
psych-block-spec.md §A6) — just a standard attention-control device.

Each item has exactly one plausible answer for any respondent who is reading.
A deviating answer is ONE signal of careless / insufficient-effort responding;
`infrequency_failed` (count of `answer != expected_answer`) is combined with
LongString and IRV, never used alone (PRO-299, conservative thresholds).

Wording rules (PRO-296 §2):
  - project-authored, not from any published scale;
  - first person, same register as the Big Five items, so a trap does not
    stand out in the interleaved battery;
  - plainly, unarguably true or false — no absurdist / comic phrasing that a
    reading teenager would flag as "the trick question";
  - no semantic overlap with the MC-SDS items
    (docs/psych/psych-block-spec.md §A7).

`expected_answer`:
  "agree" / "disagree" — the only plausible folded binary answer.

kk translation — PRO-301 (the trap must stay obvious in Kazakh too).

To change: edit ITEMS and re-run scripts/seed_lie_scale_questions.py (PRO-297).
"""

ITEMS: list[dict] = [
    {"key": "infreq_01", "expected_answer": "agree",    "text": "Прямо сейчас я читаю этот вопрос."},
    {"key": "infreq_02", "expected_answer": "agree",    "text": "Я хотя бы раз в жизни пил воду."},
    {"key": "infreq_03", "expected_answer": "disagree", "text": "Я ни разу в жизни не спал."},
    {"key": "infreq_04", "expected_answer": "disagree", "text": "Я старше своих родителей."},
    {"key": "infreq_05", "expected_answer": "disagree", "text": "Я помню каждый день своей жизни начиная с самого рождения."},
]

assert 3 <= len(ITEMS) <= 5, f"infrequency bank must hold 3–5 traps, got {len(ITEMS)}"
assert len({i["key"] for i in ITEMS}) == len(ITEMS), "infrequency keys must be unique"
assert all(i["expected_answer"] in ("agree", "disagree") for i in ITEMS)
assert [i["key"] for i in ITEMS] == [f"infreq_{n:02d}" for n in range(1, len(ITEMS) + 1)]
# Both answer directions are represented, so straight-lining in either
# direction trips at least one trap.
assert {i["expected_answer"] for i in ITEMS} == {"agree", "disagree"}

# instrument / role / age_tier / locale / order — see the note in
# scripts/lie_scale_bank.py. `order` continues the RIASEC + Big Five + MI +
# MC-SDS sequence.
from scripts.bigfive_question_bank import QUESTIONS as _BIGFIVE_QUESTIONS  # noqa: E402
from scripts.lie_scale_bank import ITEMS as _MC_SDS_ITEMS  # noqa: E402
from scripts.mi_question_bank import QUESTIONS as _MI_QUESTIONS  # noqa: E402
from scripts.riasec_question_bank import QUESTIONS as _RIASEC_QUESTIONS  # noqa: E402

_BASE = (
    len(_RIASEC_QUESTIONS)
    + len(_BIGFIVE_QUESTIONS)
    + len(_MI_QUESTIONS)
    + len(_MC_SDS_ITEMS)
)
for _i, _item in enumerate(ITEMS, start=_BASE + 1):
    _item["order"] = _i
    _item["instrument"] = "validity"
    _item["validity_role"] = "infrequency"
    _item["age_tier"] = "middle"
    _item["locale"] = "ru"
