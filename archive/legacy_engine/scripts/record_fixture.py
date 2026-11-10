#!/usr/bin/env python3
"""Graba un fixture del eval contra el clúster real, en el formato que lee FixtureRegistry.
Uso: python scripts/record_fixture.py eval/calls/<escenario>.yaml eval/fixtures/<escenario>.json
El YAML lista las llamadas a grabar, con la coincidencia que el eval exigirá a los argumentos del LLM:
  - { tool: prom_range, args: { query: "container_memory_working_set_bytes{namespace=\\"otel-demo\\"}" }, match: { query: memory } }
  - { tool: deployment_status, args: { deployment: recommendation }, match: { deployment: recommendation } }
Correrlo con la falla activa (scripts/inject_fault.py <flag> on, o un despliegue malo) y REVISAR la salida antes de
commitearla: puede traer datos internos. Usa las mismas herramientas de solo lectura que el investigador.
"""
import argparse, json, sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tider.tools import default_registry  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("calls"); ap.add_argument("fixture")
a = ap.parse_args()

reg, fixture = default_registry(), {}
for c in yaml.safe_load(Path(a.calls).read_text(encoding="utf-8")):
    res = reg.call(c["tool"], **(c.get("args") or {}))
    if res["kind"] == "error":
        sys.exit(f"{c['tool']} falló, no se graba nada: {res['summary']}")
    out = res["data"] if res["data"] is not None else ("" if res["kind"] == "empty" else res["summary"])
    fixture.setdefault(c["tool"], []).append({"match": c.get("match") or {}, "out": out})
    print(f"{c['tool']}: {res['kind']}, {len(res['summary'])} caracteres")
Path(a.fixture).write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"fixture -> {a.fixture}")
