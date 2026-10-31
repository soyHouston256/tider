"""Read-only Cloud Logging pagination with an explicit timeout on every RPC."""

from datetime import datetime
from time import monotonic
from types import SimpleNamespace


class BoundedLoggingClient:
    def __init__(self, project, deadline, client=None):
        from google.cloud.logging_v2.services.logging_service_v2 import LoggingServiceV2Client

        self.project = project
        self.deadline = min(deadline, monotonic() + 15)
        self.client = client or LoggingServiceV2Client()

    def list_entries(self, filter_, order_by, page_size, max_results):
        from google.cloud.logging_v2.types import LogEntry
        from google.protobuf.json_format import MessageToDict

        token, seen, count = "", set(), 0
        while count < max_results:
            remaining = self.deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("Tiempo de consulta agotado")
            pager = self.client.list_log_entries(
                request={"resource_names": [f"projects/{self.project}"], "filter": filter_,
                         "order_by": order_by, "page_size": min(page_size, max_results-count),
                         "page_token": token},
                timeout=min(10, remaining), retry=None,
            )
            # Read only this already-fetched page; recalculate the timeout before the next RPC.
            page = next(iter(pager.pages))
            for raw in page.entries:
                entry = MessageToDict(LogEntry.pb(raw))
                yield SimpleNamespace(payload=entry.get("jsonPayload", entry.get("textPayload", "")),
                    labels=entry.get("labels", {}), severity=entry.get("severity", "INFO"),
                    timestamp=datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")))
                count += 1
                if count >= max_results:
                    return
            token = page.next_page_token
            if not token:
                return
            if token in seen or len(seen) >= 100:
                raise RuntimeError("Paginación incompleta")
            seen.add(token)

    def close(self):
        self.client.transport.close()
