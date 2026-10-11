"""Aislamiento: ninguna prueba escribe en out/ del repo, notifica a Slack ni ejecuta comandos de verdad."""
import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TIDER_OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("TIDER_DRY_RUN", "true")
    for var in ("TIDER_SLACK_WEBHOOK", "TIDER_STOP_FILE", "TIDER_AUTONOMY", "TIDER_EXECUTOR_KUBECONFIG",
                "TIDER_READER_KUBECONFIG", "TIDER_API_TOKEN", "TIDER_MAX_ITER"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path / "out"
