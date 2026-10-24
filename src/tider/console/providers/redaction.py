"""Mask supported credential and email patterns before analysis."""

import re


def sanitize(value: str) -> str:
    value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", value)
    value = re.sub(
        r"""(?ix)(authorization|password|token|api[_-]?key|secret)["']?\s*[:=]\s*["']?[^\s,"'}]+""",
        r"\1=[REDACTED]",
        value,
    )
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[EMAIL]", value)
    return value[:600]
