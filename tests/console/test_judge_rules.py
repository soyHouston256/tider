"""Reglas fijas del Juez, Proponente determinista y cliente propio del Juez (Fase 3)."""

import sys
from types import SimpleNamespace

import pytest

from tider.console.agentic import AgenticEngine, build_judge
from tider.console.estado import asignar_roles, estado_aristas
from tider.console.judge_rules import aplicar, comandos_mutantes
from tider.console.models import AnalyzeRequest, Cita, Entidad, Hipotesis, Recomendacion
from tider.console.proposer import propose, seccion
from tider.console.settings import Settings
from tider.console.signatures import ordenar_confirmadas
from tider.llm import OpenAILLM

from .test_estado import CATALOGO, correr
from .test_pipeline_v2 import FIN, INICIO, FakeLake, FakeLLM


@pytest.fixture
def pm04(monkeypatch, tmp_path):
    barrido, grafo, veredictos, nodos, atribucion = correr("PM-04", monkeypatch, tmp_path, k=2)
    confirmadas = ordenar_confirmadas(veredictos, barrido.evidencia)
    roles = asignar_roles(confirmadas[0], grafo, nodos, barrido, atribucion)
    aristas = estado_aristas(grafo, nodos, veredictos, atribucion)
    return SimpleNamespace(barrido=barrido, ev=barrido.evidencia, confirmadas=confirmadas,
                           nodos=list(roles.values()), aristas=aristas)


def hip(v, citas=None, **kw):
    return Hipotesis(orden=kw.pop("orden", 1), entidad=kw.pop("entidad", v.entidad), t_inicio=v.t_inicio,
                     razon=v.firma_id, firma_id=v.firma_id,
                     citas=[Cita(id=i, clase="evidencia") for i in (citas or v.evidencia_ids)], **kw)


LECTURA = Recomendacion(tipo="diagnostico_no_verificado", texto="kubectl -n boutique get pods -o wide")


def reglas(p, hipotesis, rec=LECTURA, **kw):
    args = dict(evidencia=p.ev, antecedentes={"D01"}, nodos=p.nodos, aristas=p.aristas, confirmadas=p.confirmadas)
    return aplicar(hipotesis, rec, **{**args, **kw})


def test_valid_pm04_diagnosis_passes(pm04):
    r = reglas(pm04, [hip(pm04.confirmadas[0])])
    assert r.aprobado and not r.incompleto


def test_rejects_cause_entity_not_in_falla(pm04):
    v = pm04.confirmadas[0]
    otra = hip(v, entidad=Entidad.de_servicio("checkoutservice"))
    r = reglas(pm04, [otra])
    assert any("regla 2" in m and "no está CONFIRMADA" in m for m in r.rechazos)
    assert any("regla 2: la entidad causa checkoutservice" in m for m in r.rechazos)


def test_rejects_citation_of_nonexistent_evidence(pm04):
    v = pm04.confirmadas[0]
    r = reglas(pm04, [hip(v, citas=[*v.evidencia_ids, "S9999"])])
    assert r.rechazos == ["regla 1: la cita S9999 de la hipótesis 1 no existe en la evidencia"]
    con_lake = hip(v)
    con_lake.citas.append(Cita(id="D07", clase="antecedente"))
    assert any("D07" in m for m in reglas(pm04, [con_lake]).rechazos)


def test_rejects_cause_without_evidence_on_its_own_entity(pm04):
    v = pm04.confirmadas[0]
    frontend = [i for i in v.evidencia_ids if pm04.ev.por_id()[i].servicio == "frontend"]
    r = reglas(pm04, [hip(v, citas=frontend)])
    assert any("no tiene citas de evidencia sobre su entidad" in m for m in r.rechazos)


def test_rule_4_rejects_mutating_command_only_in_unverified_text(pm04):
    h = [hip(pm04.confirmadas[0])]
    texto = "kubectl -n boutique get deploy paymentservice\nkubectl -n boutique scale deploy/paymentservice --replicas=1"
    r = reglas(pm04, h, Recomendacion(tipo="diagnostico_no_verificado", texto=texto))
    assert any(m.startswith("regla 4") and "scale" in m for m in r.rechazos)
    assert reglas(pm04, h, Recomendacion(tipo="catalogo", runbook_id="RB-01", texto=texto, validada=True)).aprobado


def test_low_coverage_marks_incompleto_without_rejecting(pm04):
    truncados = [n.model_copy(update={"truncado": True}) if n.tipo == "tienda" and n.servicio not in
                 {"paymentservice", "frontend"} else n for n in pm04.nodos]
    r = reglas(pm04, [hip(pm04.confirmadas[0])], nodos=truncados)
    assert r.aprobado and r.incompleto and r.cobertura < 0.8 and "cobertura" in r.motivo_incompleto


def test_rule_3_requires_coherent_order_with_several_confirmed(pm04):
    v = pm04.confirmadas[0]
    tardia = v.model_copy(update={"entidad": Entidad.de_servicio("frontend"), "t_inicio": FIN})
    confirmadas = [v, tardia]
    sin_motivo = reglas(pm04, [hip(v)], confirmadas=confirmadas)
    assert any("regla 3" in m for m in sin_motivo.rechazos)
    con_t = hip(v, justificacion_orden=f"Empieza a las {v.t_inicio:%H:%M:%S}, antes que frontend.")
    assert not any("regla 3" in m for m in reglas(pm04, [con_t], confirmadas=confirmadas).rechazos)
    cambio = next(c for c in pm04.ev.cambios if c.servicio == "paymentservice")
    con_cambio = hip(v, justificacion_orden=f"Cambio previo {cambio.id} sobre paymentservice.")
    assert not any("regla 3" in m for m in reglas(pm04, [con_cambio], confirmadas=confirmadas).rechazos)


def test_mutating_command_detection_uses_read_only_subcommands():
    lectura = """kubectl -n $NS get deploy $SVC -o wide
kubectl -n $NS describe deploy $SVC | sed -n '/Events:/,$p'
kubectl rollout history deploy/x
gcloud logging read 'jsonPayload.reason="ScalingReplicaSet"' --project tider-ops
- confirma las réplicas con `kubectl rollout history`
aws ecs describe-services --cluster c"""
    assert comandos_mutantes(lectura) == []
    for texto in ("kubectl -n boutique delete pod x", "kubectl exec -it x -- sh", "kubectl label pod x a=b",
                  "kubectl rollout restart deploy/x", "aws ecs update-service --cluster c --service s",
                  "x && kubectl --context lab patch deploy x -p {}", "helm upgrade x ."):
        assert comandos_mutantes(texto), texto


def test_proposer_reads_runbook_sections_and_falls_back_to_generic_step(pm04):
    lake = FakeLake()
    rb01 = lake.get("runbook", "RB-01")["text"]
    pasos = seccion(rb01, "Pasos de verificación")
    assert pasos.startswith("```sh") and "kubectl -n $NS get hpa" in pasos and "## " not in pasos
    v = pm04.confirmadas[0]
    rec = propose([hip(v)], pm04.confirmadas, CATALOGO, lambda rid: None, evidencia=pm04.ev)
    assert rec.tipo == "diagnostico_no_verificado" and "get deploy,statefulset" in rec.texto
    vacia = propose([], [], CATALOGO, lambda rid: rb01)
    assert vacia.runbook_id is None and not comandos_mutantes(vacia.texto)


# --- Juez con cliente propio ------------------------------------------------------------------


def test_build_judge_openai_requires_key_package_and_model(monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_judge(Settings(judge_model="m"))
    with pytest.raises(ValueError, match="paquete `openai`"):
        build_judge(Settings(judge_model="m", openai_api_key="k"))
    with pytest.raises(ValueError, match="JUDGE_MODEL"):
        build_judge(Settings(openai_api_key="k"))


def test_openai_judge_parses_json_and_records_metadata(monkeypatch):
    sent = {}

    class Completions:
        def create(self, **kw):
            sent.update(kw)
            message = SimpleNamespace(content='{"supported": true, "notes": "ok"}')
            return SimpleNamespace(model="m", choices=[SimpleNamespace(message=message, finish_reason="stop")],
                                   usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3))

    class Client:
        def __init__(self, **kw):
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Client))
    judge = build_judge(Settings(judge_model="m", openai_api_key="secreto"))
    assert isinstance(judge, OpenAILLM)
    assert judge.complete_json("judge", "s", "u", timeout=5) == {"supported": True, "notes": "ok"}
    assert sent["timeout"] == 5 and judge.last_response_metadata["input_tokens"] == 10
    assert "secreto" not in str(judge.last_response_metadata)


def test_agentic_engine_v2_uses_a_different_client_for_the_judge(monkeypatch):
    captured = {}

    class Pipe:
        def __init__(self, settings, lake, *, investigator, judge):
            captured.update(investigator=investigator, judge=judge)

        def run(self, request, emit=None):
            return "v2"

    monkeypatch.setattr("tider.console.pipeline_v2.PipelineV2", Pipe)
    cfg = Settings(pipeline="v2", llm_provider="anthropic", tider_model="m", evidence_mode="gcp")
    req = AnalyzeRequest(incident_id="X", start=INICIO, end=FIN)
    investigator, judge = FakeLLM({}), FakeLLM({})
    assert AgenticEngine(cfg, None, investigator, judge=judge).analyze_live(req) == "v2"
    assert captured["investigator"] is investigator and captured["judge"] is judge
    with pytest.raises(ValueError, match="cliente distinto"):
        AgenticEngine(cfg, None, investigator, judge=investigator).analyze_live(req)
