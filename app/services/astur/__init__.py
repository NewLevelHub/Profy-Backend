"""АСТУР («Когнитивные навыки», PRO-338 → PRO-427).

- `bank`            — immutable bank document (text + keys + scoring methods + timers)
- `bank_validation` — pre-publish checks for a bank document
- `bank_versions`   — draft → validate → publish lifecycle of bank versions (DB)
- `scoring`         — pure scoring of one attempt against its own bank version
- `scoring_rules`   — versioned product thresholds the scoring reads
- `timing`          — server-side subtest timer + lability per-item timing
- `content`         — public (key-free, localized) content for the test-taker
- `runs`            — attempt lifecycle: start, submit, atomic finalize, retake
- `analytics`       — per-item product analytics over completed attempts
"""
