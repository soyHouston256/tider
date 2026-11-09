#!/usr/bin/env python3
"""Activa/desactiva un feature flag de falla del OpenTelemetry Demo editando el ConfigMap de flagd.
Uso: python scripts/inject_fault.py recommendationServiceCacheFailure on
     python scripts/inject_fault.py recommendationServiceCacheFailure off
VERIFICAR contra tu versión del chart: nombre del ConfigMap (--cm) y de la clave (--key), y los nombres de los flags
(kubectl -n otel-demo get cm). Flags habituales: cartServiceFailure, productCatalogFailure, adServiceHighCpu,
adServiceManualGc, kafkaQueueProblems, paymentServiceFailure, recommendationServiceCacheFailure, imageSlowLoad.
"""
import argparse, json, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument("flag"); ap.add_argument("state", choices=["on", "off"])
ap.add_argument("-n", "--namespace", default="otel-demo")
ap.add_argument("--cm", default="flagd-config")
ap.add_argument("--key", default="demo.flagd.json")
a = ap.parse_args()

cm = json.loads(subprocess.check_output(["kubectl", "-n", a.namespace, "get", "cm", a.cm, "-o", "json"]))
cfg = json.loads(cm["data"][a.key])
if a.flag not in cfg["flags"]:
    sys.exit(f"flag '{a.flag}' no existe. Disponibles: {', '.join(cfg['flags'])}")
cfg["flags"][a.flag]["defaultVariant"] = "on" if a.state == "on" else "off"
cm["data"][a.key] = json.dumps(cfg, indent=2)
subprocess.run(["kubectl", "apply", "-f", "-"], input=json.dumps(cm), text=True, check=True)
print(f"{a.flag} -> {a.state}")
