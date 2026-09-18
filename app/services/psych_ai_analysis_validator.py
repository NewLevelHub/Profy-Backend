"""Post-generation validator for the psychologist-view AI analysis — the
gate between llm_client's structured output and what gets persisted onto
AnalysisResult.psych_ai_analysis.

The one rule that actually matters here (everything else is a soft
cardinality/shape check): `recommended_profession.slug` MUST be one of
`context.careers`' own slugs. This is the literal implementation of "он
свое не придумывает, он скидывает именно ту, которая предложена из ТОП-10"
— checked against the ground truth, not just asked for in the prompt text.
"""
import re
from dataclasses import dataclass

from app.prompts.psych_ai_analysis import NO_RECOMMENDATION_SLUG
from app.schemas.psych_ai_analysis import PsychAiAnalysisOutput
from app.services.psych_ai_analysis_context import PsychAiAnalysisContext

_SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s|$)")
_MIN_FINAL_SUMMARY_SENTENCES = 3
_MAX_FINAL_SUMMARY_SENTENCES = 7


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    detail: str = ""


def _check_block_coverage(
    output: PsychAiAnalysisOutput, context: PsychAiAnalysisContext
) -> list[ValidationIssue]:
    expected_keys = {b.key for b in context.blocks}
    got_keys = [item.block for item in output.block_analyses]

    issues: list[ValidationIssue] = []
    unknown = sorted(set(got_keys) - expected_keys)
    if unknown:
        issues.append(ValidationIssue("unknown_block", ", ".join(unknown)))

    missing = sorted(expected_keys - set(got_keys))
    if missing:
        issues.append(ValidationIssue("missing_block_analysis", ", ".join(missing)))

    duplicates = sorted({k for k in got_keys if got_keys.count(k) > 1})
    if duplicates:
        issues.append(ValidationIssue("duplicate_block_analysis", ", ".join(duplicates)))

    for item in output.block_analyses:
        if item.block in expected_keys and not item.text.strip():
            issues.append(ValidationIssue("empty_block_analysis", item.block))

    return issues


def _check_final_summary(output: PsychAiAnalysisOutput) -> list[ValidationIssue]:
    count = len(_SENTENCE_END_RE.findall(output.final_summary.strip()))
    if count < _MIN_FINAL_SUMMARY_SENTENCES or count > _MAX_FINAL_SUMMARY_SENTENCES:
        return [ValidationIssue(
            "final_summary_wrong_length",
            f"expected {_MIN_FINAL_SUMMARY_SENTENCES}-{_MAX_FINAL_SUMMARY_SENTENCES} sentences, got {count}",
        )]
    return []


def _check_recommended_profession(
    output: PsychAiAnalysisOutput, context: PsychAiAnalysisContext
) -> list[ValidationIssue]:
    rec = output.recommended_profession
    if rec is None:
        return [ValidationIssue("recommended_profession_missing")]

    if not context.careers:
        if rec.slug != NO_RECOMMENDATION_SLUG:
            return [ValidationIssue("recommended_profession_when_none_available", rec.slug)]
        return []

    valid_slugs = {c.slug for c in context.careers}
    if rec.slug == NO_RECOMMENDATION_SLUG or rec.slug not in valid_slugs:
        return [ValidationIssue("recommended_profession_not_in_careers", rec.slug)]
    if not rec.reasoning.strip():
        return [ValidationIssue("recommended_profession_no_reasoning")]
    return []


def validate(
    output: PsychAiAnalysisOutput, context: PsychAiAnalysisContext
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues += _check_block_coverage(output, context)
    issues += _check_final_summary(output)
    issues += _check_recommended_profession(output, context)
    return issues
