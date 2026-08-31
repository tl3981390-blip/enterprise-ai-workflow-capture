from .errors import ValidationError
from .util import normalize_label

ACTORS = {"human", "ai", "tool", "system"}
EVENT_TYPES = {"action", "clarification", "correction", "retry", "failure", "recovery", "result"}
ADOPTION = {"adopted", "partially_adopted", "rejected", "abandoned", "unknown"}
PROVENANCE = {"observed", "user_reported", "ai_inferred", "system_generated"}
EXTERNAL_HASH_ALGORITHMS = {"sha256": 64, "sha512": 128, "blake2b": 128}
VERIFICATION_STATES = {"verified", "unverified"}


def validate_candidate(data):
    errors = []
    if not isinstance(data, dict):
        raise ValidationError("candidate must be a JSON object")
    for field in ("task_type", "task_goal", "steps", "final_result"):
        if field not in data:
            errors.append(f"missing required field: {field}")
    if not normalize_label(data.get("task_type", "")):
        errors.append("task_type must not be empty")
    if not str(data.get("task_goal", "")).strip():
        errors.append("task_goal must not be empty")
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
            if not str(step.get("summary", "")).strip():
                errors.append(f"steps[{i}].summary must not be empty")
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
