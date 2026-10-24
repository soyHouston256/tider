"""PR sobre el repo de manifiestos. MVP: escribe el parche propuesto en out/prs/ para revisión humana.
Semana 4: reemplazar por la API de GitHub (crear rama + PR)."""

from __future__ import annotations

import json
import time
import uuid

from ..config import out_dir
from .escalate import notify, safe_name


def propose(action: str, params: dict, alert: dict, summary: str) -> dict:
    out = out_dir() / "prs"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{time.strftime('%Y%m%dT%H%M%S')}-{safe_name(action)}-{uuid.uuid4().hex[:6]}.json"
    f.write_text(
        json.dumps(
            {"action": action, "params": params, "alert": alert, "summary": summary},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    notify(f"Tider propone un PR ({action}) para {alert.get('name')}: {summary}")
    return {"executed": False, "proposal": str(f)}
