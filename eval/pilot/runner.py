"""Orquestador de la validación de firmas y de la campaña (Fase 6, ítem 34; A09, A12, A15).

Modos:
  --dry-run              imprime el plan (casos, etiquetas, tiempo estimado) sin llamar a nada;
  --validate-signatures  inyecta cada mecanismo una vez + una corrida sin falla, corre solo el verificador
                         (brazo `reglas`), calcula la matriz de confusión de firmas y escribe gate.json;
  --campaign             exige gate.json con go = true y el mismo hash de catálogo; corre los casos del plan;
  --rehash               recalcula el hash del protocolo (solo antes de la primera corrida).

Por caso: precondiciones (sin experimento activo, puertos de administración y observador distintos,
registrador fresco, generador de tráfico listo) → separación desde el caso anterior → POST /api/start →
espera la restauración → espera margen posterior + ingesta → huecos del registrador en la ventana →
Tider en un proceso aparte (`tider_case`) → recién entonces lee /api/evidence/<id> (ground truth) y lo
guarda en PILOT_GT_DIR, fuera del Lake y de la carpeta de trazas. Tider nunca recibe el ground truth.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from . import protocol as P

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADMIN = "http://127.0.0.1:8093"
DEFAULT_OBSERVER = "http://127.0.0.1:8092"
DEFAULT_GT = ROOT.parents[1] / "ground_truth" / "piloto"
OUT = ROOT / "out" / "runs"


class Precondition(RuntimeError):
    """El caso no puede correr ahora (se registra como no corrido y se reintenta en otra sesión)."""


class Abort(RuntimeError):
    """Falla sistémica: se detiene la sesión (registrador caído, experimento que no se restaura...)."""


def port_of(url: str) -> int | None:
    parts = urlsplit(url)
    return parts.port or ({"http": 80, "https": 443}.get(parts.scheme))


def check_ports(admin_url: str, observer_url: str, tider_observer_url: str = "") -> None:
    a, o = port_of(admin_url), port_of(observer_url)
    if a is None or o is None or a == o:
        raise Precondition(f"Los puertos de administración ({a}) y del observador ({o}) deben ser distintos.")
    if tider_observer_url and port_of(tider_observer_url) == a:
        raise Precondition("AGENT_OBSERVER_URL de Tider apunta al puerto de administración de ChaosForge.")


class ChaosForgeAdmin:
    """Cliente mínimo del puerto de administración. `http` tiene get(url, timeout) y post(url, json, headers, timeout)."""

    def __init__(self, base_url: str, http=None):
        self.base = base_url.rstrip("/")
        if http is None:
            import httpx

            http = httpx.Client(timeout=15)
        self.http = http

    def _json(self, response, what: str):
        if response.status_code != 200:
            raise Precondition(f"ChaosForge {what}: HTTP {response.status_code} {response.text[:200]}")
        return response.json()

    def state(self) -> dict:
        return self._json(self.http.get(f"{self.base}/api/state", timeout=15), "state")

    def start(self, caso: P.Caso) -> str:
        token = self.state()["csrf"]
        body = {"service": caso.servicio, "duration": caso.duracion}
        if caso.mecanismo != "scale_zero":
            body.update(mechanism=caso.mecanismo, parameters=caso.parametros)
        data = self._json(self.http.post(f"{self.base}/api/start", json=body,
                                         headers={"X-ChaosForge-Token": token}, timeout=30), "start")
        if not data.get("id"):
            raise Precondition(f"ChaosForge no devolvió id: {data}")
        return data["id"]

    def evidence(self, experiment_id: str) -> dict:
        return self._json(self.http.get(f"{self.base}/api/evidence/{experiment_id}", timeout=15), "evidence")


class SubprocessExecutor:
    """Corre `eval.pilot.tider_case` en un proceso aparte, sin las variables del ground truth."""

    def __init__(self, work: Path, timeout: int = 1800):
        self.work, self.timeout = Path(work), timeout

    def __call__(self, spec: dict, out_dir: Path) -> Path:
        self.work.mkdir(parents=True, exist_ok=True)
        spec_path = self.work / f"{spec['case_id']}.spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k not in {"CHAOSFORGE_ADMIN_URL", "PILOT_GT_DIR"}}
        result = subprocess.run([sys.executable, "-m", "eval.pilot.tider_case", "--spec", str(spec_path),
                                 "--out", str(out_dir)], cwd=ROOT, env=env, capture_output=True, text=True,
                                timeout=self.timeout)
        if result.returncode:
            raise RuntimeError(f"tider_case falló ({result.returncode}): {result.stderr[-800:]}")
        return Path(result.stdout.strip().splitlines()[-1])


def neutral_request(protocol: dict, case_id: str, start: datetime, end: datetime) -> dict:
    """La misma solicitud para todos los casos: sin servicio, mecanismo ni id del experimento."""
    s = protocol["solicitud"]
    return {"incident_id": case_id, "objective": s["objetivo"], "scope": s["alcance"],
            "start": start.isoformat(), "end": end.isoformat(), "mode": "gcp"}


def credited(gt: dict | None, mecanismo: str | None) -> tuple[bool, str]:
    """Criterio de admisión (1) a partir de /api/evidence/<id>."""
    if mecanismo is None:
        return True, "sin_falla"
    exp = (gt or {}).get("experiment") or {}
    if mecanismo == "scale_zero":
        kinds = {e.get("kind") for e in (gt or {}).get("events") or []}
        ok = exp.get("state") == "completed" and "scale_requested" in kinds
        return ok, exp.get("state") or "desconocido"
    return exp.get("result") == "effect_observed", exp.get("result") or "desconocido"


class Runner:
    def __init__(self, protocol: dict, *, out_dir: Path, gt_dir: Path, admin: ChaosForgeAdmin, recorder,
                 executor: Callable[[dict, Path], Path], admin_url: str, observer_url: str,
                 tider_observer_url: str = "", lake_path: str = "", clock: Callable[[], datetime] | None = None,
                 sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print,
                 brazos: tuple[str, ...] = ("reglas", "tider")):
        self.protocol, self.out_dir, self.gt_dir = protocol, Path(out_dir), Path(gt_dir)
        self.admin, self.recorder, self.executor = admin, recorder, executor
        self.admin_url, self.observer_url, self.tider_observer_url = admin_url, observer_url, tider_observer_url
        self.lake_path = lake_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep, self.log, self.brazos = sleep, log, brazos
        self.protocol_hash = protocol["hash"]
        self.last_restore: datetime | None = None
        self._check_dirs()

    # --- Comprobaciones de arranque ------------------------------------------------------------------

    def _check_dirs(self):
        gt = self.gt_dir.resolve()
        for other, name in ((self.out_dir, "la carpeta de trazas"), (self.lake_path, "el Context Lake")):
            if other and (gt == Path(other).resolve() or Path(other).resolve() in gt.parents):
                raise Precondition(f"PILOT_GT_DIR no puede estar dentro de {name}.")

    def lock_protocol(self):
        """Fija el hash del protocolo en la primera corrida; después se niega a seguir si cambió."""
        if P.compute_hash(self.protocol) != self.protocol_hash:
            raise Precondition("El hash del protocolo no corresponde a su contenido.")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        lock = self.out_dir / "protocol.lock"
        if lock.exists():
            if lock.read_text(encoding="utf-8").strip() != self.protocol_hash:
                raise Precondition("El protocolo cambió después de la primera corrida de esta carpeta.")
        else:
            lock.write_text(self.protocol_hash + "\n", encoding="utf-8")

    # --- Índice de casos -----------------------------------------------------------------------------

    @property
    def index_path(self) -> Path:
        return self.out_dir / "casos.jsonl"

    def index(self) -> list[dict]:
        if not self.index_path.exists():
            return []
        return [json.loads(line) for line in self.index_path.read_text(encoding="utf-8").splitlines() if line]

    def _append(self, row: dict):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def done(self) -> set[str]:
        return {r["case_id"] for r in self.index() if r["estado"] in {"corrido", "excluido"}}

    def check_experiment_id(self, experiment_id: str):
        if P.is_prohibited(experiment_id, self.protocol):
            raise Abort(f"El experimento {experiment_id} es de historial o descartado: no se reutiliza.")
        if any(r.get("experiment_id") == experiment_id for r in self.index()):
            raise Abort(f"El experimento {experiment_id} ya se usó en otro caso.")

    # --- Precondiciones ------------------------------------------------------------------------------

    def preconditions(self):
        check_ports(self.admin_url, self.observer_url, self.tider_observer_url)
        state = self.admin.state()
        if state.get("active"):
            raise Precondition("Hay un experimento activo en ChaosForge.")
        lg = next((s for s in state.get("services") or [] if s.get("name") == "loadgenerator"), None)
        if lg is not None and not lg.get("ready"):
            raise Precondition("loadgenerator no está listo: sin tráfico no hay síntoma.")
        now = self.clock()
        reg = self.protocol["registrador"]
        gaps = self.recorder.huecos(now - timedelta(seconds=reg["frescura_previa_s"]), now,
                                    timedelta(seconds=reg["max_hueco_s"]))
        if gaps:
            raise Abort(f"El registrador no está fresco: {len(gaps)} huecos en los últimos "
                        f"{reg['frescura_previa_s']} s. ¿Está corriendo tider-recorder?")

    def _wait_until(self, t: datetime):
        while (pending := (t - self.clock()).total_seconds()) > 0:
            self.sleep(min(pending, 30))

    def wait_separation(self, caso: P.Caso):
        if self.last_restore is None:
            return
        v = self.protocol["ventana"]
        rec = v["recuperacion_estimada_s"]["scale_zero" if caso.mecanismo in {None, "scale_zero"} else "otros"]
        self._wait_until(self.last_restore + timedelta(seconds=caso.duracion + rec + v["margen_posterior_s"]))

    def wait_idle(self, experiment_id: str):
        limit = self.clock() + timedelta(seconds=self.protocol["ventana"]["tiempo_max_experimento_s"])
        while self.admin.state().get("active"):
            if self.clock() > limit:
                raise Abort(f"El experimento {experiment_id} no se restauró a tiempo; revisa el panel.")
            self.sleep(10)

    # --- Un caso -------------------------------------------------------------------------------------

    def run_case(self, caso: P.Caso) -> dict:
        P.check_case(caso, self.protocol)
        v = self.protocol["ventana"]
        self.wait_separation(caso)
        self.preconditions()
        t_start = self.clock()
        experiment_id = None
        if caso.mecanismo is not None:
            experiment_id = self.admin.start(caso)
            self.check_experiment_id(experiment_id)
            self.log(f"  {caso.case_id}: experimento {experiment_id}")
            self.wait_idle(experiment_id)
        else:
            self.sleep(caso.duracion)
        t_end = self.clock()
        self.last_restore = t_end
        self.log(f"  {caso.case_id}: restaurado; espera de ingesta {v['margen_posterior_s'] + v['espera_ingesta_s']} s")
        self.sleep(v["margen_posterior_s"] + v["espera_ingesta_s"])
        start = t_start - timedelta(seconds=v["margen_previo_s"])
        end = t_end + timedelta(seconds=v["margen_posterior_s"])
        base_inicio = t_start - (end - t_start)
        row = {"case_id": caso.case_id, **{k: val for k, val in caso.to_dict().items() if k != "case_id"},
               "experiment_id": experiment_id, "t_start": t_start.isoformat(), "t_end": t_end.isoformat(),
               "protocol_hash": self.protocol_hash, "trace": None, "motivo": None}
        gaps = self.recorder.huecos(min(start, base_inicio), end, timedelta(seconds=self.protocol["registrador"]["max_hueco_s"]))
        if gaps:
            row.update(estado="excluido", motivo="registrador_con_huecos")
        else:
            spec = {"case_id": caso.case_id, "request": neutral_request(self.protocol, caso.case_id, start, end),
                    "t0": t_start.isoformat(), "brazos": list(self.brazos),
                    "repeticiones": {k: self.protocol["repeticiones"][k] for k in ("n", "cuando")},
                    "protocol_hash": self.protocol_hash}
            row.update(estado="corrido", trace=str(self.executor(spec, self.out_dir)))
        # Ground truth: recién ahora, después de Tider, y fuera del Lake y de las trazas.
        gt = self.admin.evidence(experiment_id) if experiment_id else None
        if gt is not None:
            folder = self.gt_dir / self.out_dir.name
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{caso.case_id}.json").write_text(
                json.dumps({"case_id": caso.case_id, "experiment_id": experiment_id, "evidence": gt},
                           ensure_ascii=False, indent=1), encoding="utf-8")
        ok, detalle = credited(gt, caso.mecanismo)
        row["acreditada"], row["acreditacion"] = ok, detalle
        if row["estado"] == "corrido" and not ok:
            row.update(estado="excluido", motivo="inyeccion_no_acreditada")
        self._append(row)
        return row

    def run(self, casos: list[P.Caso], *, only: set[str] | None = None, limit: int | None = None) -> list[dict]:
        self.lock_protocol()
        done, rows = self.done(), []
        pending = [c for c in casos if c.case_id not in done and (not only or c.case_id in only)]
        for caso in pending[:limit] if limit else pending:
            self.log(f"{caso.case_id} · {caso.conjunto}/{caso.estrato} · {caso.servicio or '-'} · "
                     f"{caso.mecanismo or 'sin falla'} {caso.duracion}s")
            try:
                rows.append(self.run_case(caso))
            except Precondition as exc:
                self.log(f"  {caso.case_id}: no corrido ({exc})")
                row = {"case_id": caso.case_id, **caso.to_dict(), "estado": "no_corrido", "motivo": "precondicion",
                       "detalle": str(exc), "protocol_hash": self.protocol_hash}
                self._append(row)
                rows.append(row)
        return rows


# --- Modo dry-run ------------------------------------------------------------------------------------


def format_plan(protocol: dict, casos: list[P.Caso]) -> str:
    lines = [f"Protocolo {protocol['nombre']} · hash {protocol['hash'][:12]}", "",
             f"{'caso':5} {'conjunto':10} {'estrato':13} {'servicio':22} {'mecanismo':11} {'dur':>4}  etiqueta"]
    total = 0
    for c in casos:
        e = c.etiqueta(protocol)
        total += P.estimated_seconds(c, protocol)
        lines.append(f"{c.case_id:5} {c.conjunto:10} {c.estrato:13} {c.servicio or '-':22} "
                     f"{c.mecanismo or 'sin falla':11} {c.duracion:>4}  {e.clave} / {e.razon or '-'}")
    inyecciones = sum(c.mecanismo is not None for c in casos)
    lines += ["", f"{len(casos)} casos, {inyecciones} inyecciones, {len(casos) - inyecciones} sin falla; "
                  f"tiempo estimado {total / 3600:.1f} h en serie."]
    return "\n".join(lines)


def _settings():
    from tider.console.settings import Settings

    return Settings.from_env()


def _config_problems(settings, campaign: bool) -> list[str]:
    problems = []
    if settings.pipeline != "v2":
        problems.append("TIDER_PIPELINE=v2")
    if settings.evidence_mode != "gcp":
        problems.append("EVIDENCE_MODE=gcp")
    if not settings.lake_v3_path:
        problems.append("LAKE_V3_PATH")
    if not settings.recorder_db_path:
        problems.append("RECORDER_DB_PATH")
    if campaign and not settings.tider_model:
        problems.append("TIDER_MODEL")
    if campaign and not settings.judge_model:
        problems.append("JUDGE_MODEL")
    if campaign and settings.judge_provider == "openai" and not settings.openai_api_key:
        problems.append("OPENAI_API_KEY")
    return problems


def check_gate(gate_path: Path, catalog_hash: str, protocol_hash: str) -> None:
    if not gate_path.exists():
        raise Precondition(f"Falta {gate_path}: corre antes --validate-signatures (go/no-go, A12).")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if not gate.get("go"):
        raise Precondition("La validación de firmas dio no-go: corrige las firmas y repite la validación.")
    if gate.get("catalogo_hash") != catalog_hash:
        raise Precondition("El catálogo de firmas cambió después de la validación: repite --validate-signatures.")
    if gate.get("protocol_hash") != protocol_hash:
        raise Precondition("La validación se hizo con otro protocolo.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval.pilot.runner", description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-signatures", action="store_true")
    mode.add_argument("--campaign", action="store_true")
    mode.add_argument("--rehash", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--protocol", default=str(P.PROTOCOL))
    parser.add_argument("--out", default=None)
    parser.add_argument("--gate", default=str(OUT / "pilot-validation" / "gate.json"))
    parser.add_argument("--only", default="")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    if args.rehash:
        print(P.rehash(args.protocol))
        return 0
    protocol = P.load(args.protocol)
    casos = P.validation_plan(protocol) if args.validate_signatures else P.campaign_plan(protocol)
    if args.dry_run:
        print(format_plan(protocol, casos))
        return 0

    from tider.console.recorder import Recorder
    from tider.console.signatures import cargar_catalogo

    from .score import signature_gate

    settings = _settings()
    problems = _config_problems(settings, args.campaign)
    if problems:
        print("Falta configurar: " + ", ".join(problems), file=sys.stderr)
        return 2
    catalog_hash = cargar_catalogo().hash
    out = Path(args.out or OUT / ("pilot-validation" if args.validate_signatures else "pilot-campaign"))
    if args.campaign:
        check_gate(Path(args.gate), catalog_hash, protocol["hash"])
    admin_url = os.environ.get("CHAOSFORGE_ADMIN_URL", DEFAULT_ADMIN)
    observer_url = os.environ.get("CHAOSFORGE_OBSERVER_URL", settings.agent_observer_url or DEFAULT_OBSERVER)
    runner = Runner(protocol, out_dir=out, gt_dir=Path(os.environ.get("PILOT_GT_DIR", DEFAULT_GT)),
                    admin=ChaosForgeAdmin(admin_url), recorder=Recorder.from_settings(settings),
                    executor=SubprocessExecutor(out / "_spec"), admin_url=admin_url, observer_url=observer_url,
                    tider_observer_url=settings.agent_observer_url, lake_path=settings.lake_v3_path,
                    brazos=("reglas",) if args.validate_signatures else ("reglas", "tider"))
    try:
        runner.run(casos, only=set(filter(None, args.only.split(","))) or None, limit=args.limit)
    except (Abort, Precondition) as exc:
        print(f"Detenido: {exc}", file=sys.stderr)
        return 1
    if args.validate_signatures:
        gate = signature_gate(protocol, runner.index(), catalog_hash)
        (out / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"go": gate["go"], "matriz": gate["matriz"]}, ensure_ascii=False, indent=1))
        return 0 if gate["go"] else 3
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
