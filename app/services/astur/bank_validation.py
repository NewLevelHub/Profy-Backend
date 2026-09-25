"""Pre-publish validation of an АСТУР bank document (PRO-427 §3).

`validate_bank()` never raises on bad content — it returns every problem it
finds as a `BankIssue`, so the admin editor can show all of them at once. A
document is publishable only when the list is empty.

Rules:
- the document parses into `AsturBank`, every known subtest key is present
  exactly once and uses the scoring method its frontend renderer expects;
- item ids are non-empty and unique across the whole bank;
- every localized field has non-empty RU and KK, and list fields have the
  same length in both locales (RU and KK are the same task);
- the key exists among the options, and points at the same position in RU
  and KK;
- open-answer synonym tiers are non-empty and never overlap;
- image-based items resolve their stimulus by item_id from the stimulus
  manifest; a pinned stimulus must match it (paths and checksums), and the
  answer options must be exactly the stimulus' option letters;
- quick instructions have an even number of commands (two halves);
- against the previous published version (`base`), any item whose options
  or key changed needs an explicit key confirmation;
- `require_review` (every new version): each item has a difficulty, has
  been reviewed by a second team member, and meaning-based items explain
  their key. The pre-PRO-427 version 1 predates these fields.
"""
from dataclasses import asdict, dataclass

from pydantic import ValidationError

from app.services.astur.bank import (
    METHOD_BY_KEY,
    STIMULUS_KEYS,
    SUBJECT_TAGGED_KEYS,
    AsturBank,
    parse_bank,
    stimulus_manifest,
)

LOCALES = ("ru", "kk")
DIFFICULTIES = {"easy", "medium", "hard"}
REVIEW_STATUSES = {"unreviewed", "reviewed"}
LABILITY_DYNAMIC_KINDS = {"day_of_week", "own_name"}
LABILITY_ANSWER_FORMATS = {"digit", "shape", "symbol", "word"}

# Items whose correct answer rests on meaning, so a reviewer needs the
# reasoning behind the key to check it isn't ambiguous.
KEY_EXPLANATION_REQUIRED_KEYS = frozenset({"analogies", "classification", "generalization"})

# Fields that define what the correct answer is. Changing any of them on an
# existing item means the key has to be re-confirmed by whoever publishes.
KEY_DEFINING_FIELDS = ("options", "answer", "words", "score_2", "score_1", "concepts", "sequence", "dynamic")


@dataclass(frozen=True)
class BankIssue:
    code: str
    message: str
    subtest: str | None = None
    item_id: str | None = None
    field: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


class _Collector:
    def __init__(self) -> None:
        self.issues: list[BankIssue] = []

    def add(self, code: str, message: str, *, subtest: str | None = None,
            item_id: str | None = None, field: str | None = None) -> None:
        self.issues.append(BankIssue(code, message, subtest, item_id, field))


def _localized_text(c: _Collector, item: dict, field: str, *, subtest: str, item_id: str) -> None:
    value = item.get(field)
    if not isinstance(value, dict):
        c.add("missing_field", f"Поле «{field}» должно содержать ru и kk", subtest=subtest, item_id=item_id, field=field)
        return
    for loc in LOCALES:
        text = value.get(loc)
        if not isinstance(text, str) or not text.strip():
            c.add("missing_translation", f"Нет текста «{field}» для {loc}", subtest=subtest, item_id=item_id, field=field)


def _localized_list(
    c: _Collector, item: dict, field: str, *, subtest: str, item_id: str,
    min_len: int = 1, exact_len: int | None = None, same_length: bool = True,
) -> dict[str, list] | None:
    value = item.get(field)
    if not isinstance(value, dict):
        c.add("missing_field", f"Поле «{field}» должно содержать ru и kk", subtest=subtest, item_id=item_id, field=field)
        return None
    lists: dict[str, list] = {}
    for loc in LOCALES:
        raw = value.get(loc)
        if not isinstance(raw, list) or any(not isinstance(v, str) or not v.strip() for v in raw):
            c.add("missing_translation", f"Список «{field}» для {loc} пуст или содержит пустые значения",
                  subtest=subtest, item_id=item_id, field=field)
            return None
        lists[loc] = raw
    if same_length and len(lists["ru"]) != len(lists["kk"]):
        c.add("locale_structure_mismatch", f"В «{field}» разное число элементов в ru и kk",
              subtest=subtest, item_id=item_id, field=field)
        return None
    size = min(len(lists["ru"]), len(lists["kk"]))
    if exact_len is not None and size != exact_len:
        c.add("wrong_item_shape", f"«{field}» должно содержать ровно {exact_len} элемента(ов)",
              subtest=subtest, item_id=item_id, field=field)
    elif size < min_len:
        c.add("wrong_item_shape", f"«{field}» должно содержать не меньше {min_len} элементов",
              subtest=subtest, item_id=item_id, field=field)
    for loc in LOCALES:
        normalized = [v.strip().casefold() for v in lists[loc]]
        if len(set(normalized)) != len(normalized):
            c.add("duplicate_value", f"В «{field}» ({loc}) есть повторяющиеся значения",
                  subtest=subtest, item_id=item_id, field=field)
    return lists


def _check_single_choice(c: _Collector, item: dict, *, subtest: str, item_id: str) -> None:
    options = _localized_list(c, item, "options", subtest=subtest, item_id=item_id, min_len=2)
    answer = item.get("answer")
    if not isinstance(answer, dict) or options is None:
        if options is not None:
            c.add("missing_key", "У задания нет ключа", subtest=subtest, item_id=item_id, field="answer")
        return
    positions = {}
    for loc in LOCALES:
        if answer.get(loc) not in options[loc]:
            c.add("key_not_in_options", f"Ключ ({loc}) отсутствует среди вариантов",
                  subtest=subtest, item_id=item_id, field="answer")
            return
        positions[loc] = options[loc].index(answer[loc])
    if positions["ru"] != positions["kk"]:
        c.add("key_locale_mismatch", "Ключ указывает на разные варианты в ru и kk",
              subtest=subtest, item_id=item_id, field="answer")


def _check_pick_pair(c: _Collector, item: dict, *, subtest: str, item_id: str) -> None:
    words = _localized_list(c, item, "words", subtest=subtest, item_id=item_id, exact_len=6)
    answer = _localized_list(c, item, "answer", subtest=subtest, item_id=item_id, exact_len=2)
    if words is None or answer is None:
        return
    positions = {}
    for loc in LOCALES:
        if not set(answer[loc]).issubset(words[loc]):
            c.add("key_not_in_options", f"Ключ ({loc}) содержит слово не из списка",
                  subtest=subtest, item_id=item_id, field="answer")
            return
        positions[loc] = sorted(words[loc].index(w) for w in answer[loc])
    if positions["ru"] != positions["kk"]:
        c.add("key_locale_mismatch", "Ключ указывает на разные слова в ru и kk",
              subtest=subtest, item_id=item_id, field="answer")


def _check_open_text(c: _Collector, item: dict, *, subtest: str, item_id: str) -> None:
    _localized_list(c, item, "pair", subtest=subtest, item_id=item_id, exact_len=2)
    # Synonym tiers are per-language vocabularies — RU and KK may accept a
    # different number of phrasings for the same concept.
    tiers = {
        tier: _localized_list(c, item, tier, subtest=subtest, item_id=item_id, same_length=False)
        for tier in ("score_2", "score_1")
    }
    if tiers["score_2"] is None or tiers["score_1"] is None:
        return
    for loc in LOCALES:
        overlap = {v.strip().casefold() for v in tiers["score_2"][loc]} & {v.strip().casefold() for v in tiers["score_1"][loc]}
        if overlap:
            c.add("ambiguous_tiers", f"Ответ встречается и в 2-балльном, и в 1-балльном списке ({loc})",
                  subtest=subtest, item_id=item_id, field="score_1")


def _check_chain(c: _Collector, item: dict, *, subtest: str, item_id: str) -> None:
    _localized_list(c, item, "concepts", subtest=subtest, item_id=item_id, min_len=3)


def _check_number_pair(c: _Collector, item: dict, *, subtest: str, item_id: str) -> None:
    sequence, answer = item.get("sequence"), item.get("answer")
    if not isinstance(sequence, list) or len(sequence) < 3 or not all(isinstance(n, int) for n in sequence):
        c.add("wrong_item_shape", "Ряд должен содержать не меньше 3 целых чисел",
              subtest=subtest, item_id=item_id, field="sequence")
    if not isinstance(answer, list) or len(answer) != 2 or not all(isinstance(n, int) for n in answer):
        c.add("missing_key", "Ключ ряда — ровно 2 целых числа", subtest=subtest, item_id=item_id, field="answer")


def _check_quick_instruction(c: _Collector, item: dict, *, subtest: str, item_id: str) -> None:
    _localized_text(c, item, "instruction", subtest=subtest, item_id=item_id)
    if item.get("answer_format") not in LABILITY_ANSWER_FORMATS:
        c.add("wrong_item_shape", "Неизвестный формат ответа команды", subtest=subtest, item_id=item_id, field="answer_format")
    has_answer, has_dynamic = "answer" in item, "dynamic" in item
    if has_answer == has_dynamic:
        c.add("missing_key", "У команды должен быть либо статический ключ, либо динамическое правило",
              subtest=subtest, item_id=item_id, field="answer")
        return
    if has_dynamic:
        _localized_list(c, item, "options", subtest=subtest, item_id=item_id, exact_len=2)
        if item["dynamic"] not in LABILITY_DYNAMIC_KINDS:
            c.add("wrong_item_shape", "Неизвестное динамическое правило", subtest=subtest, item_id=item_id, field="dynamic")
        return
    options = _localized_list(c, item, "options", subtest=subtest, item_id=item_id, exact_len=2)
    if options is None:
        return
    answer = item["answer"]
    if not isinstance(answer, dict) or any(answer.get(loc) not in options[loc] for loc in LOCALES):
        c.add("key_not_in_options", "Ключ команды отсутствует среди вариантов", subtest=subtest, item_id=item_id, field="answer")
    elif options["ru"].index(answer["ru"]) != options["kk"].index(answer["kk"]):
        c.add("key_locale_mismatch", "Ключ указывает на разные варианты в ru и kk", subtest=subtest, item_id=item_id, field="answer")


_ITEM_CHECKS = {
    "single_choice": _check_single_choice,
    "pick_pair": _check_pick_pair,
    "open_text_tiers": _check_open_text,
    "chain_links": _check_chain,
    "number_pair": _check_number_pair,
    "quick_instruction": _check_quick_instruction,
}

# Content fields each subtest key needs beyond what its scoring method checks.
_EXTRA_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "awareness": (("text", "scalar"),),
    "analogies": (("third", "scalar"), ("pair", "pair")),
}


def _check_item_meta(c: _Collector, bank: AsturBank, subtest_key: str, item: dict, item_id: str) -> None:
    if item.get("difficulty") not in (None, *DIFFICULTIES):
        c.add("wrong_item_shape", "Уровень сложности: easy / medium / hard", subtest=subtest_key, item_id=item_id, field="difficulty")
    if item.get("review_status", "unreviewed") not in REVIEW_STATUSES:
        c.add("wrong_item_shape", "Статус проверки: unreviewed / reviewed", subtest=subtest_key, item_id=item_id, field="review_status")
    if not isinstance(item.get("skill"), str) or not item["skill"].strip():
        c.add("missing_field", "У задания не указан проверяемый навык", subtest=subtest_key, item_id=item_id, field="skill")
    if subtest_key in SUBJECT_TAGGED_KEYS and item.get("subject") not in bank.subjects:
        c.add("missing_field", "У задания не указана предметная область", subtest=subtest_key, item_id=item_id, field="subject")


def _check_key_confirmations(
    c: _Collector, bank: AsturBank, base: AsturBank, confirmed_item_ids: set[str]
) -> None:
    base_items = {item["item_id"]: item for s in base.subtests for item in s.items}
    for subtest in bank.subtests:
        for item in subtest.items:
            previous = base_items.get(item.get("item_id"))
            if previous is None or item["item_id"] in confirmed_item_ids:
                continue
            changed = [f for f in KEY_DEFINING_FIELDS if item.get(f) != previous.get(f)]
            if changed:
                c.add("key_confirmation_required",
                      f"Изменены {', '.join(changed)} — подтвердите ключ задания",
                      subtest=subtest.key, item_id=item["item_id"], field=changed[0])


def _check_stimulus(c: _Collector, item: dict, *, subtest: str, item_id: str) -> None:
    known = stimulus_manifest().get(item_id)
    if known is None:
        c.add("unknown_stimulus", "Для задания нет изображений в манифесте стимулов", subtest=subtest, item_id=item_id)
        return
    pinned = item.get("stimulus")
    if pinned is not None and pinned != known:
        c.add("stimulus_mismatch", "Изображения задания не совпадают с манифестом (путь или контрольная сумма)",
              subtest=subtest, item_id=item_id, field="stimulus")
    letters = sorted(known["options"])
    options = item.get("options") or {}
    if any(sorted(options.get(loc) or []) != letters for loc in LOCALES):
        c.add("stimulus_mismatch", "Варианты ответа должны совпадать с буквами изображений",
              subtest=subtest, item_id=item_id, field="options")


def _check_review(c: _Collector, item: dict, *, subtest: str, item_id: str) -> None:
    if item.get("difficulty") not in DIFFICULTIES:
        c.add("review_required", "Укажите уровень сложности", subtest=subtest, item_id=item_id, field="difficulty")
    if item.get("review_status") != "reviewed":
        c.add("review_required", "Задание не проверено вторым участником команды",
              subtest=subtest, item_id=item_id, field="review_status")
    explanation = (item.get("key_explanation") or {}).get("ru") or ""
    if subtest in KEY_EXPLANATION_REQUIRED_KEYS and not explanation.strip():
        c.add("review_required", "Добавьте объяснение ключа", subtest=subtest, item_id=item_id, field="key_explanation")


def validate_bank(
    document: dict,
    *,
    base: AsturBank | None = None,
    confirmed_item_ids: set[str] | None = None,
    require_review: bool = True,
) -> list[BankIssue]:
    c = _Collector()
    try:
        bank = parse_bank(document)
    except ValidationError as exc:
        for err in exc.errors():
            c.add("invalid_structure", f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}")
        return c.issues

    if bank.lability_item_limit_ms <= 0:
        c.add("invalid_timer", "Лимит на быструю команду должен быть положительным", field="lability_item_limit_ms")
    for code, names in bank.subjects.items():
        if any(not (names.get(loc) or "").strip() for loc in LOCALES):
            c.add("missing_translation", f"Нет названия предметной области «{code}» для ru или kk", field="subjects")

    keys = [s.key for s in bank.subtests]
    numbers = [s.number for s in bank.subtests]
    if sorted(keys) != sorted(METHOD_BY_KEY) or len(set(keys)) != len(keys):
        c.add("invalid_structure", f"Банк должен содержать ровно субтесты: {', '.join(sorted(METHOD_BY_KEY))}")
    if len(set(numbers)) != len(numbers):
        c.add("invalid_structure", "Номера субтестов повторяются")

    seen_ids: set[str] = set()
    for subtest in bank.subtests:
        expected_method = METHOD_BY_KEY.get(subtest.key)
        if expected_method is not None and subtest.scoring_method != expected_method:
            c.add("invalid_structure", f"Субтест «{subtest.key}» должен использовать метод {expected_method}", subtest=subtest.key)
            continue
        for loc in LOCALES:
            for field in ("name", "instruction"):
                if not (getattr(subtest, field).get(loc) or "").strip():
                    c.add("missing_translation", f"Нет «{field}» субтеста для {loc}", subtest=subtest.key, field=field)
        if subtest.scoring_method == "quick_instruction":
            if subtest.time_limit_sec is not None:
                c.add("invalid_timer", "Быстрые команды не имеют общего таймера", subtest=subtest.key)
            if len(subtest.items) < 2 or len(subtest.items) % 2:
                c.add("wrong_item_count", "Число быстрых команд должно быть чётным (сравнение половин)", subtest=subtest.key)
        elif not subtest.time_limit_sec or subtest.time_limit_sec <= 0:
            c.add("invalid_timer", "У субтеста должен быть положительный таймер", subtest=subtest.key)
        if not subtest.items:
            c.add("wrong_item_count", "В субтесте нет заданий", subtest=subtest.key)

        for position, item in enumerate(subtest.items, start=1):
            item_id = item.get("item_id")
            if not isinstance(item_id, str) or not item_id.strip():
                c.add("missing_item_id", f"У задания №{position} нет item_id", subtest=subtest.key)
                continue
            if item_id in seen_ids:
                c.add("duplicate_item_id", f"item_id «{item_id}» повторяется", subtest=subtest.key, item_id=item_id)
            seen_ids.add(item_id)
            _check_item_meta(c, bank, subtest.key, item, item_id)
            for field, kind in _EXTRA_FIELDS.get(subtest.key, ()):
                if kind == "scalar":
                    _localized_text(c, item, field, subtest=subtest.key, item_id=item_id)
                else:
                    _localized_list(c, item, field, subtest=subtest.key, item_id=item_id, exact_len=2)
            _ITEM_CHECKS[subtest.scoring_method](c, item, subtest=subtest.key, item_id=item_id)
            if subtest.key in STIMULUS_KEYS:
                _check_stimulus(c, item, subtest=subtest.key, item_id=item_id)
            if require_review:
                _check_review(c, item, subtest=subtest.key, item_id=item_id)

    if base is not None:
        _check_key_confirmations(c, bank, base, confirmed_item_ids or set())
    return c.issues
