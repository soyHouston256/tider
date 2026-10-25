"""Synthetic evidence fixtures. Scenario names never reach the diagnosis rules."""

import json
from datetime import datetime
from importlib.resources import files

from ..models import Signal


def scenarios() -> list[dict]:
    path = files("tider.console").joinpath("resources/scenarios.json")
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_catalog() -> list[dict]:
    return [{k: v for k, v in item.items() if k != "signals"} for item in scenarios()]


def mock_signals(service: str | None, start: datetime, end: datetime, scenario: str = "redis_down") -> list[Signal]:
    fixture = next((item for item in scenarios() if item["id"] == scenario), None)
    if fixture is None:
        raise ValueError("Escenario desconocido.")
    records = fixture["signals"]
    if service is not None and service not in {record["service"] for record in records}:
        return []
    timestamp = start + (end - start) / 2
    return [Signal(timestamp=timestamp, **record) for record in records]
