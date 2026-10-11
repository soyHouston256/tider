import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)

def dry_run() -> bool:
    return env("TIDER_DRY_RUN", "true").lower() != "false"

def max_iter() -> int:
    return int(env("TIDER_MAX_ITER", "2"))
