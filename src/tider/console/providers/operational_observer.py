"""Read-only projection of neutral measurements, never experiment records."""
import json
import math
import statistics
from collections import defaultdict
from urllib.parse import urlsplit

import httpx


def observer_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        raise ValueError("El observador requiere un túnel local HTTP configurado por el operador.")
    return value.rstrip("/") + "/api/observations"


def read_observations(url, service, start, end, timeout):
    response = httpx.get(observer_url(url), params={"start": start.timestamp(), "end": end.timestamp()},
                         timeout=timeout, follow_redirects=False)
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError("Respuesta del observador demasiado grande; acota la ventana.")
    data = response.json()
    groups = defaultdict(list)
    unavailable = 0
    for row in data.get("observations", []):
        if row.get("service") != service or not start.timestamp() <= row["at"] <= end.timestamp():
            continue
        if row.get("coverage") != "complete":
            unavailable += 1
            continue
        # Buckets preserve temporal/configuration changes without forwarding the operator's records.
        config = row.get("configuration", {})
        allowed = {k: config[k] for k in ("uid", "generation", "image", "container", "redis_address", "cpu") if k in config}
        key = (int(row["at"] // 30), json.dumps(allowed, sort_keys=True), bool(row.get("synthetic")))
        groups[key].append(row)
    summaries = []
    for (_, config, synthetic), rows in sorted(groups.items()):
        http = [p for row in rows for p in row.get("http", []) if p.get("path") == "/cart"]
        durations = sorted(p["elapsed_ms"] for p in http if isinstance(p.get("elapsed_ms"), (int, float)) and math.isfinite(p["elapsed_ms"]))
        deps = [r["dependency"] for r in rows if r.get("dependency")]
        cpu = [r["cpu_throttling"] for r in rows if r.get("cpu_throttling")]
        summaries.append({"start": rows[0]["at"], "end": rows[-1]["at"], "samples": len(rows),
            "configuration": json.loads(config), "synthetic": synthetic,
            "operation": "GET /cart", "requests": len(http), "errors": sum(p.get("status") != 200 for p in http),
            "latency_median_ms": statistics.median(durations) if durations else None,
            "latency_p95_ms": durations[max(0, math.ceil(.95 * len(durations)) - 1)] if durations else None,
            "dependency_successes": sum(bool(d.get("success")) for d in deps), "dependency_samples": len(deps),
            "dependency_median_ms": statistics.median(d["elapsed_ms"] for d in deps) if deps else None,
            "cpu_throttling": cpu[-1] if cpu else {"coverage": "unavailable"}})
    return {"service": service, "source": "neutral_operational_observer", "buckets": summaries[:30],
            "truncated": bool(data.get("truncated")) or len(summaries) > 30, "unavailable_samples": unavailable,
            "retained_since": data.get("retained_since"), "requested_start": start.isoformat(), "requested_end": end.isoformat(),
            "coverage": "observed_samples_only", "mode": data.get("mode"),
            "limitation": "Muestreo de una operación; no acredita todas las rutas ni causalidad por sí solo."}
