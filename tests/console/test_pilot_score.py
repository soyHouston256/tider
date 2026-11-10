"""Puntuación del piloto desde trazas sintéticas, sin proveedores (Fase 6, ítem 38)."""

import csv
import json

import pytest

from eval.pilot import protocol as P
from eval.pilot import score as S
from eval.pilot.judge_set import build, mutate
from eval.pilot.kappa_form import cohen_kappa, export, kappa_from_files
from eval.quality.score import paired


@pytest.fixture(scope="module")
def protocol():
    return P.load()


SVC = lambda s: {"tipo": "servicio", "servicio": s}  # noqa: E731
LINK = lambda o, d: {"tipo": "enlace", "origen": o, "destino": d}  # noqa: E731


def analysis(entidad, razon, status="hypothesis", executed=False, avisos=(), nodos=()):
    return {"status": status, "hipotesis": [{"entidad": entidad, "razon": razon, "citas": [{"id": "S0001"}]}]
            if entidad else [], "workflow": {"execution": {"executed": executed}},
            "investigation": {"avisos": list(avisos), "firmas": []}, "nodos": list(nodos),
            "hypothesis": f"{razon} en {entidad}", "recommendation": "kubectl get pods", "evidence": []}


def trace(case_id, protocol_hash, reps, reglas=None, sintoma=True, confirmadas=1, llamadas=()):
    corridas = [{"brazo": "tider", "repeticion": i, "elapsed_seconds": e, "error": None, "analysis": a}
                for i, (a, e) in enumerate(reps, 1)]
    if reglas:
        corridas.append({"brazo": "reglas", "repeticion": 1, "elapsed_seconds": 1, "error": None, "analysis": reglas})
    return {"case_id": case_id, "hashes": {"protocolo": protocol_hash}, "admision": {"sintoma": sintoma},
            "firmas_confirmadas_tienda": [f"x@{i}" for i in range(confirmadas)], "corridas": corridas,
            "llamadas": list(llamadas), "entradas": {"evidencia_congelada": None}}


def row(cid, conjunto, estrato, servicio, mecanismo, estado="corrido"):
    return {"case_id": cid, "conjunto": conjunto, "estrato": estrato, "servicio": servicio, "mecanismo": mecanismo,
            "estado": estado, "acreditada": True}


def test_service_and_link_scoring(protocol):
    link = P.etiqueta(protocol, "cartservice", "latency")
    assert link.clave == "cartservice->redis-cart" and link.razon == "dependencia-lenta"
    assert S.entity_match(link, LINK("cartservice", "redis-cart")) == {"exacto": True, "parcial": False}
    assert S.entity_match(link, SVC("redis-cart")) == {"exacto": False, "parcial": True}
    assert S.entity_match(link, SVC("cartservice"))["parcial"]
    assert S.entity_match(link, LINK("redis-cart", "cartservice")) == {"exacto": False, "parcial": False}
    svc = P.etiqueta(protocol, "checkoutservice", "scale_zero")
    assert S.entity_match(svc, SVC("checkoutservice"))["exacto"]
    assert S.entity_match(svc, LINK("checkoutservice", "paymentservice")) == {"exacto": False, "parcial": False}
    assert S.entity_match(svc, None) == {"exacto": False, "parcial": False}


def test_repetitions_collapse_per_case_before_interval(protocol):
    label = P.etiqueta(protocol, "frontend", "scale_zero")
    ok = {"analysis": analysis(SVC("frontend"), "servicio-sin-instancias"), "elapsed_seconds": 50}
    bad = {"analysis": analysis(SVC("cartservice"), "servicio-sin-instancias"), "elapsed_seconds": 90}
    other = {"analysis": analysis(SVC("adservice"), "saturacion-cpu"), "elapsed_seconds": 70}
    two_of_three = S.collapse([S.score_rep(label, c) for c in (ok, bad, ok)])
    assert two_of_three["exacto"] and two_of_three["mayoria"] and two_of_three["latencia_caso"] == 50
    none = S.collapse([S.score_rep(label, c) for c in (ok, bad, other)])
    assert not none["exacto"] and not none["mayoria"] and none["afirmacion_incorrecta"]  # empate = error
    # 3 repeticiones de un caso pesan como un caso (no como 3 en el Wilson).
    idx = [row("E01", "evaluacion", "scale_zero", "frontend", "scale_zero")]
    tr = {"E01": trace("E01", protocol["hash"], [(ok["analysis"], 50), (bad["analysis"], 90), (ok["analysis"], 60)],
                       confirmadas=2)}
    res = S.score_campaign(protocol, idx, tr)
    assert res["principal"]["exactitud"]["n"] == 1 and res["principal"]["exactitud"]["hits"] == 1
    assert res["descriptivo"]["mas_de_una_confirmada"]["hits"] == 1


def _campaign(protocol, n_ok, n_bad, latency=60):
    idx, tr = [], {}
    for i in range(n_ok + n_bad):
        cid = f"E{i + 1:02}"
        idx.append(row(cid, "evaluacion", "scale_zero", "frontend", "scale_zero"))
        a = analysis(SVC("frontend") if i < n_ok else SVC("cartservice"), "servicio-sin-instancias")
        tr[cid] = trace(cid, protocol["hash"], [(a, latency)], reglas=a)
    return idx, tr


def test_thresholds_on_wilson_bounds(protocol):
    idx, tr = _campaign(protocol, 58, 2)
    res = S.score_campaign(protocol, idx, tr)["principal"]
    assert res["exactitud"]["wilson95"][0] > .70 and res["umbrales"]["exactitud"]
    assert res["umbrales"]["afirmaciones_incorrectas"] and res["pasa"]
    idx, tr = _campaign(protocol, 45, 15, latency=150)
    res = S.score_campaign(protocol, idx, tr)["principal"]
    assert not res["umbrales"]["exactitud"] and not res["umbrales"]["latencia_p95"] and not res["pasa"]
    idx, tr = _campaign(protocol, 20, 0)  # n < 60 y aceptar_n_menor: false
    assert not S.score_campaign(protocol, idx, tr)["principal"]["umbrales"]["n_suficiente"]


def test_exclusions_actions_controls_and_foreign_protocol(protocol):
    idx, tr = _campaign(protocol, 2, 0)
    idx += [row("E03", "evaluacion", "scale_zero", "frontend", "scale_zero", estado="excluido") | {"motivo": "registrador_con_huecos"},
            row("E04", "evaluacion", "scale_zero", "frontend", "scale_zero"),
            row("C01", "control", "loadgenerator", "loadgenerator", "scale_zero"),
            row("C02", "control", "sin_falla", None, None)]
    tr["E04"] = trace("E04", protocol["hash"], [(analysis(SVC("frontend"), "x", executed=True), 1)], sintoma=False)
    lg = analysis(None, None, status="insufficient_evidence",
                  avisos=["Generación de tráfico detenida: loadgenerator sin instancias"],
                  nodos=[{"servicio": "frontend", "tipo": "tienda"}])
    tr["C01"] = trace("C01", protocol["hash"], [(lg, 10)])
    tr["C02"] = trace("C02", protocol["hash"], [(analysis(SVC("frontend"), "servicio-sin-instancias"), 10)])
    res = S.score_campaign(protocol, idx, tr)
    assert {e["case_id"]: e["motivo"] for e in res["excluidos"]} == {"E03": "registrador_con_huecos", "E04": "sin_sintoma"}
    assert res["descriptivo"]["controles"]["loadgenerator"]["hits"] == 1
    assert res["descriptivo"]["controles"]["sin_falla"]["hits"] == 0  # respaldó una causa sin falla
    assert "PASA" in S.report_markdown(res) or "NO PASA" in S.report_markdown(res)
    tr["E01"]["hashes"]["protocolo"] = "otro"
    with pytest.raises(ValueError, match="otro protocolo"):
        S.score_campaign(protocol, idx, tr)


def test_exact_mcnemar_with_known_pairs():
    # 1 par discordante a favor del primero y 6 a favor del segundo: p = 2 * (1 + 7) / 2**7 = 0.125.
    first = [True] * 1 + [False] * 6 + [True] * 3
    second = [False] * 1 + [True] * 6 + [True] * 3
    r = paired(first, second)
    assert (r["first_only"], r["second_only"]) == (1, 6) and r["exact_two_sided_p"] == pytest.approx(0.125)
    decisions = [{"origen": "natural", "verdadero": True, "aprobado": True},
                 {"origen": "natural", "verdadero": False, "aprobado": False},
                 {"origen": "natural", "verdadero": False, "aprobado": True},
                 {"origen": "fabricado", "verdadero": False, "aprobado": False}]
    j = S.judge_scores(decisions)
    assert j["natural"]["falsa_aprobacion"]["hits"] == 1 and j["natural"]["falso_rechazo"]["hits"] == 0
    assert j["fabricado"]["falsa_aprobacion"]["n"] == 1
    assert j["mcnemar_natural_exploratorio"]["first_only"] == 1  # el juez acierta donde aprobar-todo falla


def test_cohen_kappa_textbook_example():
    # 50 ítems: sí/sí 20, sí/no 5, no/sí 10, no/no 15 -> po = .70, pe = .50, κ = .40.
    a = ["si"] * 25 + ["no"] * 25
    b = ["si"] * 20 + ["no"] * 5 + ["si"] * 10 + ["no"] * 15
    k = cohen_kappa(a, b)
    assert k["po"] == pytest.approx(.7) and k["pe"] == pytest.approx(.5) and k["kappa"] == pytest.approx(.4)
    assert k["ic95"][0] < .4 < k["ic95"][1]


def test_signature_confusion_and_gate(protocol):
    plan = P.validation_plan(protocol)
    idx, tr = [], {}
    confirm = {"V1": ["servicio-sin-instancias@productcatalogservice"], "V2": ["configuracion-incorrecta@cartservice"],
               "V3": ["dependencia-lenta@cartservice->redis-cart"], "V4": ["saturacion-cpu@cartservice"], "V5": []}
    for c in plan:
        idx.append(row(c.case_id, "validacion", c.estrato, c.servicio, c.mecanismo))
        tr[c.case_id] = {"firmas_confirmadas_tienda": confirm[c.case_id]}
    gate = S.signature_gate(protocol, idx, "cat", traces=tr)
    assert gate["go"] and gate["matriz"]["ninguna"] == {"ninguna": 1}
    tr["V3"]["firmas_confirmadas_tienda"].append("configuracion-incorrecta@cartservice")  # caso A20
    gate = S.signature_gate(protocol, idx, "cat", traces=tr)
    assert not gate["go"] and gate["matriz"]["dependencia-lenta"]["configuracion-incorrecta"] == 1
    assert "no-go" in S.report_markdown(S.score_campaign(protocol, [], {}), gate=gate)


def _judge_trace(protocol, cid, servicio):
    payload = {"diagnostico": {"resumen": f"{servicio} sin instancias",
                               "hipotesis": [{"entidad": SVC(servicio), "firma_id": "servicio-sin-instancias",
                                              "razon": "servicio-sin-instancias",
                                              "citas": [{"id": "S0001", "clase": "evidencia"}, {"id": "D01", "clase": "antecedente"}]}]},
               "citas_resueltas": {"S0001": {"texto": "x"}, "D01": {"texto": "rb"}},
               "tabla": [{"servicio": servicio, "rol": "causa"}, {"servicio": "checkoutservice", "rol": "victima"},
                         {"servicio": "adservice", "rol": "ninguno"}]}
    inv = {"hipotesis": [{"orden": 1, "entidad": servicio, "firma_id": "servicio-sin-instancias"}]}
    llamadas = [{"corrida": "tider#1", "agent": "investigator", "output": inv, "input": "{}"},
                {"corrida": "tider#1", "agent": "judge", "output": {"supported": True}, "input": json.dumps(payload)}]
    t = trace(cid, protocol["hash"], [(analysis(SVC(servicio), "servicio-sin-instancias"), 10)], llamadas=llamadas)
    t["entradas"]["evidencia_congelada"] = {"evidencia": {"senales": [
        {"id": "S0009", "servicio": "adservice", "texto_original": "ad ok", "tiempo": "t"}]}}
    return t, payload


def test_judge_set_ratio_and_mutations(protocol):
    idx, tr = [], {}
    for i, svc in enumerate(["frontend", "emailservice", "shippingservice"], 1):
        cid = f"E{i:02}"
        idx.append(row(cid, "evaluacion", "scale_zero", svc, "scale_zero"))
        tr[cid], payload = _judge_trace(protocol, cid, svc)
    cands = build(protocol, idx, tr)
    nat = [c for c in cands if c["origen"] == "natural"]
    fab = [c for c in cands if c["origen"] == "fabricado"]
    assert len(nat) == 3 and all(c["verdadero"] and c["aprobado"] for c in nat)
    assert len(fab) == 3 and not any(c["verdadero"] for c in fab)  # 1:1
    assert len({c["transformacion"] for c in fab}) == 3  # round-robin entre transformaciones
    assert build(protocol, idx, tr) == cands  # semilla fija
    import random
    rng = random.Random(0)
    swapped = mutate(payload, "intercambio_causa_victima", tr["E03"], rng)
    assert swapped["diagnostico"]["hipotesis"][0]["entidad"] == SVC("checkoutservice")
    only_d = mutate(payload, "solo_antecedentes", tr["E03"], rng)
    assert [c["id"] for c in only_d["diagnostico"]["hipotesis"][0]["citas"]] == ["D01"]
    irrelevant = mutate(payload, "citas_irrelevantes", tr["E03"], rng)
    assert "S0009" in irrelevant["citas_resueltas"] and "S0001" not in irrelevant["citas_resueltas"]
    assert mutate(payload, "razon_cambiada", tr["E03"], rng)["diagnostico"]["hipotesis"][0]["firma_id"] != \
        "servicio-sin-instancias"
    assert all("verdadero" not in json.dumps(c["payload"]) for c in fab)


def test_kappa_form_is_blind_and_roundtrips(protocol, tmp_path):
    idx, tr = [], {}
    for i in range(40):
        cid = f"E{i + 1:02}"
        estrato = ["scale_zero", "wrong_port", "latency", "cpu_limit"][i % 4]
        mec = estrato
        svc = "frontend" if mec == "scale_zero" else "cartservice"
        idx.append(row(cid, "evaluacion", estrato, svc, mec))
        a = analysis(SVC(svc), "x")
        tr[cid] = trace(cid, protocol["hash"], [(a, 5)], reglas=a)
    form, key = export(protocol, idx, tr, tmp_path)
    text = form.read_text(encoding="utf-8")
    assert "tider" not in text and "reglas" not in text and "E01" not in text
    lines = [x for x in text.splitlines() if not x.startswith("#")]
    rows = list(csv.DictReader(lines))
    assert len(rows) == 30 and {"Q1", "Q2", "Q3"} <= set(rows[0])
    variantes = [v["variante"] for v in json.loads(key.read_text())["items"].values()]
    assert variantes.count("tider") == 15
    for name, answer in (("a.csv", "si"), ("b.csv", "si")):
        with (tmp_path / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows({**r, "Q1": answer, "Q2": "no" if r["item"] < "K10" else "si", "Q3": "si"} for r in rows)
    k = kappa_from_files(protocol, tmp_path / "a.csv", tmp_path / "b.csv", key_path=key)
    assert k["Q2"]["kappa"] == pytest.approx(1.0)
