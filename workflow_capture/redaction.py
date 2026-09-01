import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Redaction:
    category: str
    path: str


PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I | re.S)),
    ("credential", re.compile(r"(?i)\b(api[_ -]?key|secret|password|passwd|token|authorization)\b\s*[:=]\s*['\"]?[^\s,'\"}]{6,}")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|github_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b")),
    ("china_id", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("payment_card", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")),
)


def _sanitize_string(value, path, findings):
    output = value
    for category, pattern in PATTERNS:
        if pattern.search(output):
            findings.append(Redaction(category, path))
            output = pattern.sub(f"[REDACTED:{category.upper()}]", output)
    return output


def sanitize(value, path="$", findings=None):
    findings = [] if findings is None else findings
    if isinstance(value, str):
        return _sanitize_string(value, path, findings), findings
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            cleaned, _ = sanitize(item, f"{path}[{index}]", findings)
            result.append(cleaned)
        return result, findings
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            cleaned, _ = sanitize(item, f"{path}.{key}", findings)
            result[key] = cleaned
        return result, findings
    return value, findings
