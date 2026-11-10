"""Aislamiento: ninguna prueba escribe en out/ del repo, notifica a Slack ni ejecuta comandos de verdad."""

import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TIDER_OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("TIDER_DRY_RUN", "true")
    for var in (
        "TIDER_SLACK_WEBHOOK",
        "TIDER_STOP_FILE",
        "TIDER_AUTONOMY",
        "TIDER_EXECUTOR_KUBECONFIG",
        "TIDER_READER_KUBECONFIG",
        "TIDER_API_TOKEN",
        "TIDER_MAX_ITER",
    ):
        monkeypatch.delenv(var, raising=False)
    return tmp_path / "out"


@pytest.fixture(autouse=True)
def clean_console_env(monkeypatch):
    """Las pruebas no heredan la configuración del shell (historial, proveedor LLM, fuente, modelo, pipeline)."""
    for var in (
        "INVESTIGATION_HISTORY_PATH",
        "LLM_PROVIDER",
        "EVIDENCE_MODE",
        "TIDER_MODEL",
        "TIDER_PIPELINE",
        "RECORDER_DB_PATH",
        "LAKE_V3_PATH",
        "JUDGE_PROVIDER",
        "JUDGE_MODEL",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def no_real_kubectl(monkeypatch):
    """El registrador nunca llama a un kubectl real en las pruebas: cada prueba inyecta uno simulado."""

    def forbidden(*args, **kwargs):
        raise AssertionError("Las pruebas no pueden ejecutar kubectl real.")

    monkeypatch.setattr("tider.console.recorder.default_run", forbidden)
