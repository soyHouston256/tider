"""Historical GKE events from Cloud Logging, using the existing read-only ADC scope."""

import json
import re
from datetime import timezone

from tider.llm import error_details

from .logging_sdk import BoundedLoggingClient
from .redaction import sanitize

AVAILABILITY_REASONS = {"ScalingReplicaSet", "Killing", "Unhealthy", "FailedScheduling", "BackOff",
                        "Failed", "Evicted", "OOMKilling", "FailedMount", "FailedAttachVolume"}


def event_filter(start, end, settings, services=None):
    """`services=None` lee todo el namespace, sin la regex de nombres (barrido v2, independiente del Lake)."""
    q = json.dumps
    fields = {"resource.labels.project_id": settings.google_cloud_project,
              "resource.labels.cluster_name": settings.gcp_cluster,
              "resource.labels.location": settings.gcp_location,
              "logName": f"projects/{settings.google_cloud_project}/logs/events",
              "jsonPayload.involvedObject.namespace": settings.gcp_namespace}
    clauses = [*[f'{k}={q(v)}' for k, v in fields.items()],
               f'timestamp>={q(start.astimezone(timezone.utc).isoformat())}',
               f'timestamp<={q(end.astimezone(timezone.utc).isoformat())}']
    if services is not None:
        # A hyphen outside a character class is literal; keep DNS labels literal in Logging's regex.
        names = '^(' + '|'.join(re.escape(name).replace(r'\-', '-') for name in sorted(services)) + ')(-[a-z0-9]+)*$'
        clauses.append(f'jsonPayload.involvedObject.name=~{q(names)}')
    return ' AND '.join(clauses)


# Pod de Deployment (<carga>-<hash RS>-<5>), ReplicaSet (<carga>-<hash>) y pod de StatefulSet (<carga>-<n>).
_OWNER_PATTERNS = {'Pod': (re.compile(r'^(?P<base>.+)-[a-z0-9]{5,10}-[a-z0-9]{5}$'), re.compile(r'^(?P<base>.+)-\d+$')),
                   'ReplicaSet': (re.compile(r'^(?P<base>.+)-[a-z0-9]{5,10}$'),)}


def owner_from_name(name, kind, inventory):
    """Carga del inventario de la plataforma a la que pertenece un objeto, o None si no se puede decidir (A32)."""
    if kind in {'Deployment', 'StatefulSet', 'DaemonSet', 'Service'}:
        return (name, 'exact_workload_name') if name in inventory else (None, '')
    for pattern in _OWNER_PATTERNS.get(kind, ()):
        match = pattern.match(name)
        if match and match['base'] in inventory:
            return match['base'], 'platform_name_pattern'
    return None, ''


def event_from_entry(entry, services, namespace, start, end, inventory=None):
    """Con `services=None`, el servicio sale del inventario de la plataforma (`inventory`); si no se puede
    asignar, el evento se conserva con `service=None` (evento del namespace)."""
    data = entry.payload
    if not isinstance(data, dict) or not entry.timestamp or not start <= entry.timestamp <= end:
        return None
    obj = data.get('involvedObject') or {}
    if obj.get('namespace') != namespace:
        return None
    name, kind = obj.get('name', ''), obj.get('kind', '')
    if services is None:
        service, mapping = owner_from_name(name, kind, set(inventory or ()))
        return _event(data, entry, service, kind, name, mapping or 'unassigned_namespace_event')
    # Exact workload identity is authoritative. Pod/ReplicaSet prefixes are only suggestions.
    exact = name in services and kind in {'Deployment', 'StatefulSet', 'DaemonSet', 'Service'}
    matches = [s for s in services if name.startswith(s + '-')] if kind in {'Pod', 'ReplicaSet'} else []
    service = name if exact else matches[0] if len(matches) == 1 else None
    if not service:
        return None
    return _event(data, entry, service, kind, name,
                  'exact_workload_name' if exact else 'name_prefix_not_verified_ownership')


def _event(data, entry, service, kind, name, mapping):
    return {'service': service, 'timestamp': entry.timestamp.isoformat(),
            'object_kind': kind, 'object_name': name, 'reason': data.get('reason', ''),
            'message': sanitize(str(data.get('message', '')), limit=800),
            'mapping': mapping,
            'type': data.get('type', ''), 'first_reported_at': data.get('firstTimestamp'),
            'last_reported_at': data.get('lastTimestamp') or data.get('eventTime'),
            'availability_change': data.get('reason') in AVAILABILITY_REASONS}


def gcp_events(start, end, settings, services, *, deadline, limit=100, inventory=None):
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
            event = event_from_entry(entry, services, settings.gcp_namespace, start, end, inventory)
            if event:
                events.append(event)
    except Exception as exc:
        if not events:
            raise
        incomplete = error_details(exc)
    finally:
        client.close()
    return {'events': sorted(events, key=lambda e: e['timestamp']), 'records_read': min(read, limit),
            'truncated': read > limit, 'incomplete': incomplete,
            'queried_services': sorted(services) if services is not None else 'namespace',
            'start': start.isoformat(), 'end': end.isoformat(), 'temporal_scope': 'incident_window',
            'interpretation': 'Eventos históricos; un cambio de réplicas o un reinicio no demuestra quién lo provocó. '
                              'Los eventos de varios servicios pueden corresponder a episodios diferentes.'}
