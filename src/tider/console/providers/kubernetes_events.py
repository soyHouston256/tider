"""Historical GKE events from Cloud Logging, using the existing read-only ADC scope."""

import json
import re
from datetime import timezone

from tider.llm import error_details

from .logging_sdk import BoundedLoggingClient
from .redaction import sanitize

AVAILABILITY_REASONS = {"ScalingReplicaSet", "Killing", "Unhealthy", "FailedScheduling", "BackOff",
                        "Failed", "Evicted", "OOMKilling", "FailedMount", "FailedAttachVolume"}


def event_filter(start, end, settings, services):
    q = json.dumps
    # A hyphen outside a character class is literal; keep DNS labels literal in Logging's regex.
    names = '^(' + '|'.join(re.escape(name).replace(r'\-', '-') for name in sorted(services)) + ')(-[a-z0-9]+)*$'
    fields = {"resource.labels.project_id": settings.google_cloud_project,
              "resource.labels.cluster_name": settings.gcp_cluster,
              "resource.labels.location": settings.gcp_location,
              "logName": f"projects/{settings.google_cloud_project}/logs/events",
              "jsonPayload.involvedObject.namespace": settings.gcp_namespace}
    return ' AND '.join([*[f'{k}={q(v)}' for k, v in fields.items()],
                        f'timestamp>={q(start.astimezone(timezone.utc).isoformat())}',
                        f'timestamp<={q(end.astimezone(timezone.utc).isoformat())}',
                        f'jsonPayload.involvedObject.name=~{q(names)}'])


def event_from_entry(entry, services, namespace, start, end):
    data = entry.payload
    if not isinstance(data, dict) or not entry.timestamp or not start <= entry.timestamp <= end:
        return None
    obj = data.get('involvedObject') or {}
    if obj.get('namespace') != namespace:
        return None
    name, kind = obj.get('name', ''), obj.get('kind', '')
    # Exact workload identity is authoritative. Pod/ReplicaSet prefixes are only suggestions.
    exact = name in services and kind in {'Deployment', 'StatefulSet', 'DaemonSet', 'Service'}
    matches = [s for s in services if name.startswith(s + '-')] if kind in {'Pod', 'ReplicaSet'} else []
    service = name if exact else matches[0] if len(matches) == 1 else None
    if not service:
        return None
    return {'service': service, 'timestamp': entry.timestamp.isoformat(),
            'object_kind': kind, 'object_name': name, 'reason': data.get('reason', ''),
            'message': sanitize(str(data.get('message', '')), limit=800),
            'mapping': 'exact_workload_name' if exact else 'name_prefix_not_verified_ownership',
            'type': data.get('type', ''), 'first_reported_at': data.get('firstTimestamp'),
            'last_reported_at': data.get('lastTimestamp') or data.get('eventTime'),
            'availability_change': data.get('reason') in AVAILABILITY_REASONS}


def gcp_events(start, end, settings, services, *, deadline, limit=100):
    if settings.evidence_mode != 'gcp':
        raise ValueError('Activa GCP para consultar eventos históricos.')
    client = BoundedLoggingClient(settings.google_cloud_project, deadline)
    events, incomplete, read = [], None, 0
    try:
        for entry in client.list_entries(event_filter(start, end, settings, services),
                                         'timestamp desc', min(100, limit + 1), limit + 1):
            read += 1
            if read > limit:
                break
            event = event_from_entry(entry, services, settings.gcp_namespace, start, end)
            if event:
                events.append(event)
    except Exception as exc:
        if not events:
            raise
        incomplete = error_details(exc)
    finally:
        client.close()
    return {'events': sorted(events, key=lambda e: e['timestamp']), 'records_read': min(read, limit),
            'truncated': read > limit, 'incomplete': incomplete, 'queried_services': sorted(services),
            'start': start.isoformat(), 'end': end.isoformat(), 'temporal_scope': 'incident_window',
            'interpretation': 'Eventos históricos; un cambio de réplicas o un reinicio no demuestra quién lo provocó. '
                              'Los eventos de varios servicios pueden corresponder a episodios diferentes.'}
