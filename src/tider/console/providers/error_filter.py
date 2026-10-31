"""Error matching shared by local fixtures and Cloud Logging (RE2-compatible)."""

import re

# Whole words avoid matching failures/s table headings and settings such as bf-error-rate.
ERROR_PATTERN = (r"(?i)((^|[^a-z0-9_-])(error|failed|failure|unavailable|connection refused|"
                 r"deadline exceeded|timed out|socketclosed|readendofstream)([^a-z0-9_-]|$)"
                 r"|[a-z0-9_.]*exception\b)")
TIMEOUT_PATTERN = r"(?i)\btimeout\b"
TIMEOUT_SETTING = r"(?i)timeout[ ]*(\([^)]*\))?[ ]*:"


def is_error(message, severity="INFO"):
    return (severity in {"ERROR", "CRITICAL", "FATAL", "ALERT", "EMERGENCY"}
            or bool(re.search(ERROR_PATTERN, message))
            or bool(re.search(TIMEOUT_PATTERN, message) and not re.search(TIMEOUT_SETTING, message)))


def logging_error_filter():
    import json

    clauses = ['severity >= ERROR', '(jsonPayload.error:* AND NOT jsonPayload.error="")',
               'jsonPayload.level=~"(?i)^(error|fatal|critical)$"']
    for field in ('textPayload', 'jsonPayload.message', 'jsonPayload.msg'):
        clauses += [f'{field}=~{json.dumps(ERROR_PATTERN)}',
                    f'({field}=~{json.dumps(TIMEOUT_PATTERN)} AND NOT {field}=~{json.dumps(TIMEOUT_SETTING)})']
    return '(' + ' OR '.join(clauses) + ')'
