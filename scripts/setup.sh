#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v uv >/dev/null 2>&1; then
  echo 'Instala uv para crear el entorno con las versiones de uv.lock.' >&2
  exit 1
fi
uv sync --frozen --extra dev --extra gcp --extra llm --python 3.12
