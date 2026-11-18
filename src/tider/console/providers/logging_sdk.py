"""Read-only Cloud Logging pagination with an explicit timeout on every RPC."""

from datetime import datetime
from threading import Lock
from time import monotonic
from types import SimpleNamespace

_lock = Lock()
_shared = None


def shared_client():
    """Cliente gRPC único del proceso, seguro entre hilos.

    Crear un `LoggingServiceV2Client` por lectura resuelve las credenciales cada vez, y con las
    credenciales de usuario de gcloud eso lanza un subproceso (`gcloud config config-helper`) para
    averiguar el proyecto. Hacerlo desde varios hilos mientras otros están dentro de una llamada gRPC
    congela esas llamadas alrededor de un minuto (medido en el barrido: 504 Deadline Exceeded tras
    65 s con un tiempo máximo de 10 s). Un solo cliente evita los subprocesos repetidos y reutiliza
    el canal.

    El candado serializa la creación: ningún hilo puede estar dentro de una llamada gRPC antes de que
    el cliente exista, así que el subproceso nunca coincide con una llamada en curso.
    """
    global _shared
    with _lock:
        if _shared is None:
            from google.cloud.logging_v2.services.logging_service_v2 import LoggingServiceV2Client

            _shared = LoggingServiceV2Client()
        return _shared


class BoundedLoggingClient:
    def __init__(self, project, deadline, client=None):
        self.project = project
        self.deadline = min(deadline, monotonic() + 15)
        # Un cliente recibido es de quien lo pasa (y se cierra con `close`); el compartido no.
        self._propio = client is not None
        self.client = client if client is not None else shared_client()

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
                    labels=entry.get("labels", {}), resource=entry.get("resource", {}), severity=entry.get("severity", "INFO"),
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
        if self._propio:
            self.client.transport.close()
