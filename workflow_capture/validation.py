from .errors import ValidationError
from .util import normalize_label

ACTORS = {"human", "ai", "tool", "system"}
EVENT_TYPES = {"action", "clarification", "correction", "retry", "failure", "recovery", "result"}
ADOPTION = {"adopted", "partially_adopted", "rejected", "abandoned", "unknown"}
PROVENANCE = {"observed", "user_reported", "ai_inferred", "system_generated"}


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
    if not isinstance(data.get("evidence", []), list):
        errors.append("evidence must be a list")
    if errors:
        raise ValidationError("; ".join(errors))
    return data

