"""
Backfill for university-cards-ux-fix-plan.md §2: Program.cost_label
sometimes shows a master's-only rate or a domestic/subsidized-citizen rate
that doesn't apply to a Kazakhstani (non-EU/non-citizen, bachelor's-seeking)
applicant -- e.g. NTU Singapore's "17 000 - 38 000 SGD в год (с субсидией
Tuition Grant)", which is the Singapore-citizen-subsidized rate shown with
no indication it doesn't apply to a foreign school leaver.

Built from a read-only keyword audit (see university-cards-ux-fix-plan.md
section 2) that pulled every Program row whose cost_label/description/
who_its_for matched: магистратур, master, граждан, citizen, subsidy,
субсиди, резидент, resident -- then hand-classified each distinct value.

Two kinds of fix, matching the plan's two documented sub-cases:
  - REWRITE: the same free-text field also has a clean bachelor's/
    international figure -- keep only that, drop the master's/domestic
    clause.
  - HONEST_NOTE: only the master's/subsidized/domestic figure exists, no
    international bachelor's number anywhere in the text -- replace with an
    honest "ask the university" note rather than inventing a number.

Also corrects/clears Program.cost_per_year_min/max/cost_currency where
those numeric fields (parsed separately by scripts/parse_cost_label.py,
see docs/university-module-fix-plan.md A6) encode the same wrong figure --
discovered live: University of Waterloo's numeric fields hold 47500/47500
CAD, which is actually the *master's* MActSc figure, not the 45500-48000
CAD bachelor's range that the same cost_label text states right next to it.

Deliberately NOT included here (left for human judgement, see the report
this script's dry-run output was attached to):
  - Rows where "для граждан вне ЕС/ЕЭЗ" etc. is already the correct
    international rate (Kazakhstan is non-EU) -- false positives, e.g.
    Copenhagen Business School, Wageningen, TU Munich (semester-fee-only
    row), University of Hohenheim, Johannes Gutenberg Mainz.
  - Rows where the same number covers both bachelor's and master's, so
    nothing is actually misleading (Politecnico di Milano, China University
    of Petroleum Beijing, Tsinghua, National Institute of Dramatic Art).
  - Genuinely ambiguous rows: NUS variants where the bachelor's figure
    itself may already be a post-Tuition-Grant (subsidized) number with no
    unsubsidized figure stated; University of Toronto's OISE range; Gubkin
    (unclear which of two RUB figures the leading USD conversion matches);
    Toronto Metropolitan University; the Sorbonne Nouvelle interpreting
    program (price is accurate, but the program itself may be graduate-only
    -- a plan-section-5 concern, not a pricing one).
  - description/who_its_for hits that mention "master"/"магистратура" as
    narrative context (e.g. "Columbia Journalism School's Master of
    Science...") without stating a price -- nothing to rewrite here; these
    are flagged in the report as possibly relevant to plan section 5
    (whether these universities belong on this profession's card at all).

Dry-run by default -- prints every row that would change, does not write
anything. Pass --apply to actually UPDATE the database.

Run inside the api container (docker cp this file in first — the API
container doesn't live-mount the repo):
  docker exec profy-backend-api-1 python /tmp/backfill_strip_masters_domestic_cost.py [--apply]
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, "/app")  # matches when run via docker cp to /tmp inside the api container

from sqlalchemy import or_, select

from app.database import async_session
from app.models.program import Program
from app.models.university import University

HONEST_NOTE = "Стоимость для иностранных студентов уточняйте на сайте вуза"

AUDIT_KEYWORDS = [
    "магистратур", "master", "граждан", "citizen", "subsidy", "субсиди", "резидент", "resident",
]


# Each rule: (university_name, [required substrings all present in cost_label],
#             new_cost_label, numeric_action)
# numeric_action: "clear" -> null out min/max/currency
#                 ("set", min, max, currency) -> overwrite with these
#                 "keep" -> leave numeric fields as-is
RULES: list[tuple[str, list[str], str, object]] = [
    # --- sub-case 1: strip the master's clause, keep the bachelor's/international figure ---
    (
        "Aalto University",
        ["бакалавриат для иностранцев", "магистратура"],
        "€12 000–15 000 в год (бакалавриат для иностранцев)",
        "clear",
    ),
    (
        "University of Edinburgh",
        ["26 500", "37 500", "магистратура"],
        "26 500 – 37 500 GBP в год (бакалавриат)",
        "clear",
    ),
    (
        "University of Melbourne",
        ["38 000", "58 000", "AUD", "магистратура"],
        "38 000 – 58 000 AUD в год (бакалавриат)",
        "clear",
    ),
    (
        "University of Toronto",
        ["55 000", "75 000", "CAD", "магистратура"],
        "55 000 – 75 000 CAD в год (бакалавриат)",
        "clear",
    ),
    (
        "Technical University of Munich (TUM)",
        ["€2000", "€3000", "магистратура"],
        "€2000–€3000 за семестр (бакалавриат) для студентов вне ЕС",
        "clear",
    ),
    (
        "University of Surrey — School of Hospitality and Tourism Management",
        ["22 900", "27 000", "магистратура"],
        "22 900–27 000 £ в год (бакалавриат) для иностранных студентов",
        "clear",
    ),
    (
        "National University of Singapore — NUS Business School",
        ["MSc Business Analytics"],
        "около 40 000–50 000 SGD в год для иностранных студентов бакалавриата",
        "keep",  # numeric already matches this retained bachelor's range (40000/50000 SGD)
    ),
    (
        "University of Waterloo",
        ["45 500", "48 000", "MActSc"],
        "около 45 500–48 000 CAD за первый год бакалавриата для иностранных студентов",
        ("set", 45500, 48000, "CAD"),  # was wrongly 47500/47500 (the MASTER'S figure)
    ),
    (
        "Indian Institute of Management Ahmedabad",
        ["граждан Индии", "иностранцев"],
        "Для иностранных студентов — от ~5 млн INR за программу",
        "clear",
    ),
    # --- sub-case 2: only a master's/subsidized/domestic figure exists -> honest note ---
    (
        "Hebrew University of Jerusalem",
        ["магистратуры", "israelских"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "HEC Paris",
        ["Master in International Finance"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Escola de Administração de Empresas de São Paulo, Fundação Getulio Vargas",
        ["магистратуры/MBA"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "IE Business School",
        ["Master in Management", "MBA"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Nanyang Technological University (NTU)",
        ["субсидией Tuition Grant"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "National University of Singapore, Department of Biological Sciences",
        ["MSc Biotechnology"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Sveriges lantbruksuniversitet (Swedish University of Agricultural Sciences)",
        ["программы магистратуры"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Technion – Israel Institute of Technology",
        ["магистратура"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "The University of Tokyo",
        ["магистратуры"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Cornell University — ILR School (School of Industrial and Labor Relations)",
        ["MILR/EMHRM"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Delft University of Technology (TU Delft)",
        ["17 300", "25 600", "магистратуре"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Delft University of Technology",  # separate University row, no "(TU Delft)" suffix
        ["25,633"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Erasmus University Rotterdam",
        ["18 000", "24 000", "магистратуры"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Ivey Business School",
        ["программ магистратуры", "международных студентов"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "National University of Singapore — NUS Business School",
        ["65 000", "за программу магистратуры"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "National University of Singapore — Supply Chain Management",
        ["магистратура Supply Chain Management"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Norwegian University of Science and Technology",
        ["магистратура на английском"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "WHU – Otto Beisheim School of Management",
        ["программ магистратуры"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Cranfield University",
        ["за программы магистратуры"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "KTH Royal Institute of Technology",
        ["программ магистратуры", "неEU граждане"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "University of Birmingham — Birmingham Centre for Railway Research and Education",
        ["магистратура Railway Systems Engineering"],
        HONEST_NOTE,
        "clear",
    ),
    (
        "Universidade de São Paulo",
        ["Бесплатно для граждан Бразилии"],
        "Иностранным студентам — по договору с университетом (уточняйте стоимость на сайте вуза)",
        "clear",
    ),
]


async def main() -> None:
    apply = "--apply" in sys.argv

    async with async_session() as db:
        conditions = [Program.cost_label.ilike(f"%{kw}%") for kw in AUDIT_KEYWORDS]
        rows = (
            (
                await db.execute(
                    select(Program, University.name)
                    .join(University, Program.university_id == University.id)
                    .where(or_(*conditions))
                )
            )
            .all()
        )

        matched_rule_counts = [0] * len(RULES)
        changed = 0
        unmatched_but_flagged = 0

        for program, uni_name in rows:
            label = program.cost_label or ""
            rule_hit = None
            for idx, (rule_uni, markers, new_value, numeric_action) in enumerate(RULES):
                if uni_name == rule_uni and all(m in label for m in markers):
                    rule_hit = (idx, new_value, numeric_action)
                    break

            if rule_hit is None:
                # Keyword-matched but no rule -> false positive or ambiguous case
                # we deliberately left for human judgement (see module docstring
                # and the accompanying audit report). Not printed here to keep
                # dry-run output focused on actual proposed changes.
                unmatched_but_flagged += 1
                continue

            idx, new_value, numeric_action = rule_hit
            matched_rule_counts[idx] += 1

            if new_value == label and numeric_action == "keep":
                continue  # already correct, nothing to do

            changed += 1
            tag = "[updating]" if apply else "[would update]"
            print(f"\n{tag} {uni_name} | Program.id={program.id} | Program.name={program.name!r}")
            print(f"  cost_label: {label!r}")
            print(f"           -> {new_value!r}")
            if numeric_action == "clear" and (
                program.cost_per_year_min is not None
                or program.cost_per_year_max is not None
                or program.cost_currency is not None
            ):
                print(
                    f"  cost_per_year_min/max/currency: "
                    f"{program.cost_per_year_min!r}/{program.cost_per_year_max!r}/{program.cost_currency!r} -> None/None/None"
                )
            elif isinstance(numeric_action, tuple):
                new_min, new_max, new_cur = numeric_action[1], numeric_action[2], numeric_action[3]
                print(
                    f"  cost_per_year_min/max/currency: "
                    f"{program.cost_per_year_min!r}/{program.cost_per_year_max!r}/{program.cost_currency!r} "
                    f"-> {new_min!r}/{new_max!r}/{new_cur!r}"
                )

            if apply:
                program.cost_label = new_value
                if numeric_action == "clear":
                    program.cost_per_year_min = None
                    program.cost_per_year_max = None
                    program.cost_currency = None
                elif isinstance(numeric_action, tuple):
                    program.cost_per_year_min = numeric_action[1]
                    program.cost_per_year_max = numeric_action[2]
                    program.cost_currency = numeric_action[3]

        print("\n" + "=" * 100)
        for idx, (rule_uni, markers, new_value, _) in enumerate(RULES):
            print(f"rule[{idx}] {rule_uni} (markers={markers}) matched {matched_rule_counts[idx]} row(s)")

        print(f"\n{changed} of {len(rows)} keyword-matched rows would change.")
        print(
            f"{unmatched_but_flagged} keyword-matched rows had no fix rule -- these are the "
            f"false-positive / ambiguous cases from the audit report, intentionally left alone."
        )

        if apply:
            await db.commit()
            print("Committed.")
        else:
            print("Dry run — nothing written. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main())
