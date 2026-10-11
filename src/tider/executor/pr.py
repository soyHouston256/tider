"""PR sobre el repo de manifiestos. MVP: escribe el parche propuesto en out/prs/ para revisión humana.
Semana 4: reemplazar por la API de GitHub (crear rama + PR)."""
from __future__ import annotations
import json, time
from pathlib import Path
from ..config import ROOT


def propose(action: str, params: dict, alert: dict, summary: str) -> dict:
    out = ROOT / "out" / "prs"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{int(time.time())}-{action}.json"
    f.write_text(json.dumps({"action": action, "params": params, "alert": alert, "summary": summary}, indent=2, ensure_ascii=False))
    return {"executed": False, "proposal": str(f)}
