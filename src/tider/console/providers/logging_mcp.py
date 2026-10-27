"""Optional Google Logging MCP transport: only list_log_entries is exposed.

Protocol and tool schema checked against the public tools/list endpoint. Authenticated
calls require separately configured ADC/IAM; no permissions are changed here.
"""
import json
from datetime import datetime
from time import monotonic
from types import SimpleNamespace

import httpx


class LoggingMCPClient:
    def __init__(self, project, client=None, token=None, deadline=None):
        self.project = project
        self.deadline = deadline
        self.client = client or httpx.Client(timeout=15)
        if token is None:
            import google.auth
            from google.auth.transport.requests import Request
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            credentials.refresh(Request())
            token = credentials.token
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
                        "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/call",
                        "Mcp-Name": "list_log_entries"}

    def list_entries(self, filter_, order_by, page_size, max_results):
        if max_results is None:
            raise ValueError("El transporte MCP exige un presupuesto de registros.")
        token, seen, count = None, set(), 0
        while count < max_results:
            if self.deadline is not None and monotonic() >= self.deadline:
                raise TimeoutError("Presupuesto de consulta MCP agotado.")
            args = {"resourceNames": [f"projects/{self.project}"], "filter": filter_,
                    "orderBy": order_by, "pageSize": min(page_size, max_results-count)}
            if token:
                args["pageToken"] = token
            response = self.client.post("https://logging.googleapis.com/mcp", headers=self.headers,
                json={"jsonrpc": "2.0", "id": count+1, "method": "tools/call",
                      "params": {"name": "list_log_entries", "arguments": args}})
            response.raise_for_status()
            body = response.json()
            result = body.get("result", {})
            if body.get("error") or result.get("isError"):
                raise RuntimeError("Cloud Logging MCP rechazó la consulta.")
            data = result.get("structuredContent")
            if data is None:
                blocks = [b["text"] for b in result.get("content", []) if b.get("type") == "text"]
                data = json.loads("".join(blocks))
            if not isinstance(data, dict):
                raise ValueError("Respuesta MCP no estructurada.")
            for entry in data.get("entries", []):
                if count >= max_results:
                    break
                count += 1
                yield SimpleNamespace(payload=entry.get("jsonPayload", entry.get("textPayload", "")),
                    labels=entry.get("labels", {}), severity=entry.get("severity", "INFO"),
                    timestamp=datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")))
            token = data.get("nextPageToken")
            if not token:
                return
            if token in seen or len(seen) >= 100:
                raise RuntimeError("Paginación MCP incompleta; no se presenta como evidencia completa.")
            seen.add(token)

    def close(self):
        self.client.close()
