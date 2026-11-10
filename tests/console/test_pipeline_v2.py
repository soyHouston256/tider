"""Pipeline v2 de punta a punta (Fase 3) sobre evidencia con forma de PM-04, con LLM y juez simulados.

Barrido → Cartógrafo → verificador → estado → roles → Investigador → Proponente → reglas fijas → Juez.
Ningún proveedor real: el Investigador y el Juez son clientes simulados distintos.
"""

import json
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from tider.console.analysis import LabEngine
from tider.console.context_lake import front_matter
from tider.console.models import Analysis, AnalyzeRequest
from tider.console.pipeline_v2 import PipelineV2
from tider.console.recorder import Recorder
from tider.console.service import AnalysisService
from tider.console.settings import Settings
from tider.console.signatures import cargar_catalogo
from tider.console.sweep import sweep

from .pilot_fakes import FakeCluster, install_logging, load, record, utc

FIXTURES = Path(__file__).parent / "fixtures"
INICIO, T0, FIN = utc(18, 33, 54), utc(18, 38, 54), utc(18, 46, 21)
ABAJO, ARRIBA, LISTO = utc(18, 38, 55), utc(18, 40, 55), utc(18, 41, 4)


class FakeLake:
    """Lake v3 en memoria: vía por clave (`get`) y topología, leídos de las fixtures."""

    def __init__(self):
        self.docs = {}
        for path in sorted((FIXTURES / "lake_v3").glob("*/*.md")):
            meta, body = front_matter(path.read_text(encoding="utf-8"))
            tipo = meta.get("tipo_doc")
            for campo in {"ficha": ("servicio",), "runbook": ("id", "modo_falla")}.get(tipo, ()):
                self.docs[(tipo, str(meta[campo]))] = {"name": path.name, "text": body, "tipo_doc": tipo}

    def get(self, tipo, clave):
        return self.docs.get((tipo, clave))

    def get_topology(self):
        return yaml.safe_load((FIXTURES / "topologia.yaml").read_text(encoding="utf-8"))

    def manifest(self):
        return {"documentos": len(self.docs)}


class FakeLLM:
    """Cliente con la interfaz `complete_json`; registra cada llamada (agente y texto recibido)."""

    def __init__(self, respuestas, model="fake"):
        self.respuestas = list(respuestas) if isinstance(respuestas, list) else [respuestas]
        self.calls: list[tuple[str, str]] = []
        self.model = model

    def complete_json(self, agent, system, user, *, timeout=None):
        self.calls.append((agent, user))
        r = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        return r(user) if callable(r) else r


def settings(**kw):
    return Settings(evidence_mode="gcp", pipeline="v2", healthy_traffic_min_lines=2, **kw)


def pm04_sweeper(monkeypatch, tmp_path, *, proxy=False, logs=True, events=None, overrides=None):
    def scaled(t, name):
        o = dict(overrides(t, name)) if overrides else {}
        if name == "paymentservice" and overrides is None:
            o.update(replicas=0 if ABAJO <= t < ARRIBA else 1, ready=0 if ABAJO <= t < LISTO else 1)
        if proxy and name == "cartservice":
            o["env"] = [{"name": "REDIS_ADDR", "value": "chaosforge-proxy:6379"}]
        return o

    rec = record(Recorder, tmp_path / "pm04.db", FakeCluster(proxy=proxy, overrides=scaled),
                 T0 - (FIN - T0) - timedelta(minutes=1), FIN, step=timedelta(seconds=10))
    install_logging(monkeypatch, load("pm04-logs.json") if logs else [],
                    load("pm04-eventos.json") if events is None else events)
    cfg = settings()
    return lambda request: sweep(request, cfg, t0=T0, recorder=rec)


def request():
    return AnalyzeRequest(incident_id="PM-04", start=INICIO, end=FIN, mode="gcp",
                          objective="Los pagos fallan, investiga")


def confirmed_ids(analysis):
    return next(f["evidencia_ids"] for f in analysis.investigation["firmas"] if f["veredicto"] == "CONFIRMADA")


def investigator_answer(user):
    payload = json.loads(user)
    firma = payload["firmas_confirmadas"][0]
    return {"resumen": f"paymentservice sin instancias ({firma['evidencia_ids'][0]}).",
            "hipotesis": [{"orden": 1, "entidad": firma["entidad"], "firma_id": firma["firma_id"],
                           "rol": "causa", "citas": firma["evidencia_ids"][:3] + ["D01"]}],
            "cambios_rol": []}


JUDGE_OK = {"supported": True, "notes": "Deployment a 0 réplicas y errores de frontend hacia su ClusterIP."}


def test_pm04_without_llm_produces_analysis_v2(monkeypatch, tmp_path):
    result = PipelineV2(settings(), FakeLake(), sweeper=pm04_sweeper(monkeypatch, tmp_path)).run(request())
    assert result.schema_version == 2 and result.engine == "pipeline-v2" and result.reasoning_mode == "rules"
    h = result.hipotesis[0]
    assert (h.entidad.servicio, h.razon, h.firma_id, h.rol) == (
        "paymentservice", "servicio-sin-instancias", "servicio-sin-instancias", "causa")
    assert h.t_inicio == ABAJO and result.component == "paymentservice"
    roles = {n.servicio: n.rol_en_principal for n in result.nodos}
    assert roles["paymentservice"] == "causa"
    assert {n for n, r in roles.items() if r == "victima"} == {"frontend", "checkoutservice"}
    estados = {n.servicio: n.estado for n in result.nodos}
    assert estados["paymentservice"] == "falla"
    assert {a.estado for a in result.aristas} <= {"falla", "sano", "sin_datos"}
    # RB-01 está `validado: false` → pasos de solo lectura rellenados, no la acción de catálogo.
    rec = result.recomendacion_estructurada
    assert rec.tipo == "diagnostico_no_verificado" and rec.runbook_id == "RB-01" and not rec.validada
    assert "SVC=paymentservice" in rec.texto and "10.49.5.115:50051" in rec.texto
    assert "scale" not in rec.texto and rec.texto.startswith("Sugerencia no verificada")
    assert result.status == "hypothesis" and not result.investigation["reglas_juez"]["rechazos"]
    assert result.incompleto is False
    assert result.recommendation == rec.texto and result.evidence
    assert result.workflow.execution["executed"] is False


def test_validated_runbook_returns_catalog_action_and_passes_rule_4(monkeypatch, tmp_path):
    catalogo = cargar_catalogo()
    firma = catalogo.firma("servicio-sin-instancias")
    catalogo.firmas[catalogo.firmas.index(firma)] = firma.model_copy(update={"validado": True})
    result = PipelineV2(settings(), FakeLake(), sweeper=pm04_sweeper(monkeypatch, tmp_path),
                        catalogo=catalogo).run(request())
    rec = result.recomendacion_estructurada
    assert rec.tipo == "catalogo" and rec.validada and rec.runbook_id == "RB-01"
    assert "kubectl -n boutique scale deploy/paymentservice" in rec.texto
    assert result.status == "hypothesis"  # A07: la regla 4 no se aplica a la acción de catálogo


def test_pm04_with_llm_neutralizes_lab_names_and_uses_separate_judge(monkeypatch, tmp_path):
    investigator = FakeLLM(investigator_answer, model="investigador")
    judge = FakeLLM(JUDGE_OK, model="juez")
    pipe = PipelineV2(settings(), FakeLake(), investigator=investigator, judge=judge,
                      sweeper=pm04_sweeper(monkeypatch, tmp_path, proxy=True))
    result = pipe.run(request())
    assert result.status == "hypothesis" and result.reasoning_mode == "agentic"
    assert result.investigation["review_status"] == "passed"
    assert {a for a, _ in investigator.calls} == {"investigator"} and {a for a, _ in judge.calls} == {"judge"}
    assert investigator is not judge and result.investigation["judge_model"] == "juez"
    # El Investigador recibe solo firmas CONFIRMADAS.
    payload = json.loads(investigator.calls[0][1])
    assert [f["firma_id"] for f in payload["firmas_confirmadas"]] == ["servicio-sin-instancias"]
    firmas = {(f["entidad"], f["veredicto"]) for f in result.investigation["firmas"]}
    assert any(v != "CONFIRMADA" for _, v in firmas)  # hubo otras evaluadas que no se entregaron
    # P9: ningún LLM recibe `chaosforge`, y el análisis guardado tampoco lo contiene.
    assert pipe.llm_inputs and all("chaosforge" not in t.lower() for t in pipe.llm_inputs)
    assert "componente-auxiliar" in investigator.calls[0][1]
    assert "chaosforge" not in result.model_dump_json().lower()
    assert any("componente auxiliar" in d for d in result.discrepancias)


def test_judge_llm_can_ask_for_one_more_round_only(monkeypatch, tmp_path):
    investigator = FakeLLM(investigator_answer)
    judge = FakeLLM({"supported": False, "notes": "Falta contrastar el orden.", "otra_ronda": True})
    result = PipelineV2(settings(), FakeLake(), investigator=investigator, judge=judge,
                        sweeper=pm04_sweeper(monkeypatch, tmp_path)).run(request())
    assert len(investigator.calls) == 2 and len(judge.calls) == 2  # máximo una ronda adicional
    assert result.status == "partial" and result.investigation["review_status"] == "rejected"
    assert result.hypothesis.startswith("Hipótesis no respaldada")


def test_fixed_rule_rejection_gives_the_investigator_a_second_round(monkeypatch, tmp_path):
    def bad(user):
        answer = investigator_answer(user)
        answer["hipotesis"][0]["citas"] = ["S9999"]
        return answer

    investigator = FakeLLM([bad, investigator_answer])
    judge = FakeLLM(JUDGE_OK)
    result = PipelineV2(settings(), FakeLake(), investigator=investigator, judge=judge,
                        sweeper=pm04_sweeper(monkeypatch, tmp_path)).run(request())
    assert len(investigator.calls) == 2 and len(judge.calls) == 1
    assert "regla 1" in json.loads(investigator.calls[1][1])["correcciones"]
    assert result.status == "hypothesis"


def test_role_change_applies_only_when_judge_accepts(monkeypatch, tmp_path):
    def with_role(user):
        answer = investigator_answer(user)
        answer["cambios_rol"] = [{"servicio": "adservice", "rol": "victima", "justificacion": "prueba",
                                  "citas": []}]
        return answer

    for aceptados, esperado in (([], "ninguno"), (["adservice"], "victima")):
        result = PipelineV2(settings(), FakeLake(), investigator=FakeLLM(with_role),
                            judge=FakeLLM({**JUDGE_OK, "cambios_rol_aceptados": aceptados}),
                            sweeper=pm04_sweeper(monkeypatch, tmp_path / str(len(aceptados)))).run(request())
        assert {n.servicio: n.rol_en_principal for n in result.nodos}["adservice"] == esperado
        trace = result.investigation["cambios_rol"][0]
        assert trace["rol_codigo"] == "ninguno" and trace["rol_propuesto"] == "victima"
        assert trace["aceptado"] is bool(aceptados)


def test_loadgenerator_scaled_to_zero_reports_traffic_stopped_not_a_store_cause(monkeypatch, tmp_path):
    def overrides(t, name):
        return {"replicas": 0, "ready": 0} if name == "loadgenerator" and t >= ABAJO else {}

    evento = load("pm04-eventos.json")[0]
    evento = json.loads(json.dumps(evento).replace("paymentservice", "loadgenerator"))
    investigator = FakeLLM(investigator_answer)
    result = PipelineV2(settings(), FakeLake(), investigator=investigator, judge=FakeLLM(JUDGE_OK),
                        sweeper=pm04_sweeper(monkeypatch, tmp_path, logs=False, events=[evento],
                                             overrides=overrides)).run(request())
    assert result.hipotesis == [] and result.component == "desconocida"
    assert result.status == "insufficient_evidence"
    assert "Generación de tráfico detenida: loadgenerator" in result.hypothesis
    assert investigator.calls == []  # sin firmas confirmadas de la tienda no hay nada que ordenar
    assert result.recomendacion_estructurada.tipo == "diagnostico_no_verificado"


def test_lab_engine_v2_without_llm_skips_v1_provider(monkeypatch, tmp_path):
    sweeper = pm04_sweeper(monkeypatch, tmp_path)
    monkeypatch.setattr("tider.console.pipeline_v2.sweep", lambda req, cfg: sweeper(req))

    class NoProvider:
        def load(self, request):
            raise AssertionError("v2 no consulta la fuente v1")

    cfg = settings()
    result = AnalysisService(cfg, NoProvider(), LabEngine(cfg, FakeLake())).analyze(request())
    assert result.schema_version == 2 and result.component == "paymentservice"


def test_v2_rejects_mock_evidence_mode():
    cfg = Settings(evidence_mode="mock", pipeline="v2")
    with pytest.raises(ValueError, match="EVIDENCE_MODE=gcp"):
        PipelineV2(cfg).run(AnalyzeRequest(incident_id="X", start=INICIO, end=FIN))


def test_v1_analysis_without_v2_fields_still_parses():
    saved = {"incident_id": "OLD", "hypothesis": "h", "component": "cartservice", "confidence": None,
             "evidence": [], "recommendation": "r"}
    old = Analysis.model_validate_json(json.dumps(saved))
    assert old.schema_version == 1 and old.hipotesis == [] and old.recomendacion_estructurada is None
    assert Settings().pipeline == "v1"


def test_every_v2_stage_has_a_label_in_the_console(monkeypatch, tmp_path):
    from tider.console.explanation import TITLES

    static = Path(__file__).parents[2] / "src" / "tider" / "console" / "static" / "js"
    flow = (static / "flow.js").read_text(encoding="utf-8")
    result = PipelineV2(settings(), FakeLake(), investigator=FakeLLM(investigator_answer), judge=FakeLLM(JUDGE_OK),
                        sweeper=pm04_sweeper(monkeypatch, tmp_path)).run(request())
    stages = list(dict.fromkeys(step.stage for step in result.decision_steps))
    assert stages == ["sweep", "cartographer", "signatures", "investigator", "proposer", "judge", "reporter"]
    assert "verificador" not in stages  # no colisiona con la etapa del grafo archivado
    for stage in stages:
        assert stage in TITLES and f"['{stage}'," in flow
    assert "schema_version === 2" in (static / "catalog.js").read_text(encoding="utf-8")
