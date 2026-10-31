"""Cloud Logging adapter: bounded reads scoped to the configured lab."""

import json
from datetime import datetime, timezone
from itertools import chain
from time import monotonic

from tider.llm import error_details

from ..models import Signal
from ..settings import Settings
from .catalog import related_services
from .redaction import sanitize


def gcp_filter(
    service: str, start: datetime, end: datetime, settings: Settings, services: list[str] | None = None
) -> str:
    q = json.dumps
    fields = {
        "resource.type": "k8s_container",
        "resource.labels.project_id": settings.google_cloud_project,
        "resource.labels.cluster_name": settings.gcp_cluster,
        "resource.labels.location": settings.gcp_location,
        "resource.labels.namespace_name": settings.gcp_namespace,
    }
    clauses = [f"{key}={q(value)}" for key, value in fields.items()]
    clauses += [
        f"timestamp >= {q(start.astimezone(timezone.utc).isoformat())}",
        f"timestamp <= {q(end.astimezone(timezone.utc).isoformat())}",
    ]
    labels = " OR ".join(
        f'labels."k8s-pod/app"={q(s)}'
        for s in (services if services is not None else related_services(service))
    )
    return " AND ".join([*clauses, "(" + labels + ")"])


# Match structured errors as well as applications that log failures at INFO.
ERROR_FILTER = '(' + ' OR '.join([
    'severity >= ERROR',
    '(jsonPayload.error:* AND NOT jsonPayload.error="")',
    'jsonPayload.level=~"(?i)^(error|fatal|critical)$"',
    *[f'{field}=~"(?i)(error|exception|failed|failure|unavailable|connection refused|deadline exceeded|timeout)"'
      for field in ('textPayload', 'jsonPayload.message', 'jsonPayload.msg')],
]) + ')'


class SignalBatch(list):
    """A partial read retains its rows and explicitly records the missing coverage."""

    incomplete: dict | None = None


def gcp_signals(
    service: str, start: datetime, end: datetime, settings: Settings, services: list[str] | None = None,
    max_records: int | None = None, text: str = "", errors_only: bool = True, deadline: float | None = None,
) -> list[Signal]:
    if settings.evidence_mode != "gcp":
        raise ValueError("Activa EVIDENCE_MODE=gcp en el servidor para consultar Cloud Logging.")
    if not settings.google_cloud_project:
        raise ValueError("GOOGLE_CLOUD_PROJECT es obligatorio.")
    if max_records is not None and settings.agent_logging_transport == "mcp":
        from .logging_mcp import LoggingMCPClient
        client = LoggingMCPClient(settings.google_cloud_project, deadline=deadline)
    elif max_records is not None and deadline is not None:
        from .logging_sdk import BoundedLoggingClient
        client = BoundedLoggingClient(settings.google_cloud_project, deadline)
    else:
        from google.cloud import logging_v2
        client = logging_v2.Client(project=settings.google_cloud_project)
    signals = SignalBatch()
    try:
        base = gcp_filter(service, start, end, settings, services)
        if text:
            base += " AND " + json.dumps(text)
        entries = client.list_entries(
            filter_=base + (" AND " + ERROR_FILTER if errors_only else ""),
            order_by="timestamp desc",
            page_size=min(settings.gcp_log_limit, 100),
            max_results=max_records,
        )
        # The SDK iterator follows every page token; page_size is not a total cap.
        iterator = iter(entries)
        first = next(iterator, None)
        if first is None and max_records is None:
            # No matching errors: retain a bounded normal-activity sample.
            entries = client.list_entries(
                filter_=base,
                order_by="timestamp desc", page_size=min(settings.gcp_log_limit, 100),
                max_results=settings.gcp_log_limit,
            )
        else:
            entries = chain([first], iterator) if first is not None else []
        for entry in entries:
            if deadline is not None and monotonic() >= deadline:
                raise TimeoutError("Presupuesto de consulta agotado")
            payload = entry.payload
            if isinstance(payload, dict):
                # Keep diagnostic details before the general message so truncation
                # cannot hide the error behind a long request description.
                parts = []
                for key in ("error", "message", "msg"):
                    value = payload.get(key)
                    if value:
                        part = sanitize(str(value))
                        if part not in parts:
                            parts.append(part)
                message = " | ".join(parts) or sanitize(json.dumps(payload, ensure_ascii=False))
            else:
                message = payload if isinstance(payload, str) else ""
            if not message:
                continue
            observed_service = (entry.labels or {}).get("k8s-pod/app", service)
            signals.append(
                Signal(
                    timestamp=entry.timestamp or start,
                    service=observed_service,
                    source="log",
                    message=sanitize(str(message)),
                    severity=str(entry.severity or "INFO"),
                )
            )
    except Exception as exc:
        if max_records is None or not signals:
            raise
        signals.incomplete = error_details(exc)
    finally:
        client.close()
    return signals
