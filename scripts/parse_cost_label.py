"""Parses Program.cost_label / cost_text free text into a numeric
(min, max, currency) triple where the text is unambiguous, for
Program.cost_per_year_min/max/currency (see docs/university-module-fix-plan.md A6).

Deliberately conservative: only accepts a value when there's exactly ONE
plausible year-denominated tuition figure in the string. Real cost_label
text in this dataset regularly contains a SECOND, different number for
something else entirely (living costs, a different program level, a
non-EU/non-resident rate, a parenthetical currency conversion) — e.g.
"26 000 – 45 000 CNY в год (около 3 600 – 6 200 USD)" states the real figure
in CNY with a USD conversion note; picking whichever currency word appears
anywhere in the string (rather than the one actually attached to the parsed
number) silently produces a right-looking number in the wrong currency —
caught by testing this exact case during development, see git history.
Anything with more than one distinct "в год" figure, a semester-only figure
with no annual equivalent stated, or a "free tuition" clause mixed with a
real fee is left unparsed (None) rather than guessed at — a missing number
is recoverable later, a wrong one on a live product page is not.
"""
import re

CURRENCY_PATTERNS: list[tuple[str, str]] = [
    (r"\bKZT\b|тенге", "KZT"),
    (r"австралийских\s+доллар", "AUD"),
    (r"канадских\s+доллар", "CAD"),
    (r"сингапурских\s+доллар", "SGD"),
    (r"гонконгских\s+доллар", "HKD"),
    (r"новозеландских\s+доллар", "NZD"),
    (r"\bUSD\b|долларов?\s+США|американских\s+доллар", "USD"),
    (r"\bEUR\b|евро", "EUR"),
    (r"\bGBP\b|фунтов", "GBP"),
    (r"\bCHF\b|франков", "CHF"),
    (r"\bCNY\b|юаней", "CNY"),
    (r"\bAUD\b", "AUD"),
    (r"\bCAD\b", "CAD"),
    (r"\bSGD\b", "SGD"),
    (r"\bHKD\b", "HKD"),
    (r"\bSEK\b|шведских\s+крон", "SEK"),
    (r"\bNOK\b|норвежских\s+крон", "NOK"),
    (r"\bJPY\b|иен(?:\b|ы|ой)|йен(?:\b|ы|ой)", "JPY"),
    (r"\bZAR\b|рэндов|рандов", "ZAR"),
    (r"\bBRL\b|реалов|реалов\b", "BRL"),
    (r"\bKRW\b|(?<!\d )вон\b", "KRW"),
]

NUMBER = r"\d[\d\s]*(?:[.,]\d+)?"
# A single number or dash-range, then a short currency phrase (<=4 words, no
# digits in it so it can't accidentally swallow a second amount), then an
# explicit annual marker. The currency is resolved ONLY from this captured
# phrase — never from elsewhere in the string — so a parenthetical
# conversion note elsewhere can't hijack the result (see module docstring).
AMOUNT_RE = re.compile(
    rf"(?:от\s+)?(?P<lo>{NUMBER})\s*(?:[-–—]|до)\s*(?P<hi>{NUMBER})?\s*"
    rf"(?P<currency>(?:[A-Za-zА-Яа-яё.]+\s*){{1,4}}?)\s*"
    rf"(?:в\s+год\b|/\s*год\b|годовой\b)",
    re.IGNORECASE | re.UNICODE,
)
# Single figure, no range, e.g. "18 900 GBP в год".
SINGLE_RE = re.compile(
    rf"(?P<lo>{NUMBER})\s*"
    rf"(?P<currency>(?:[A-Za-zА-Яа-яё.]+\s*){{1,4}}?)\s*"
    rf"(?:в\s+год\b|/\s*год\b|годовой\b)",
    re.IGNORECASE | re.UNICODE,
)


def _resolve_currency(phrase: str) -> str | None:
    for pattern, code in CURRENCY_PATTERNS:
        if re.search(pattern, phrase, re.IGNORECASE):
            return code
    return None


def _to_num(s: str | None) -> float | None:
    if not s:
        return None
    cleaned = re.sub(r"\s", "", s).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_cost_label(text: str) -> tuple[float, float, str] | None:
    if not text:
        return None

    range_matches = list(AMOUNT_RE.finditer(text))
    single_matches = [
        m for m in SINGLE_RE.finditer(text)
        if not any(m.start() >= r.start() and m.end() <= r.end() for r in range_matches)
    ]
    matches = range_matches + single_matches
    if len(matches) != 1:
        return None  # zero, or more than one distinct "в год" figure -> refuse to guess

    m = matches[0]
    currency = _resolve_currency(m.group("currency"))
    if currency is None:
        return None

    lo = _to_num(m.group("lo"))
    hi = _to_num(m.groupdict().get("hi")) or lo
    if lo is None:
        return None
    if lo > hi:
        lo, hi = hi, lo
    # Sanity floor — catches accidental capture of a stray small number
    # (e.g. a year digit) as if it were a currency amount.
    if lo < 50:
        return None

    return (lo, hi, currency)


if __name__ == "__main__":
    import sys

    ok = skipped = 0
    with open(sys.argv[1], encoding="utf-8") as f:
        for line in f:
            text = line.rstrip("\n")
            if not text:
                continue
            result = parse_cost_label(text)
            if result:
                ok += 1
                print(f"OK    {result}  <=  {text}")
            else:
                skipped += 1
                print(f"SKIP  {text}")
    print(f"\nparsed: {ok}, skipped: {skipped}, total: {ok + skipped}", file=sys.stderr)
