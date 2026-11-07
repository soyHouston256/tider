#!/bin/sh
# Recalculate both frozen arms without contacting a model or modifying the reference.
set -eu
cd "$(dirname "$0")/../../.."
.venv/bin/python - <<'PY'
from eval.quality.followup.compare import DATA, check_inputs, read, summarize
check_inputs()
if summarize() != read(DATA / "summary.json"):
    raise SystemExit("Diferencia en las capturas o en su puntuación")
print("Comparación reproducida a partir de las 12 investigaciones y los dos rankings.")
PY
