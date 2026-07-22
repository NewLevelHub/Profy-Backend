"""
Specialty alias map — seed-only curation helper.

Maps informal query terms (e.g. "devops", "sre") to one or more canonical
akinator specialty/section slugs from seed_akinator_content.py.

Rules:
  - Only slugs that appear in SECTIONS or SPECIALTIES are allowed here.
  - Module-level assertions enforce this at import time.
  - This file is NEVER imported from app/ — it exists only to help seed
    scripts and the lookup CLI tool (scripts/lookup_specialty_alias.py).

NEVER add: invented slugs, deprecated slugs, or slugs from a different
source of truth. Add entries only when seed data genuinely covers a
program that maps to multiple specialties.
"""

import os
import sys

# Allow running this file directly from the project root inside Docker.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.seed_akinator_content import SECTIONS, SPECIALTIES  # noqa: E402

# ---------------------------------------------------------------------------
# Alias map: informal term -> list of canonical akinator slugs
# Keys are lower-case; values must all exist in SECTIONS or SPECIALTIES.
# ---------------------------------------------------------------------------

SPECIALTY_ALIASES: dict[str, list[str]] = {
    # --- IT и данные ---
    # DevOps sits between software engineering and IT-infrastructure/security.
    "devops": ["software-engineer", "it-infrastructure-security"],
    # SRE (Site Reliability Engineering) is operations-heavy; closest specialty
    # is IT-infrastructure-security; also overlaps software-engineer.
    "sre": ["it-infrastructure-security", "software-engineer"],
    # Cloud engineering: infrastructure + software development.
    "cloud-engineer": ["it-infrastructure-security", "software-engineer"],
    # Cybersecurity / information security.
    "cybersecurity": ["it-infrastructure-security"],
    "infosec": ["it-infrastructure-security"],
    "network-engineer": ["it-infrastructure-security"],
    "sysadmin": ["it-infrastructure-security"],
    # Machine learning / AI engineering — primarily data-science, but also
    # software-engineer (writing production ML systems).
    "ml-engineer": ["data-science", "software-engineer"],
    "ai-engineer": ["data-science", "software-engineer"],
    "data-engineer": ["data-science", "software-engineer"],
    "bi-analyst": ["data-science"],
    "data-analyst": ["data-science"],
    # Full-stack / mobile are pure software engineering tracks.
    "fullstack": ["software-engineer"],
    "mobile-developer": ["software-engineer"],
    "frontend": ["software-engineer"],
    "backend": ["software-engineer"],
    "qa-engineer": ["software-engineer"],
    # Game development: creative + software.
    "game-developer": ["software-engineer", "design"],
    # UX/UI design: design specialty (ux-designer merged into "design" in the
    # specialty pivot; see seed_akinator_content.py).
    "ux-designer": ["design"],
    "ui-designer": ["design"],
    # --- Инженерия и техника ---
    # Robotics / mechatronics straddles mechanical engineering and IT.
    "robotics-engineer": ["mechanical-engineer", "software-engineer"],
    "mechatronics": ["mechanical-engineer", "it-infrastructure-security"],
    # Electrical engineering is closest to mechanical + civil in KZ curriculum.
    "electrical-engineer": ["mechanical-engineer", "civil-engineering"],
    # --- Бизнес и продажи ---
    # Product management overlaps management and marketing.
    "product-manager": ["management-entrepreneurship", "marketing"],
    # Digital marketing is fully within marketing.
    "digital-marketer": ["marketing"],
    # Logistics maps to management-entrepreneurship (logistician is listed
    # under that specialty's professions list).
    "logistician": ["management-entrepreneurship"],
    # Entrepreneur / startup founder.
    "entrepreneur": ["management-entrepreneurship"],
    # Accountant / auditor are within finance-accounting.
    "accountant": ["finance-accounting"],
    "auditor": ["finance-accounting"],
    "financial-analyst": ["finance-accounting"],
    # --- Медицина ---
    # Nurse / paramedic — closest is general-medicine (they share the same
    # bachelor entry track in KZ: «Сестринское дело» / «Фельдшер» branching
    # happens inside the track).
    "nurse": ["general-medicine"],
    "paramedic": ["general-medicine"],
    # Dentist maps directly.
    "dentist": ["dentist"],
    # Pharmacist / provisor.
    "pharmacist": ["pharmacist"],
    # --- Творчество и дизайн ---
    # Graphic design, illustration, fashion design are all under the unified
    # "design" specialty (specialty pivot, 2026-07).
    "graphic-designer": ["design"],
    "illustrator": ["design"],
    "fashion-designer": ["design"],
    "furniture-designer": ["design"],
    # Architecture stays separate.
    "architect": ["architect"],
    # --- Сцена и медиа ---
    # Photographer merged into cinematographer (specialty pivot).
    "photographer": ["cinematographer"],
    "videographer": ["cinematographer"],
    # Copywriter / content writer — closest specialty is pr-specialist.
    "copywriter": ["pr-specialist"],
    "content-writer": ["pr-specialist"],
    # Blogger / vlogger merged into journalist (specialty pivot).
    "blogger": ["journalist"],
    # --- Образование ---
    # Tutor merged into school-teacher (specialty pivot).
    "tutor": ["school-teacher"],
    # --- Спорт ---
    # Physical therapist / physio maps to rehabilitation-therapist.
    "physiotherapist": ["rehabilitation-therapist"],
    # --- Безопасность и спасение ---
    # Fire safety / occupational safety.
    "fire-safety": ["fire-safety-engineer"],
    "safety-engineer": ["fire-safety-engineer"],
}

# ---------------------------------------------------------------------------
# Integrity check: every slug in the values must exist in the taxonomy.
# ---------------------------------------------------------------------------

_valid_slugs: set[str] = {s["slug"] for s in SECTIONS} | {p["slug"] for p in SPECIALTIES}

for _alias, _slugs in SPECIALTY_ALIASES.items():
    _unknown = [s for s in _slugs if s not in _valid_slugs]
    assert not _unknown, (
        f"SPECIALTY_ALIASES[{_alias!r}]: unknown slugs {_unknown}. "
        f"Valid slugs are: {sorted(_valid_slugs)}"
    )

if __name__ == "__main__":
    # Quick self-test: just importing (and the assertions above running) is the check.
    print(f"OK — {len(SPECIALTY_ALIASES)} aliases validated against {len(_valid_slugs)} valid slugs.")
