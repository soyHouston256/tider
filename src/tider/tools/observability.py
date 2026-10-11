"""Prometheus, Jaeger y OpenSearch por HTTP. Solo consultas."""
from __future__ import annotations
import json, time
import httpx
from ..config import env
from .base import Tool


def prom_query(query: str) -> str:
    r = httpx.get(f"{env('PROMETHEUS_URL','http://localhost:9090')}/api/v1/query", params={"query": query}, timeout=15)
    r.raise_for_status()
    return json.dumps(r.json()["data"]["result"][:20])[:4000]


def prom_range(query: str, minutes: int = 30, step: str = "30s") -> str:
    end = time.time()
    r = httpx.get(f"{env('PROMETHEUS_URL','http://localhost:9090')}/api/v1/query_range",
                  params={"query": query, "start": end - minutes * 60, "end": end, "step": step}, timeout=20)
    r.raise_for_status()
    out = []
    for s in r.json()["data"]["result"][:10]:
        vals = [float(v[1]) for v in s["values"] if v[1] not in ("NaN", "+Inf")]
        if vals:
            out.append({"metric": s["metric"], "min": min(vals), "max": max(vals), "last": vals[-1]})
    return json.dumps(out)[:4000]


def traces_errors(service: str, limit: int = 10, lookback: str = "30m") -> str:
    r = httpx.get(f"{env('JAEGER_URL','http://localhost:16686')}/api/traces",
                  params={"service": service, "limit": limit, "lookback": lookback,
                          "tags": json.dumps({"error": "true"})}, timeout=20)
    r.raise_for_status()
    summary = []
    for t in r.json().get("data", [])[:limit]:
        procs = {p: v["serviceName"] for p, v in t["processes"].items()}
        spans = [(procs[s["processID"]], s["operationName"], s["duration"]) for s in t["spans"]]
        summary.append({"traceID": t["traceID"], "spans": spans[:12]})
    return json.dumps(summary)[:4000]


def logs_search(service: str, text: str = "error", size: int = 20) -> str:
    body = {"size": size, "sort": [{"@timestamp": "desc"}],
            "query": {"bool": {"must": [{"match": {"resource.service.name": service}}, {"match": {"body": text}}]}}}
    r = httpx.post(f"{env('OPENSEARCH_URL','http://localhost:9200')}/otel-logs-*/_search", json=body, timeout=20)
    r.raise_for_status()
    return "\n".join(h["_source"].get("body", "") for h in r.json()["hits"]["hits"])[:4000]


def tools() -> list[Tool]:
    return [
        Tool("prom_query", "PromQL instantáneo. args: query", "metric", prom_query),
        Tool("prom_range", "PromQL en rango (min/max/last). args: query, minutes", "metric", prom_range),
        Tool("traces_errors", "Trazas con error de un servicio. args: service", "trace", traces_errors),
        Tool("logs_search", "Búsqueda de logs. args: service, text", "log", logs_search),
    ]
