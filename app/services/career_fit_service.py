"""«Почему тебе подходит» for the student's careers.

Two halves, so a report's text never depends on the language it was built in:

- `build_career_fit` (report generation and the backfill) decides —
  locale-free — which interest types the student and the profession share
  and which reasons apply, and is stored on `AnalysisResult.career_fit`.
- `render_career` (every GET) turns one stored entry into text in the row's
  language: the fact half is the vetted «Сильные стороны» card title, the
  profession half is that career's own catalog skill from the row's
  `careers` snapshot, so the kk row reads kk on both sides.

A reason pairs one fact from the same vetted pool as the strength cards
(`student_strengths_service.vetted_candidates`, lie-scale rule included)
with one skill of the profession tagged with a shared axis
(app/data/career_fit_skill_axes.json). A skill whose current catalog text no
longer equals the tagged text is never paired. Subjects pair the student's
easy/liked subjects with the profession's `subjects_to_develop` only when a
shared axis also points to a concrete skill of that profession that no fact
reason has named yet.

Interest fallback: only the student's confirmed RIASEC interests (the same
bar as the strength cards — high and not contradicted by aversion answers)
that sit above the average for BOTH the student and the profession
(`onet_vector`) — the types that actually raise the Pearson match the careers
are ranked by. A type that is low for both also raises the correlation, but
"you both don't like art" is no reason; and a near-flat profile has no
interest to call «ближе всего».

`why` is one connected text over every concrete reason («… А ещё … Кроме
того, …»). Without a concrete reason it falls back to the shared-interest
line (plus the profession's first skill), and without that to a profession
skill with an honest "not yet linked to your strengths" note.
"""
import logging
import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CareerFitRules, career_fit_rules
from app.i18n.catalog import tr
from app.models.analysis_result import AnalysisResult
from app.models.direction import Direction
from app.schemas.result_v2 import StudentFitReason
from app.schemas.student_strengths import StrengthCandidate, StrengthInputs
from app.services import student_strengths_service
from app.services.riasec_service import HOLLAND_ORDER

logger = logging.getLogger(__name__)

# Two-fact cards name two things at once — too vague to pair with one skill.
_UNPAIRED_CONTENT_KEYS = frozenset({"ddo.hybrid", "belbin.pair"})
_DDO_PREFIXES = frozenset({"ddo", "ddo_ability", "ddo_interest"})
_TRAILING_NOTE = re.compile(r"\s*\(.*\)\s*$")


# ── build (locale-free, stored) ──────────────────────────────────────────────


def shared_letters(
    profile: dict[str, float],
    vector: dict | None,
    holland_code: str,
    confirmed: list[str],
    rules: CareerFitRules = career_fit_rules,
) -> list[str]:
    """Confirmed RIASEC interests that raise this career's match."""
    if isinstance(vector, dict) and all(t in vector for t in HOLLAND_ORDER):
        mean_user = sum(float(profile.get(t, 0.0)) for t in HOLLAND_ORDER) / len(HOLLAND_ORDER)
        mean_job = sum(float(vector[t]) for t in HOLLAND_ORDER) / len(HOLLAND_ORDER)
        contribution = {
            t: (float(profile.get(t, 0.0)) - mean_user) * (float(vector[t]) - mean_job)
            for t in HOLLAND_ORDER
            if t in confirmed and float(profile.get(t, 0.0)) > mean_user and float(vector[t]) > mean_job
        }
        ranked = sorted(contribution, key=lambda t: (-contribution[t], HOLLAND_ORDER.index(t)))
        return ranked[: rules.max_letters]
    # No O*NET vector (ranked by the legacy code score): the code's own
    # letters the student confirmed, in the code's order.
    return [letter for letter in holland_code if letter in confirmed][: rules.max_letters]


def evidence_axes(evidence_id: str, rules: CareerFitRules = career_fit_rules) -> set[str]:
    prefix, separator, scale = evidence_id.partition(":")
    if separator and prefix in _DDO_PREFIXES:
        evidence_id = f"ddo:{scale}"
    return set(rules.evidence_axes.get(evidence_id, ()))


def subject_key(text: str, rules: CareerFitRules = career_fit_rules) -> str | None:
    """Canonical onboarding subject for a free-text subject, or None."""
    normalized = _TRAILING_NOTE.sub("", text.strip().lower()).strip()
    return rules.subject_aliases.get(normalized)


def fact_pool(inputs: StrengthInputs) -> list[StrengthCandidate]:
    """Pairable student facts, strongest grounding first.

    Start with every vetted candidate, then add the cautious interest-only
    cards that actually fill the visible «Сильные стороны» section. The
    latter matters for an ordinary/flat RIASEC profile: it may have no
    *confirmed-high* letter, while the report still truthfully says
    «тебе интересно разбираться…» as an exploratory observation. Career
    reasons may reuse that exact observation, but never turn it into an
    ability claim. Confirmed interests that did not fit into the five visible
    cards are added last under the same cautious wording."""
    pool = [
        c for c in student_strengths_service.vetted_candidates(inputs)
        if c.content_key not in _UNPAIRED_CONTENT_KEYS
    ]
    source_ids = {c.source_id for c in pool}
    pool += [
        c for c in student_strengths_service.select_strengths(inputs)
        if c.basis == "interest"
        and c.content_key not in _UNPAIRED_CONTENT_KEYS
        and c.source_id not in source_ids
    ]
    used = {e for c in pool for e in c.evidence_ids}
    letters = [letter for letter in inputs.riasec_confirmed if f"riasec:{letter}" not in used]
    pool += student_strengths_service.interest_candidates(inputs, letters)
    return [c for _, c in sorted(enumerate(pool), key=lambda pair: (pair[1].priority, pair[0]))]


def _skills(direction: Direction, rules: CareerFitRules) -> list[tuple[int, set[str]]]:
    tagged = rules.skill_axes.get(direction.slug, ())
    current = list((direction.skills_needed or {}).get("ru") or [])
    return [
        (index, set(tag.axes))
        for index, tag in enumerate(tagged)
        if tag.axes and index < len(current) and current[index] == tag.ru
    ]


def _fact_reasons(
    pool: list[StrengthCandidate], skills: list[tuple[int, set[str]]], rules: CareerFitRules
) -> list[dict]:
    """Greedy, strongest fact first: each fact and each skill backs at most
    one reason; among matching skills the widest overlap, then catalog order."""
    reasons: list[dict] = []
    used_facts: set[str] = set()
    used_skills: set[int] = set()
    for candidate in pool:
        if len(reasons) >= rules.max_fact_reasons:
            break
        if used_facts & set(candidate.evidence_ids):
            continue
        spoken = candidate.evidence_ids[:1] if candidate.source_type == "cross" else candidate.evidence_ids
        axes = set().union(*(evidence_axes(e, rules) for e in spoken))
        matches = [(index, len(skill_axes & axes)) for index, skill_axes in skills if index not in used_skills]
        matches = [m for m in matches if m[1] > 0]
        if not matches:
            continue
        index = min(matches, key=lambda m: (-m[1], m[0]))[0]
        reasons.append({
            "kind": "fact",
            "source_id": candidate.source_id,
            "content_key": candidate.content_key,
            "evidence_ids": list(candidate.evidence_ids),
            "skill_index": index,
        })
        used_facts |= set(candidate.evidence_ids)
        used_skills.add(index)
    return reasons


def _subject_reason(
    direction: Direction, inputs: StrengthInputs, rules: CareerFitRules, used_skills: set[int]
) -> dict | None:
    easy = {k for k in (subject_key(s, rules) for s in inputs.subjects_easy) if k}
    liked = {k for k in (subject_key(s, rules) for s in inputs.subjects_liked) if k}
    # A skill a fact reason already names is not repeated for the subject.
    skills = [(index, axes) for index, axes in _skills(direction, rules) if index not in used_skills]

    def reason(key: str, how: str) -> dict | None:
        axes = set(rules.subject_axes.get(key, ()))
        matches = [(index, len(skill_axes & axes)) for index, skill_axes in skills]
        matches = [match for match in matches if match[1] > 0]
        if not matches:
            # A subject alone produces the same vague sentence for unrelated
            # professions. Keep it only when we can name what it helps with in
            # this particular profession; otherwise a stronger fact/interest
            # or the honest profession-specific fallback should explain it.
            return None
        return {
            "kind": "subject",
            "subject": key,
            "how": how,
            "skill_index": min(matches, key=lambda match: (-match[1], match[0]))[0],
        }

    for text in (direction.subjects_to_develop or {}).get("ru") or []:
        key = subject_key(text, rules)
        if key in easy:
            matched = reason(key, "easy")
            if matched is not None:
                return matched
        if key in liked:
            matched = reason(key, "liked")
            if matched is not None:
                return matched
    return None


def build_career_fit(
    inputs: StrengthInputs,
    profile: dict[str, float],
    directions: Iterable[Direction],
    rules: CareerFitRules = career_fit_rules,
) -> dict:
    """The stored, locale-free «Почему тебе подходит» for a report's careers."""
    pool = fact_pool(inputs)
    careers: dict[str, dict] = {}
    # How often a fact already opened an earlier career's reasons: the one
    # used least goes first, so the list of cards doesn't open alike.
    opened: dict[str, int] = {}
    for direction in directions:
        reasons = _fact_reasons(pool, _skills(direction, rules), rules)
        reasons.sort(key=lambda r: opened.get(r["source_id"], 0))
        if reasons:
            opened[reasons[0]["source_id"]] = opened.get(reasons[0]["source_id"], 0) + 1
        used_skills = {r["skill_index"] for r in reasons}
        subject = _subject_reason(direction, inputs, rules, used_skills)
        if subject is not None:
            reasons.append(subject)
        careers[direction.slug] = {
            "letters": shared_letters(
                profile, direction.onet_vector, direction.holland_code, inputs.riasec_confirmed, rules
            ),
            "reasons": reasons[: rules.max_reasons],
        }
    return {"version": rules.version, "careers": careers}


def is_current(career_fit: dict | None, rules: CareerFitRules = career_fit_rules) -> bool:
    return bool(career_fit) and career_fit.get("version") == rules.version


async def _directions(slugs: list[str], db: AsyncSession) -> list[Direction]:
    if not slugs:
        return []
    found = {
        d.slug: d for d in (await db.execute(select(Direction).where(Direction.slug.in_(slugs)))).scalars().all()
    }
    return [found[s] for s in slugs if s in found]


async def build_for_rows(rows: list[AnalysisResult], db: AsyncSession) -> dict | None:
    """Fresh career fit for one assessment's report rows (all locales share
    it — it is locale-free), read from every instrument again — the
    backfill of reports built before it or under older rules."""
    if not rows:
        return None
    slugs = list(dict.fromkeys(c.get("slug") for row in rows for c in (row.careers or []) if c.get("slug")))
    inputs = await student_strengths_service.collect_inputs(rows[0].assessment_id, db)
    return build_career_fit(inputs, dict(rows[0].profile or {}), await _directions(slugs, db))


# ── render (per request, row locale) ─────────────────────────────────────────


def _join(items: list[str], conjunction: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + conjunction + items[-1]


def _lower_first(text: str) -> str:
    text = text.strip().rstrip(".")
    if len(text) > 1 and text[1].isupper():
        return text  # an acronym («SQL …») keeps its case
    return text[:1].lower() + text[1:]


def fact_title(content_key: str, evidence_ids: list[str], t: dict, overrides: dict | None = None) -> str | None:
    """The fact's wording in the current locale: the strength card title,
    or its career-specific replacement (`career_fit.fact_titles`)."""
    if overrides and content_key in overrides:
        return overrides[content_key]
    card = t["cards"].get(content_key)
    if not card:
        return None
    refs = [e.partition(":")[2] for e in evidence_ids]
    spheres = t["ddo_spheres"]
    params = {
        "sphere": spheres.get(refs[0], "") if refs else "",
        "spheres": t["list_conjunction"].join(spheres.get(r, "") for r in refs),
        "contribution": t["belbin_contributions"].get(refs[0], "") if refs else "",
    }
    try:
        return card["title"].format(**params)
    except (KeyError, IndexError):
        return None


def _profession_fallback(career: dict, t: dict) -> str:
    skills = list(career.get("skills_needed") or [])
    if skills and skills[0]:
        return t["reason_skill_fallback"].format(skill=_lower_first(skills[0]))
    return t["summary_general"]


def render_career(entry: dict | None, career: dict) -> tuple[str, list[StudentFitReason], list[str]]:
    """(why, reasons, comparison keys) for one career. `why` is never empty:
    up to two concrete reasons, then shared interests, then the general line.
    A career added by hand (no stored entry) and any unexpected stored shape
    use the general line: a report must always render."""
    if entry:
        try:
            return _render_career(entry, career)
        except Exception:  # noqa: BLE001
            logger.exception("career fit render failed for career=%s", career.get("slug"))
    t = tr("career_fit")
    return _profession_fallback(career, t), [], []


def _render_career(entry: dict, career: dict) -> tuple[str, list[StudentFitReason], list[str]]:
    t = tr("career_fit")
    strengths = tr("student_strengths")
    subjects = tr("subjects")["school_subjects"]
    letters = [letter for letter in entry.get("letters") or [] if letter in t["letters"]]
    interest_fallback = (
        t["summary"].format(items=_join([t["letters"][letter] for letter in letters], t["list_conjunction"]))
        if letters
        else t["summary_general"]
    )

    skills = list(career.get("skills_needed") or [])
    reasons: list[StudentFitReason] = []
    keys = [f"riasec:{letter}" for letter in letters]
    for stored in entry.get("reasons") or []:
        if stored.get("kind") == "fact":
            title = fact_title(
                stored.get("content_key", ""), list(stored.get("evidence_ids") or []), strengths, t["fact_titles"]
            )
            index = stored.get("skill_index")
            if not title or not isinstance(index, int) or not 0 <= index < len(skills) or not skills[index]:
                continue
            reasons.append(StudentFitReason(
                kind="fact",
                fact=title,
                text=t["reason_fact_skill"].format(fact=title, skill=_lower_first(skills[index])),
            ))
            keys.append(stored.get("source_id", ""))
        elif stored.get("kind") == "subject":
            subject = subjects.get(stored.get("subject", ""))
            how = stored.get("how")
            if not subject or how not in ("easy", "liked"):
                continue
            index = stored.get("skill_index")
            has_skill = isinstance(index, int) and 0 <= index < len(skills) and bool(skills[index])
            template = t[f"reason_subject_{how}_skill"] if has_skill else t[f"reason_subject_{how}"]
            params = {"subject": subject}
            if has_skill:
                params["skill"] = _lower_first(skills[index])
            reasons.append(StudentFitReason(
                kind="subject",
                fact=subject,
                text=template.format(**params),
            ))
            keys.append(f"subject:{stored['subject']}")
    # `why` is what the student reads first, so make it about this particular
    # profession rather than repeating the same RIASEC combination across the
    # whole top-10 — one connected text over every reason, so nothing reads
    # as a separate verdict next to it.
    why = interest_fallback
    if reasons:
        connectives = [t["reason_additional"], t["reason_more"]]
        why = " ".join(
            [reasons[0].text]
            + [
                connectives[min(i, len(connectives) - 1)].format(text=_lower_first(reason.text))
                for i, reason in enumerate(reasons[1:])
            ]
        )
    elif skills:
        if letters:
            why += " " + t["profession_skill"].format(skill=_lower_first(skills[0]))
        else:
            why = _profession_fallback(career, t)
    return why, reasons, [k for k in keys if k]
