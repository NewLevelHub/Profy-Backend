"""app/services/report_narrative_service.py — the orchestration pipeline:
LLM attempt → validate → retry (max 2 retries, 3 attempts total) →
deterministic fallback. TZ_Profi.md §17.7/§17.8. `llm_client.is_enabled`/
`llm_client.complete_json` are monkeypatched directly on the shared module
object, same pattern the real pipeline uses (`from app.services import
llm_client`), so patching `llm_client.complete_json` here is exactly what
`report_narrative_service.py` will call.
"""
import logging

from app.models.profile import AgeGroup
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services import llm_client, report_narrative_service as service
from app.services.report_narrative_fallback import build_fallback_narrative
from app.services.report_narrative_validator import validate


def _senior_context() -> ReportNarrativeContext:
    return ReportNarrativeContext(
        age_group=AgeGroup.senior.value,
        interest_instrument="riasec",
        evidence=[
            EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Реалистичный"),
            EvidenceItem(source_id="riasec:I", source_type="riasec_category", text="Исследовательский"),
            EvidenceItem(source_id="personality:openness", source_type="personality", text="Открыт новому"),
            EvidenceItem(source_id="personality:conscientiousness", source_type="personality", text="Доводит дело до конца"),
            EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Тебя драйвит интерес"),
        ],
    )


def _payload_queue(*results):
    remaining = list(results)

    async def _fake(messages, schema, schema_name, *, timeout=None, max_tokens=None):
        item = remaining.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return _fake


async def test_llm_disabled_uses_fallback_and_never_calls_the_llm(monkeypatch):
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)

    async def _unexpected(*args, **kwargs):
        raise AssertionError("complete_json must not be called when the LLM is disabled")

    monkeypatch.setattr(llm_client, "complete_json", _unexpected)

    context = _senior_context()
    output, is_ai = await service.generate_report_narrative(context)

    assert is_ai is False
    assert validate(output, context) == []


async def test_llm_success_on_first_attempt(monkeypatch):
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    context = _senior_context()
    good_payload = build_fallback_narrative(context).model_dump()
    monkeypatch.setattr(llm_client, "complete_json", _payload_queue(good_payload))

    output, is_ai = await service.generate_report_narrative(context)

    assert is_ai is True
    assert validate(output, context) == []


async def test_invalid_first_attempt_retries_and_succeeds_on_second(monkeypatch):
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    context = _senior_context()
    good_payload = build_fallback_narrative(context).model_dump()
    bad_payload = build_fallback_narrative(context).model_dump()
    bad_payload["summary"] = "У тебя низкий результат, но не переживай"
    monkeypatch.setattr(llm_client, "complete_json", _payload_queue(bad_payload, good_payload))

    output, is_ai = await service.generate_report_narrative(context)

    assert is_ai is True
    assert output.summary != bad_payload["summary"]


async def test_exhausts_all_three_attempts_then_falls_back(monkeypatch):
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    context = _senior_context()
    bad_payload = build_fallback_narrative(context).model_dump()
    bad_payload["summary"] = "У тебя низкий результат, но не переживай"
    call_count = {"n": 0}

    async def _always_invalid(messages, schema, schema_name, *, timeout=None, max_tokens=None):
        call_count["n"] += 1
        return dict(bad_payload)

    monkeypatch.setattr(llm_client, "complete_json", _always_invalid)

    output, is_ai = await service.generate_report_narrative(context)

    assert call_count["n"] == service.MAX_ATTEMPTS == 3
    assert is_ai is False
    assert validate(output, context) == []


async def test_llm_error_on_every_attempt_falls_back_without_raising(monkeypatch):
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    context = _senior_context()
    call_count = {"n": 0}

    async def _always_raises(messages, schema, schema_name, *, timeout=None, max_tokens=None):
        call_count["n"] += 1
        raise llm_client.LLMError("simulated transport failure with raw content inside: SECRET_RAW_TEXT")

    monkeypatch.setattr(llm_client, "complete_json", _always_raises)

    output, is_ai = await service.generate_report_narrative(context)

    assert call_count["n"] == 3
    assert is_ai is False
    assert validate(output, context) == []


async def test_retry_feeds_the_previous_failure_back_to_the_model(monkeypatch):
    """A blind retry (identical prompt) can't fix a systematic mistake — this
    was measured live against the real model (docs/rs-progress-notes.md:
    career_narrative's evidence_ids came back empty on all 3 attempts,
    every time, because nothing told the model what it got wrong). The
    retry must grow the conversation with the failed output + what to fix,
    not just resend the original messages."""
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    context = _senior_context()
    good_payload = build_fallback_narrative(context).model_dump()
    bad_payload = build_fallback_narrative(context).model_dump()
    bad_payload["summary"] = "У тебя низкий результат, но не переживай"
    seen_messages: list[list[dict]] = []

    async def _fake(messages, schema, schema_name, *, timeout=None, max_tokens=None):
        seen_messages.append(messages)
        return bad_payload if len(seen_messages) == 1 else good_payload

    monkeypatch.setattr(llm_client, "complete_json", _fake)

    output, is_ai = await service.generate_report_narrative(context)

    assert is_ai is True
    assert len(seen_messages[1]) > len(seen_messages[0]), "second attempt must carry more context than the first"
    correction = seen_messages[1][-1]["content"]
    assert "banned_phrase" in correction


async def test_logging_never_leaks_the_matched_banned_phrase_or_raw_llm_error_text(monkeypatch, caplog):
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    context = _senior_context()
    bad_payload = build_fallback_narrative(context).model_dump()
    secret_phrase = "низкий результат"
    bad_payload["summary"] = f"У тебя {secret_phrase}, но не переживай"

    async def _always_invalid(messages, schema, schema_name, *, timeout=None, max_tokens=None):
        return dict(bad_payload)

    monkeypatch.setattr(llm_client, "complete_json", _always_invalid)

    with caplog.at_level(logging.INFO):
        await service.generate_report_narrative(context)

    assert secret_phrase not in caplog.text
    assert "banned_phrase" in caplog.text


async def test_generation_exception_logging_only_names_the_exception_class(monkeypatch, caplog):
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    context = _senior_context()
    raw_leak = "RAW_MODEL_RESPONSE_FRAGMENT_SHOULD_NOT_BE_LOGGED"

    async def _always_raises(messages, schema, schema_name, *, timeout=None, max_tokens=None):
        raise llm_client.LLMError(raw_leak)

    monkeypatch.setattr(llm_client, "complete_json", _always_raises)

    with caplog.at_level(logging.INFO):
        await service.generate_report_narrative(context)

    assert raw_leak not in caplog.text
    assert "LLMError" in caplog.text


async def test_llm_disabled_does_not_record_a_validation_fallback_metric(monkeypatch):
    """Review finding: with the LLM off, the deterministic narrative is the
    intended path — it must not bump llm.fallback:reason=validation or log a
    fallback warning, or the fallback-rate alert fires just because a config
    flag is off."""
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)
    service._metric_counts.clear()

    context = _senior_context()
    _, is_ai = await service.generate_report_narrative(context, language="kk")

    assert is_ai is False
    assert service.metric_counts() == {}


async def test_llm_enabled_but_all_attempts_invalid_still_records_validation_fallback(monkeypatch):
    """The metric must still fire for a real validation failure (LLM on)."""
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    service._metric_counts.clear()
    context = _senior_context()
    # valid shape, but summary is one sentence -> fails _check_summary_sentence_count
    bad = build_fallback_narrative(context).model_dump()
    bad["summary"] = "Слишком коротко."
    monkeypatch.setattr(llm_client, "complete_json", _payload_queue(bad, bad, bad))

    _, is_ai = await service.generate_report_narrative(context)

    assert is_ai is False
    assert service.metric_counts().get("llm.fallback:reason=validation", 0) >= 1
