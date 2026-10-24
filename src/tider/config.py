import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def out_dir() -> Path:
    """Escalamientos, PRs propuestos y el archivo STOP. El eval y las pruebas lo apuntan a otro lado."""
    return Path(env("TIDER_OUT_DIR", str(ROOT / "out")))


def dry_run() -> bool:
    return env("TIDER_DRY_RUN", "true").lower() != "false"


def max_iter() -> int:
    """Rondas Investigador->Juez en total (incluida la primera)."""
    return int(env("TIDER_MAX_ITER", "2"))


def verify_timeout() -> int:
    return int(env("TIDER_VERIFY_TIMEOUT", "600"))


def verify_interval() -> int:
    return int(env("TIDER_VERIFY_INTERVAL", "30"))


def autonomy_enabled() -> bool:
    """Interruptor de apagado: TIDER_AUTONOMY=off o el archivo TIDER_STOP_FILE (por defecto out/STOP) frenan toda
    acción automática al instante, sin reiniciar. Se lee en cada decisión."""
    if env("TIDER_AUTONOMY", "on").lower() == "off":
        return False
    return not Path(env("TIDER_STOP_FILE", str(out_dir() / "STOP"))).exists()
