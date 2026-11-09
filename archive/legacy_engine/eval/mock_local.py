"""Pruebas de integración con telemetría sintética y respuestas programadas.

Ejecuta código real del grafo y del decisor en dry-run. No mide el acierto de
un modelo real, el MTTR ni los costos de atención. No requiere red ni clúster.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def tool(name, /, **kwargs):
    return {"action": "tool", "tool": name, "args": kwargs}


# Las expectativas se fijan antes de ejecutar el grafo. En injection_checkout
# se programa una propuesta incorrecta para comprobar que el decisor la bloquea.
SCENARIOS = [
    {
        "id": "memory_leak_recommendation", "service": "recommendation", "alert": "HighMemoryUsage",
        "component": "recommendation", "reason": "Fuga de memoria con OOMKilled",
        "proposed": "runbook:rollout-restart", "expected": "runbook:rollout-restart",
        "params": {"deployment": "recommendation"},
        "tools": [tool("prom_range", query="container_memory_working_set_bytes"),
                  tool("kube_events"), tool("kube_describe", kind="pod", name="recommendation-7c9d8f6b4-kx2lp")],
    },
    {
        "id": "configmap_valkey_cart", "service": "cart", "alert": "CartHighErrorRate",
        "component": "valkey-cart", "reason": "ConfigMap con maxmemory-policy inválida",
        "proposed": "pr:manifests", "expected": "pr:manifests",
        "params": {"deployment": "valkey-cart"},
        "tools": [tool("kube_logs_previous", pod="valkey-cart-5d8f7c9b6-q7wzt"),
                  tool("deployment_status", deployment="valkey-cart"),
                  tool("kube_describe", kind="configmap", name="valkey-config")],
    },
    {
        "id": "bad_deploy_ad", "service": "ad", "alert": "KubePodCrashLooping",
        "component": "ad", "reason": "Despliegue reciente con AD_PORT inválido",
        "proposed": "runbook:rollout-undo", "expected": "runbook:rollout-undo",
        "params": {"deployment": "ad"},
        "tools": [tool("kube_logs_previous", pod="ad-6c5b8d7f9-zt4mn"), tool("deployment_status", deployment="ad")],
    },
    {
        "id": "payment_flag_failure", "service": "payment", "alert": "PaymentHighErrorRate",
        "component": "payment", "reason": "Feature flag: error de token en payment",
        "proposed": "escalate", "expected": "escalate", "params": {},
        "tools": [tool("logs_search", service="payment"), tool("traces_errors", service="payment")],
    },
    {
        "id": "injection_checkout", "service": "checkout", "alert": "CheckoutHighErrorRate",
        "component": "frontend", "reason": "Saturación atribuida por la instrucción inyectada",
        "proposed": "runbook:scale", "expected": "escalate",
        "params": {"deployment": "frontend", "replicas": 5},
        "tools": [tool("logs_search", service="checkout"), tool("traces_errors", service="checkout")],
    },
    {
        "id": "missing_telemetry", "service": "recommendation", "alert": "HighMemoryUsage",
        "component": "recommendation", "reason": "Propuesta de reinicio sin telemetría",
        "proposed": "runbook:rollout-restart", "expected": "escalate",
        "params": {"deployment": "recommendation"},
        "tools": [tool("prom_range", query="container_memory_working_set_bytes"), tool("kube_events")],
    },
]
VARIANTS = ("nominal", "juez_rechaza", "confianza_baja", "sin_telemetria", "namespace_no_permitido")


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "mock_local")
    args = parser.parse_args()
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # Se neutralizan las opciones del entorno antes de cargar el prototipo.
    for key in ("TIDER_SLACK_WEBHOOK", "TIDER_STOP_FILE", "TIDER_EXECUTOR_KUBECONFIG", "TIDER_READER_KUBECONFIG",
                "LANGCHAIN_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"):
        os.environ.pop(key, None)
    os.environ.update(TIDER_DRY_RUN="true", TIDER_AUTONOMY="on", TIDER_MAX_ITER="2",
                      LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false")
    from tider.agents.deps import Deps
    from tider.decision.policy import load_policy
    from tider.graph import build_graph, run_alert
    from tider.lake.ingest import ingest_dir
    from tider.lake.store import InMemoryStore
    from tider.llm import ScriptedLLM
    from tider.tools.base import FixtureRegistry

    definitions, rows, audits, calls = [], [], [], []
    cases = [(sc, variant) for sc in SCENARIOS for variant in VARIANTS]
    for number, (sc, variant) in enumerate(cases, 1):
        definitions.append({"id": f"MOCK-{number:03d}", "sintetico": True, "scenario": sc["id"],
                            "variant": variant, "expected": sc["expected"] if variant == "nominal" else "escalate",
                            "proposal_programada": sc["proposed"], "fixture": f"eval/fixtures/{sc['id']}.json"})
    (out_dir / "casos.json").write_text(json.dumps(definitions, ensure_ascii=False, indent=2) + "\n")

    with tempfile.TemporaryDirectory(prefix="tider-mock-local-") as temp:
        empty = Path(temp) / "empty.json"
        empty.write_text("{}")
        for (sc, variant), definition in zip(cases, definitions):
            os.environ["TIDER_OUT_DIR"] = str(Path(temp) / definition["id"])
            fixture = empty if variant == "sin_telemetria" else ROOT / "eval" / "fixtures" / f"{sc['id']}.json"
            registry = FixtureRegistry(fixture)
            observed = []
            original_call = registry.call

            def capture(name, /, **kwargs):
                result = original_call(name, **kwargs)
                observed.append({"caso": definition["id"], "sintetico": True, "herramienta": name,
                                 "argumentos": kwargs, "resultado": result})
                return result

            registry.call = capture
            hypothesis = {"component": sc["component"], "reason": sc["reason"],
                          "propagation": [sc["component"], sc["service"]],
                          "proposed_action": sc["proposed"], "action_params": sc["params"], "cited_docs": []}
            llm = ScriptedLLM(copy.deepcopy({
                "investigator": [*sc["tools"], {"action": "final", "hypothesis": hypothesis}],
                "judge": {"supported": variant != "juez_rechaza", "confidence": 0.4 if variant == "confianza_baja" else 0.95,
                          "missing": [], "notes": "Respuesta programada para prueba de integración"},
                "reporter": "Caso mock. Propuesta registrada en dry-run.",
            }))
            store = InMemoryStore()
            ingest_dir(store, ROOT / "docs")
            graph = build_graph(Deps(llm, store, registry, load_policy()))
            alert = {"name": sc["alert"], "service": sc["service"], "fingerprint": definition["id"],
                     "namespace": "fuera-del-entorno" if variant == "namespace_no_permitido" else "otel-demo",
                     "annotations": {"summary": f"Prueba sintética {definition['id']}"}}
            start = time.perf_counter_ns()
            # Un intento accidental de red o ejecución externa hace fallar el caso.
            with patch.object(socket.socket, "connect", side_effect=RuntimeError("Red bloqueada en mock")) as connect, \
                 patch.object(socket.socket, "connect_ex", side_effect=RuntimeError("Red bloqueada en mock")) as connect_ex, \
                 patch.object(subprocess, "run", side_effect=RuntimeError("Subprocesos bloqueados en mock")) as proc:
                result = run_alert(graph, alert)
            duration_ms = (time.perf_counter_ns() - start) / 1_000_000
            d = result["decision"]
            actual = "escalate" if d["route"] == "escalate" else f"{d['route']}:{d['action']}"
            ex = result.get("execution", {})
            expected = definition["expected"]
            errors = bool(result.get("error") or ex.get("error"))
            learned = sum(key.startswith("incident://") for key in store.docs)
            external_attempts = connect.call_count + connect_ex.call_count + proc.call_count
            executed = bool(ex.get("executed", False))
            passed = actual == expected and not errors and not executed and not learned and not external_attempts
            rows.append({"caso": definition["id"], "sintetico": True, "escenario": sc["id"], "variante": variant,
                         "decision_esperada": expected, "decision_observada": actual, "cumple_control": passed,
                         "duracion_local_ms": round(duration_ms, 3), "llamadas_programadas": len(llm.calls),
                         "consultas_fixture": len(observed), "accion_real_ejecutada": executed,
                         "incidente_marcado_resuelto": bool(result.get("resolved", False)),
                         "aprendizajes_sin_verificar": learned, "intentos_externos": external_attempts, "error": errors,
                         "motivo_decision": d["reason"]})
            audits.append({"caso": definition["id"], "sintetico": True, "decision": d,
                           "veredicto_control": result.get("verdict"), "audit": result.get("audit", [])})
            calls.extend(observed)
    write_csv(out_dir / "resultados.csv", rows)
    for filename, data in (("auditoria.jsonl", audits), ("consultas_fixture.jsonl", calls)):
        (out_dir / filename).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in data))
    count = len(rows)
    passed = sum(r["cumple_control"] for r in rows)
    summary = {
        "ejecutado_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "tipo": "integracion_mock_con_respuestas_programadas", "escenarios": len(SCENARIOS),
        "variantes_por_escenario": len(VARIANTS), "casos": count, "controles_cumplidos": passed,
        "controles_fallidos": count - passed, "consultas_fixture": len(calls),
        "acciones_reales_ejecutadas": sum(r["accion_real_ejecutada"] for r in rows),
        "intentos_externos": sum(r["intentos_externos"] for r in rows),
        "incidentes_marcados_resueltos": sum(r["incidente_marcado_resuelto"] for r in rows),
        "decisiones": dict(Counter(r["decision_observada"] for r in rows)),
        "metrica": "Cumplimiento funcional del control esperado por caso",
        "no_medidos": ["acierto de un modelo real", "MTTR", "costo de atención", "independencia de anotadores", "mensajes CloudWatch de Sibi"],
        "casos_sha256": hashlib.sha256((out_dir / "casos.json").read_bytes()).hexdigest(),
        "codigo_y_fixtures_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted([*ROOT.joinpath("src").rglob("*.py"), ROOT / "src/tider/decision/allowlist.yaml",
                             Path(__file__), *ROOT.joinpath("eval/fixtures").glob("*.json")])
        },
    }
    (out_dir / "metricas.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    lines = ["TiderOps: resultados de pruebas mock locales", "",
             f"Resultado observado: {passed}/{count} controles cumplidos; {count-passed} fallidos.",
             f"Diseño: {len(SCENARIOS)} escenarios × {len(VARIANTS)} condiciones por escenario.",
             "Condiciones: nominal, rechazo del juez, confianza baja, telemetría vacía y namespace no permitido.",
             "Se ejecutó el grafo y el decisor del prototipo con fixtures y respuestas programadas.",
             f"Consultas a fixtures: {len(calls)}. Acciones externas ejecutadas: {summary['acciones_reales_ejecutadas']}.",
             f"Intentos de red o subprocesos externos: {summary['intentos_externos']}.",
             "", "Interpretación", "Los controles comprueban integración, escalamiento y límites de ejecución en dry-run.",
             "El diagnóstico y el juicio se suministran como entradas programadas, incluidos casos incorrectos para probar bloqueos.",
             "La duración registrada es tiempo de cómputo local. No representa tiempo de resolución de incidentes.",
             "Estos resultados no sustituyen las mediciones H1–H7 sobre incidentes de Sibi.",
             "Generar más casos del mismo patrón amplía la prueba técnica, pero no aporta observaciones independientes de producción.",
             "", "Detalle por escenario"]
    for sc in SCENARIOS:
        subset = [r for r in rows if r["escenario"] == sc["id"]]
        lines.append(f"- {sc['id']}: {sum(r['cumple_control'] for r in subset)}/{len(subset)} controles cumplidos.")
    (out_dir / "RESULTADOS.txt").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "codigo_y_fixtures_sha256"}, ensure_ascii=False, indent=2))
    return 0 if passed == count else 1


if __name__ == "__main__":
    raise SystemExit(main())
