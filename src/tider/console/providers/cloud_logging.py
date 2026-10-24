"""Cloud Logging adapter: bounded reads scoped to the configured lab."""

import json
from datetime import datetime, timezone

from ..models import Signal
from ..settings import Settings
from .catalog import related_services
from .redaction import sanitize


def gcp_filter(service: str, start: datetime, end: datetime, settings: Settings) -> str:
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
    labels = " OR ".join(f'labels."k8s-pod/app"={q(s)}' for s in related_services(service))
    return " AND ".join([*clauses, "(" + labels + ")"])


def gcp_signals(service: str, start: datetime, end: datetime, settings: Settings) -> list[Signal]:
    if settings.evidence_mode != "gcp":
        raise ValueError("Activa EVIDENCE_MODE=gcp en el servidor para consultar Cloud Logging.")
    if not settings.google_cloud_project:
        raise ValueError("GOOGLE_CLOUD_PROJECT es obligatorio.")
    from google.cloud import logging_v2

    client = logging_v2.Client(project=settings.google_cloud_project)
    signals = []
    try:
        entries = client.list_entries(
            filter_=gcp_filter(service, start, end, settings),
            order_by="timestamp desc",
            page_size=min(settings.gcp_log_limit, 100),
            max_results=settings.gcp_log_limit,
        )
        for entry in entries:
            payload = entry.payload
            if isinstance(payload, dict):
                message = payload.get("message") or payload.get("msg") or payload.get("error") or ""
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
    finally:
        client.close()
    return signals
