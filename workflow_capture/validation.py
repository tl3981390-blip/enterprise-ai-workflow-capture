from .errors import ValidationError
from .util import normalize_label, parse_iso8601

ACTORS = {"human", "ai", "tool", "system"}
EVENT_TYPES = {"action", "clarification", "correction", "retry", "failure", "recovery", "decision", "result"}
ADOPTION = {"adopted", "partially_adopted", "rejected", "abandoned", "unknown"}
PROVENANCE = {"observed", "user_reported", "ai_inferred", "system_generated"}
CONTEXT_PROVENANCE = {"harness_provided", "user_reported"}
AI_CONTEXT_PROVENANCE = {"harness_provided", "user_reported", "observed"}
CAPABILITY_KINDS = {"model", "skill", "tool", "harness"}
INTERVENTION_REASONS = {"error", "business_preference", "style", "other", "unknown"}
EXTERNAL_HASH_ALGORITHMS = {"sha256": 64, "sha512": 128, "blake2b": 128}
VERIFICATION_STATES = {"verified", "unverified"}

# Records describe workflows, never people. Scoring/ranking fields are rejected
# mechanically. Authorization claims inside a payload are self-authorization
# attempts: the authorization fact comes only from the harness environment.
FORBIDDEN_KEYS = {
    "employee_score",
    "ai_usage_score",
    "productivity_rank",
    "employee_ranking",
    "department_ranking",
    "performance_score",
    "capture_authorized",
    "enterprise_authorized",
    "authorized",
    "authorization",
    "authorization_grant",
    "grant",
    "grant_id",
}

MAX_EXCERPT_LENGTH = 2000
MAX_SUMMARY_LENGTH = 4000
MAX_SESSION_ID_LENGTH = 200


def _scan_forbidden(value, path, errors):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in FORBIDDEN_KEYS:
                errors.append(f"{path}.{key} is forbidden: records describe workflows, never employee scores or self-authorization")
            _scan_forbidden(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_forbidden(item, f"{path}[{index}]", errors)


def _validate_timestamp(value, field, errors):
    if value is not None and parse_iso8601(value) is None:
        errors.append(f"{field} must be an ISO-8601 timestamp when supplied")


def _validate_duration(value, field, errors):
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{field} must be a non-negative integer number of milliseconds")


def _validate_capability(value, field, errors):
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return
    if value.get("kind") not in CAPABILITY_KINDS:
        errors.append(f"{field}.kind must be one of {sorted(CAPABILITY_KINDS)}")
    if not str(value.get("name", "")).strip():
        errors.append(f"{field}.name must not be empty when capability is supplied")
    if "version" in value and not isinstance(value.get("version"), str):
        errors.append(f"{field}.version must be a string when supplied")


def _validate_intervention(value, field, errors):
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return
    if value.get("reason") not in INTERVENTION_REASONS:
        errors.append(f"{field}.reason must be one of {sorted(INTERVENTION_REASONS)}")
    if "rework" in value and not isinstance(value.get("rework"), bool):
        errors.append(f"{field}.rework must be a boolean")
    if "modified_step" in value:
        modified = value.get("modified_step")
        if isinstance(modified, bool) or not isinstance(modified, int) or modified < 1:
            errors.append(f"{field}.modified_step must be a positive integer step ordinal")


def _validate_business_context(value, errors):
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append("business_context must be an object")
        return
    if value.get("provenance") not in CONTEXT_PROVENANCE:
        errors.append(f"business_context.provenance must be one of {sorted(CONTEXT_PROVENANCE)}")
    for field in ("ref", "department", "workflow"):
        if field in value and value[field] is not None and not isinstance(value[field], str):
            errors.append(f"business_context.{field} must be a string when supplied")


def _validate_ai_context(value, errors):
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append("ai_context must be an object")
        return
    if value.get("provenance") not in AI_CONTEXT_PROVENANCE:
        errors.append(f"ai_context.provenance must be one of {sorted(AI_CONTEXT_PROVENANCE)}; never invent AI context")
    for field in ("model", "provider", "skill", "version"):
        if field in value and value[field] is not None and not isinstance(value[field], str):
            errors.append(f"ai_context.{field} must be a string when supplied")


def validate_candidate(data):
    errors = []
    if not isinstance(data, dict):
        raise ValidationError("candidate must be a JSON object")
    _scan_forbidden(data, "$", errors)
    for field in ("task_type", "task_goal", "steps", "final_result"):
        if field not in data:
            errors.append(f"missing required field: {field}")
    if not normalize_label(data.get("task_type", "")):
        errors.append("task_type must not be empty")
    if not str(data.get("task_goal", "")).strip():
        errors.append("task_goal must not be empty")
    session_id = data.get("capture_session_id")
    if session_id is not None:
        if not isinstance(session_id, str) or not session_id.strip():
            errors.append("capture_session_id must be a non-empty string when supplied")
        elif len(session_id) > MAX_SESSION_ID_LENGTH:
            errors.append(f"capture_session_id must not exceed {MAX_SESSION_ID_LENGTH} characters")
    _validate_timestamp(data.get("started_at"), "started_at", errors)
    _validate_timestamp(data.get("completed_at"), "completed_at", errors)
    _validate_business_context(data.get("business_context"), errors)
    _validate_ai_context(data.get("ai_context"), errors)
    summary = data.get("process_summary")
    if summary is not None and len(str(summary)) > MAX_SUMMARY_LENGTH:
        errors.append(f"process_summary must not exceed {MAX_SUMMARY_LENGTH} characters; record what happened, not the full transcript")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
    else:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"steps[{i}] must be an object")
                continue
            if step.get("actor") not in ACTORS:
                errors.append(f"steps[{i}].actor must be one of {sorted(ACTORS)}")
            if step.get("event_type") not in EVENT_TYPES:
                errors.append(f"steps[{i}].event_type must be one of {sorted(EVENT_TYPES)}")
            if step.get("provenance") not in PROVENANCE:
                errors.append(f"steps[{i}].provenance must be one of {sorted(PROVENANCE)}")
            if step.get("provenance") == "ai_inferred":
                confidence = step.get("confidence")
                if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
                    errors.append(f"steps[{i}].confidence must be a number in [0, 1] when provenance is ai_inferred; inference is never observation")
            if not str(step.get("summary", "")).strip():
                errors.append(f"steps[{i}].summary must not be empty")
            elif len(str(step.get("summary", ""))) > MAX_SUMMARY_LENGTH:
                errors.append(f"steps[{i}].summary must not exceed {MAX_SUMMARY_LENGTH} characters")
            _validate_timestamp(step.get("occurred_at"), f"steps[{i}].occurred_at", errors)
            _validate_duration(step.get("duration_ms"), f"steps[{i}].duration_ms", errors)
            _validate_capability(step.get("capability"), f"steps[{i}].capability", errors)
            _validate_intervention(step.get("intervention"), f"steps[{i}].intervention", errors)
    result = data.get("final_result")
    if not isinstance(result, dict):
        errors.append("final_result must be an object")
    elif result.get("adoption_status") not in ADOPTION:
        errors.append(f"final_result.adoption_status must be one of {sorted(ADOPTION)}")
    evidence = data.get("evidence", [])
    if not isinstance(evidence, list):
        errors.append("evidence must be a list")
    else:
        for i, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"evidence[{i}] must be an object")
                continue
            if "content_hash" in item:
                errors.append(f"evidence[{i}].content_hash is system-generated and must not be supplied")
            excerpt = item.get("sanitized_excerpt")
            has_excerpt = isinstance(excerpt, str) and bool(excerpt.strip())
            if has_excerpt:
                if len(excerpt) > MAX_EXCERPT_LENGTH:
                    errors.append(
                        f"evidence[{i}].sanitized_excerpt must not exceed {MAX_EXCERPT_LENGTH} characters; "
                        "retain a minimal excerpt or a hash, never a full transcript"
                    )
                for field in ("external_digest", "hash_algorithm", "verification_state"):
                    if field in item:
                        errors.append(f"evidence[{i}].{field} is not allowed for internally retained evidence")
            else:
                for field in ("external_digest", "hash_algorithm", "source_ref", "verification_state"):
                    if not str(item.get(field, "")).strip():
                        errors.append(f"evidence[{i}].{field} is required for external-only evidence")
                algorithm = item.get("hash_algorithm")
                if algorithm not in EXTERNAL_HASH_ALGORITHMS:
                    errors.append(f"evidence[{i}].hash_algorithm must be one of {sorted(EXTERNAL_HASH_ALGORITHMS)}")
                if item.get("verification_state") not in VERIFICATION_STATES:
                    errors.append(f"evidence[{i}].verification_state must be one of {sorted(VERIFICATION_STATES)}")
                external_digest = str(item.get("external_digest", "")).lower()
                if algorithm in EXTERNAL_HASH_ALGORITHMS:
                    expected = EXTERNAL_HASH_ALGORITHMS[algorithm]
                    if len(external_digest) != expected or any(c not in "0123456789abcdef" for c in external_digest):
                        errors.append(f"evidence[{i}].external_digest is not a valid {algorithm} hex digest")
    if errors:
        raise ValidationError("; ".join(errors))
    return data
