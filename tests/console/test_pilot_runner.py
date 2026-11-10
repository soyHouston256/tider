"""Runner de la campaña con ChaosForge, registrador y Tider simulados. Nada toca la red ni el clúster."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from eval.pilot import protocol as P
from eval.pilot import runner as R
from eval.pilot.tider_case import run_case
from tider.console.trace import prompt_hashes

from .test_pipeline_v2 import (
    JUDGE_OK,
    FakeLake,
    FakeLLM,
    investigator_answer,
    pm04_sweeper,
    request,
    settings,
)

EXP = "0f1e2d3c-1111-2222-3333-444455556666"


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


class FakeHTTP:
    """Puerto de administración: un experimento queda activo 2 lecturas de estado y luego se restaura."""

    def __init__(self, ids=(EXP,), active_reads=2, reject=False):
        self.calls, self.ids, self.active_reads, self.reject = [], list(ids), active_reads, reject
        self.active = None

    def _resp(self, code, body):
        return SimpleNamespace(status_code=code, json=lambda: body, text=json.dumps(body))

    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        if url.endswith("/api/state"):
            if self.active and self.active_reads <= 0:
                self.active = None
            elif self.active:
                self.active_reads -= 1
            return self._resp(200, {"csrf": "tok", "active": self.active,
                                    "services": [{"name": "loadgenerator", "ready": 1}]})
        if "/api/evidence/" in url:
            return self._resp(200, {"experiment": {"id": url.rsplit("/", 1)[1], "state": "completed",
                                                   "result": "effect_observed"},
                                    "events": [{"kind": "scale_requested"}]})
        return self._resp(404, {})

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, headers))
        if self.reject:
            return self._resp(409, {"error": "Se necesitan observaciones sanas."})
        self.active = {"id": self.ids[0]}
        return self._resp(200, {"id": self.ids.pop(0)})


class FakeRecorder:
    def __init__(self, gaps=()):
        self.gaps, self.calls = list(gaps), []

    def huecos(self, desde, hasta, max_gap):
        self.calls.append((desde, hasta))
        return self.gaps


class FakeExecutor:
    def __init__(self, sintoma=True):
        self.specs, self.sintoma = [], sintoma

    def __call__(self, spec, out_dir):
        self.specs.append(spec)
        trace = {"case_id": spec["case_id"], "hashes": {"protocolo": spec["protocol_hash"]},
                 "admision": {"sintoma": self.sintoma}, "corridas": []}
        path = out_dir / f"{spec['case_id']}.json"
        path.write_text(json.dumps(trace), encoding="utf-8")
        return path


@pytest.fixture
def protocol():
    return P.load()


def make(tmp_path, protocol, http=None, recorder=None, executor=None, **kw):
    clock = Clock()
    http = http or FakeHTTP()
    args = dict(out_dir=tmp_path / "runs" / "camp", gt_dir=tmp_path / "gt", admin=R.ChaosForgeAdmin("http://127.0.0.1:8093", http),
                recorder=recorder or FakeRecorder(), executor=executor or FakeExecutor(),
                admin_url="http://127.0.0.1:8093", observer_url="http://127.0.0.1:8092", clock=clock,
                sleep=clock.sleep, log=lambda m: None)
    args.update(kw)
    return R.Runner(protocol, **args), http, clock


def caso(protocol, cid="E01"):
    return next(c for c in P.campaign_plan(protocol) if c.case_id == cid)


def test_protocol_hash_is_verified_and_plan_respects_frozen_split(protocol, tmp_path):
    assert protocol["hash"] == P.compute_hash(protocol)
    altered = tmp_path / "p.yaml"
    altered.write_text(P.PROTOCOL.read_text(encoding="utf-8").replace("n_objetivo: 60", "n_objetivo: 30"),
                       encoding="utf-8")
    with pytest.raises(P.ProtocolError):
        P.load(altered)
    plan = P.campaign_plan(protocol)
    ev = [c for c in plan if c.conjunto == "evaluacion"]
    assert len(ev) == 63 and len(plan) == 70
    historial = P.historial_pairs(protocol)
    assert not any((c.servicio, c.mecanismo) in historial for c in plan)
    assert {c.servicio for c in ev if c.mecanismo == "scale_zero"} == {
        "redis-cart", "checkoutservice", "shippingservice", "emailservice", "recommendationservice", "frontend"}
    assert {c.servicio for c in ev if c.mecanismo != "scale_zero"} == {"cartservice"}
    assert P.campaign_plan(protocol) == plan  # determinista


def test_dry_run_prints_plan_without_calling_anything(capsys, monkeypatch):
    monkeypatch.setattr(R, "ChaosForgeAdmin", lambda *a, **k: pytest.fail("dry-run no debe llamar a ChaosForge"))
    assert R.main(["--campaign", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "E01" in out and "C01" in out and "66 inyecciones" in out and "cartservice->redis-cart" in out
    assert R.main(["--validate-signatures", "--dry-run"]) == 0
    assert "V5" in capsys.readouterr().out


def test_refuses_reused_historial_ids(protocol, tmp_path):
    for ident in ("d7db0523-07da-4883-95a6-95c195644553", "a90ebc41-610e-41e5-b7d1-f9d9cdbf7b03", "c9155003-aaaa"):
        assert P.is_prohibited(ident, protocol)
    runner, http, _ = make(tmp_path, protocol, http=FakeHTTP(ids=["41f3a824-05d7-438a-ad3f-ee71bed83c28"]))
    with pytest.raises(R.Abort, match="historial"):
        runner.run([caso(protocol)])
    # Un caso de evaluación sobre un par de historial se rechaza antes de inyectar.
    bad = P.Caso("E99", "evaluacion", "scale_zero", "paymentservice", "scale_zero", 60)
    with pytest.raises(P.ProtocolError):
        P.check_case(bad, protocol)


def test_refuses_duplicate_experiment_id(protocol, tmp_path):
    runner, _, _ = make(tmp_path, protocol, http=FakeHTTP(ids=[EXP, EXP], active_reads=0))
    plan = P.campaign_plan(protocol)
    with pytest.raises(R.Abort, match="ya se usó"):
        runner.run(plan[:2])


def test_refuses_equal_ports(protocol, tmp_path):
    with pytest.raises(R.Precondition, match="distintos"):
        R.check_ports("http://127.0.0.1:8093", "http://localhost:8093")
    with pytest.raises(R.Precondition, match="AGENT_OBSERVER_URL"):
        R.check_ports("http://127.0.0.1:8093", "http://127.0.0.1:8092", "http://127.0.0.1:8093")
    runner, http, _ = make(tmp_path, protocol, observer_url="http://127.0.0.1:8093")
    rows = runner.run([caso(protocol)])
    assert rows[0]["estado"] == "no_corrido" and not any(c[0] == "POST" for c in http.calls)


def test_refuses_active_experiment_and_stale_recorder(protocol, tmp_path):
    http = FakeHTTP()
    http.active = {"id": "otro"}
    http.active_reads = 99
    runner, _, _ = make(tmp_path, protocol, http=http)
    assert runner.run([caso(protocol)])[0]["motivo"] == "precondicion"
    runner, http, _ = make(tmp_path / "b", protocol, recorder=FakeRecorder(gaps=[(1, 2)]))
    with pytest.raises(R.Abort, match="registrador"):
        runner.run([caso(protocol)])
    assert not any(c[0] == "POST" for c in http.calls)


def test_case_flow_keeps_ground_truth_away_from_tider(protocol, tmp_path):
    executor = FakeExecutor()
    runner, http, clock = make(tmp_path, protocol, executor=executor)
    c = caso(protocol)
    t_start = clock()
    row = runner.run([c])[0]
    assert row["estado"] == "corrido" and row["experiment_id"] == EXP and row["acreditada"]
    post = next(x for x in http.calls if x[0] == "POST")
    assert post[3] == {"X-ChaosForge-Token": "tok"} and post[2]["service"] == c.servicio
    # Tider recibe una solicitud neutra: sin servicio, mecanismo ni id del experimento.
    spec = executor.specs[0]
    text = json.dumps(spec)
    assert EXP not in text and c.servicio not in text and "scale_zero" not in text
    assert spec["request"]["scope"] == "general" and spec["request"]["incident_id"] == c.case_id
    assert spec["t0"] == t_start.isoformat()
    # El ground truth se lee después de Tider y se guarda fuera de la carpeta de trazas.
    order = [x[1] for x in http.calls if x[0] == "GET" and "/api/evidence/" in x[1]]
    assert order and http.calls.index(("GET", order[0])) > http.calls.index(post)
    gt = tmp_path / "gt" / "camp" / f"{c.case_id}.json"
    assert json.loads(gt.read_text())["experiment_id"] == EXP
    assert not any("evidence" in p.name for p in (tmp_path / "runs" / "camp").iterdir())
    assert (tmp_path / "runs" / "camp" / "protocol.lock").read_text().strip() == protocol["hash"]
    # Reanudar no repite el caso.
    assert runner.run([c]) == []


def test_gt_dir_cannot_live_inside_traces_or_lake(protocol, tmp_path):
    with pytest.raises(R.Precondition):
        make(tmp_path, protocol, gt_dir=tmp_path / "runs" / "camp" / "gt")
    with pytest.raises(R.Precondition):
        make(tmp_path, protocol, gt_dir=tmp_path / "lake" / "gt", lake_path=str(tmp_path / "lake"))


def test_recorder_gaps_in_window_exclude_case_without_calling_tider(protocol, tmp_path):
    class GapsLater(FakeRecorder):
        def huecos(self, desde, hasta, max_gap):
            self.calls.append((desde, hasta))
            return [] if len(self.calls) == 1 else [(desde, hasta)]

    executor = FakeExecutor()
    runner, _, _ = make(tmp_path, protocol, recorder=GapsLater(), executor=executor)
    row = runner.run([caso(protocol)])[0]
    assert row["estado"] == "excluido" and row["motivo"] == "registrador_con_huecos" and not executor.specs


def test_campaign_requires_go_gate_with_same_catalog(tmp_path):
    gate = tmp_path / "gate.json"
    with pytest.raises(R.Precondition, match="validate-signatures"):
        R.check_gate(gate, "c", "p")
    gate.write_text(json.dumps({"go": False, "catalogo_hash": "c", "protocol_hash": "p"}))
    with pytest.raises(R.Precondition, match="no-go"):
        R.check_gate(gate, "c", "p")
    gate.write_text(json.dumps({"go": True, "catalogo_hash": "viejo", "protocol_hash": "p"}))
    with pytest.raises(R.Precondition, match="catálogo"):
        R.check_gate(gate, "c", "p")
    gate.write_text(json.dumps({"go": True, "catalogo_hash": "c", "protocol_hash": "p"}))
    R.check_gate(gate, "c", "p")


def test_tider_case_trace_has_hashes_and_no_ground_truth_in_llm_inputs(monkeypatch, tmp_path):
    investigator = FakeLLM(investigator_answer, model="investigador")
    judge = FakeLLM(JUDGE_OK, model="juez")
    req = json.loads(request().model_dump_json())
    req["incident_id"] = "E07"
    spec = {"case_id": "E07", "request": req, "t0": "2026-11-09T18:38:54+00:00", "brazos": ["reglas", "tider"],
            "repeticiones": {"n": 3, "cuando": "mas_de_una_firma_confirmada"}, "protocol_hash": "abc"}
    calls = []
    sweeper = pm04_sweeper(monkeypatch, tmp_path)

    def counted(r):
        calls.append(r)
        return sweeper(r)

    trace = run_case(spec, settings=settings(), lake=FakeLake(), sweeper=counted,
                     investigator=investigator, judge=judge)
    assert len(calls) == 1  # evidencia congelada: un solo barrido para todos los brazos
    h = trace["hashes"]
    assert h["prompts"] == prompt_hashes() and len(h["catalogo"]) == 64 and h["protocolo"] == "abc"
    assert h["evidencia_congelada"] and trace["entradas"]["evidencia_congelada"]["filas"]
    assert [(c["brazo"], c["repeticion"]) for c in trace["corridas"]] == [("reglas", 1), ("tider", 1)]
    assert trace["corridas"][1]["evidence_ids"]["hipotesis_1"]
    llamadas = trace["llamadas"]
    assert {c["agent"] for c in llamadas} == {"investigator", "judge"}
    assert all(c["corrida"] == "tider#1" and len(c["input_sha256"]) == 64 and "output" in c for c in llamadas)
    assert trace["admision"]["sintoma"] is True
    # Ninguna entrada al LLM lleva marcas del ground truth ni del laboratorio (los runbooks del Lake sí
    # nombran mecanismos: son antecedentes, no la respuesta del caso).
    for c in llamadas:
        for marca in (EXP, "effect_observed", "scale_requested", "experiment_id", "chaosforge"):
            assert marca not in c["input"].lower()
    assert EXP not in json.dumps(trace)
    assert "api_key" not in json.dumps(trace["settings"]).lower()
