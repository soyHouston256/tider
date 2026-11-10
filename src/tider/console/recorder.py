"""Registrador de estado de Kubernetes (`tider-recorder`), solo lectura y solo de laboratorio (A15).

Cada `RECORDER_INTERVAL_SECONDS` (10 s: una falla de ChaosForge dura 30-120 s, así que una inyección deja
entre 3 y 12 instantáneas) guarda una instantánea del namespace en SQLite (`RECORDER_DB_PATH`):
Deployments, StatefulSets, Services (ClusterIP y puertos, A01), EndpointSlices y Pods. Retención de 48 h.

* Solo ejecuta `kubectl get … -o json` con el kubeconfig de lectura (`AGENT_READER_KUBECONFIG`).
  Ningún camino de este módulo puede modificar el clúster.
* Si `kubectl` falla, la fila se guarda con `ok = 0` y el motivo: así la frescura se puede verificar
  (heartbeat) y una ventana sin instantáneas válidas da SIN_DATOS, nunca el estado actual.

Esquema SQLite::

    snapshots(t TEXT PRIMARY KEY  -- ISO-8601 UTC con microsegundos, ordenable como texto
              ok INTEGER,          -- 1 instantánea completa, 0 lectura fallida
              error TEXT,          -- motivo de la falla, sin salida de kubectl
              payload TEXT)        -- JSON de `Instantanea`
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

KINDS = ("deployments", "statefulsets", "services", "endpointslices", "pods")
READ_ONLY_VERBS = frozenset({"get"})
_ADDR = re.compile(r"^[A-Z0-9_]*_ADDR$")
_ADDR_VALUE = re.compile(r"^[a-z0-9.-]+:[0-9]{1,5}$")


class Carga(BaseModel):
    nombre: str
    tipo: str  # Deployment | StatefulSet
    deseadas: int | None = None
    listas: int = 0
    generacion: int | None = None
    hash_spec: str = ""
    direcciones: dict[str, str] = Field(default_factory=dict)
    imagenes: dict[str, str] = Field(default_factory=dict)
    recursos: dict[str, dict] = Field(default_factory=dict)
    selector: dict[str, str] = Field(default_factory=dict)


class ServiceK8s(BaseModel):
    nombre: str
    cluster_ip: str | None = None
    puertos: list[int] = Field(default_factory=list)


class SliceK8s(BaseModel):
    servicio: str
    listos: int = 0
    direcciones: list[str] = Field(default_factory=list)


class ContenedorK8s(BaseModel):
    nombre: str
    listo: bool | None = None
    reinicios: int | None = None
    terminado_motivo: str | None = None
    terminado_codigo: int | None = None


class PodK8s(BaseModel):
    nombre: str
    etiquetas: dict[str, str] = Field(default_factory=dict)
    fase: str | None = None
    ip: str | None = None
    contenedores: list[ContenedorK8s] = Field(default_factory=list)


class Instantanea(BaseModel):
    tiempo: datetime
    ok: bool = True
    error: str = ""
    cargas: list[Carga] = Field(default_factory=list)
    services: list[ServiceK8s] = Field(default_factory=list)
    endpointslices: list[SliceK8s] = Field(default_factory=list)
    pods: list[PodK8s] = Field(default_factory=list)

    def carga(self, nombre: str) -> Carga | None:
        return next((c for c in self.cargas if c.nombre == nombre), None)

    def endpoints_listos(self, servicio: str) -> int | None:
        slices = [s for s in self.endpointslices if s.servicio == servicio]
        return sum(s.listos for s in slices) if slices else None


def spec_hash(template_spec: dict) -> str:
    """Hash estable de lo que define la configuración: contenedores (imagen, env, args, recursos)."""
    containers = [
        {k: c.get(k) for k in ("name", "image", "env", "envFrom", "args", "command", "resources", "ports")}
        for c in template_spec.get("containers", [])
    ]
    canonical = json.dumps(containers, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _carga(item: dict, tipo: str) -> Carga:
    spec = item.get("spec", {})
    template = spec.get("template", {}).get("spec", {})
    containers = template.get("containers", [])
    return Carga(
        nombre=item["metadata"]["name"],
        tipo=tipo,
        deseadas=spec.get("replicas", 1),
        listas=item.get("status", {}).get("readyReplicas", 0) or 0,
        generacion=item.get("metadata", {}).get("generation"),
        hash_spec=spec_hash(template),
        direcciones={
            e["name"]: e["value"]
            for c in containers
            for e in c.get("env", [])
            if _ADDR.match(e.get("name", ""))
            and isinstance(e.get("value"), str)
            and _ADDR_VALUE.match(e["value"])
        },
        imagenes={c["name"]: c.get("image", "") for c in containers},
        recursos={c["name"]: c.get("resources", {}) for c in containers},
        selector=spec.get("selector", {}).get("matchLabels", {}),
    )


def parse_snapshot(tiempo: datetime, raw: dict[str, dict]) -> Instantanea:
    """Proyecta la salida de `kubectl get -o json` a la instantánea compacta (sin secretos ni env completo)."""
    cargas = [_carga(i, "Deployment") for i in raw["deployments"].get("items", [])]
    cargas += [_carga(i, "StatefulSet") for i in raw["statefulsets"].get("items", [])]
    services = [
        ServiceK8s(
            nombre=i["metadata"]["name"],
            cluster_ip=i.get("spec", {}).get("clusterIP"),
            puertos=sorted({p["port"] for p in i.get("spec", {}).get("ports", []) if "port" in p}),
        )
        for i in raw["services"].get("items", [])
    ]
    slices = []
    for i in raw["endpointslices"].get("items", []):
        svc = i.get("metadata", {}).get("labels", {}).get("kubernetes.io/service-name")
        if not svc:
            continue
        ready = [
            a
            for e in i.get("endpoints") or []
            if (e.get("conditions") or {}).get("ready", True)
            for a in e.get("addresses", [])
        ]
        slices.append(SliceK8s(servicio=svc, listos=len(ready), direcciones=ready))
    pods = []
    for i in raw["pods"].get("items", []):
        status = i.get("status", {})
        conts = []
        for c in status.get("containerStatuses", []) or []:
            term = (
                (c.get("lastState") or {}).get("terminated") or (c.get("state") or {}).get("terminated") or {}
            )
            conts.append(
                ContenedorK8s(
                    nombre=c["name"],
                    listo=c.get("ready"),
                    reinicios=c.get("restartCount"),
                    terminado_motivo=term.get("reason"),
                    terminado_codigo=term.get("exitCode"),
                )
            )
        pods.append(
            PodK8s(
                nombre=i["metadata"]["name"],
                etiquetas=i["metadata"].get("labels", {}),
                fase=status.get("phase"),
                ip=status.get("podIP"),
                contenedores=conts,
            )
        )
    return Instantanea(tiempo=tiempo, cargas=cargas, services=services, endpointslices=slices, pods=pods)


def default_run(args, **kwargs):
    return subprocess.run(args, **kwargs)


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Recorder:
    def __init__(
        self,
        db_path: str | Path,
        namespace: str,
        kubeconfig: str = "",
        context: str = "",
        *,
        run: Callable | None = None,
        now: Callable[[], datetime] | None = None,
        retention: timedelta = timedelta(hours=48),
        timeout_seconds: int = 10,
    ):
        self.db_path = str(Path(db_path).expanduser())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.namespace, self.kubeconfig, self.context = namespace, kubeconfig, context
        self.run, self.now = run, now or (lambda: datetime.now(timezone.utc))
        self.retention, self.timeout_seconds = retention, timeout_seconds
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS snapshots (t TEXT PRIMARY KEY, ok INTEGER NOT NULL, "
                "error TEXT NOT NULL DEFAULT '', payload TEXT NOT NULL)"
            )

    @classmethod
    def from_settings(cls, settings, **kwargs) -> "Recorder":
        if not settings.recorder_db_path:
            raise ValueError("Configura RECORDER_DB_PATH para usar el registrador.")
        return cls(
            settings.recorder_db_path,
            settings.gcp_namespace,
            settings.agent_reader_kubeconfig,
            settings.agent_kube_context,
            retention=timedelta(hours=settings.recorder_retention_hours),
            **kwargs,
        )

    def _kubectl_args(self, kind: str) -> list[str]:
        args = ["kubectl"]
        if self.kubeconfig:
            args += ["--kubeconfig", self.kubeconfig]
        if self.context:
            args += ["--context", self.context]
        args += [
            "--namespace",
            self.namespace,
            f"--request-timeout={self.timeout_seconds}s",
            "get",
            kind,
            "-o",
            "json",
        ]
        verb = args[args.index(f"--request-timeout={self.timeout_seconds}s") + 1]
        if verb not in READ_ONLY_VERBS:  # defensa en profundidad: el registrador nunca escribe
            raise RuntimeError("El registrador solo usa verbos de lectura.")
        return args

    def _get(self, kind: str) -> dict:
        run = self.run or default_run  # resuelto en cada llamada (las pruebas lo sustituyen)
        result = run(
            self._kubectl_args(kind), capture_output=True, text=True, timeout=self.timeout_seconds + 2
        )
        if result.returncode:
            raise RuntimeError(
                f"kubectl get {kind} falló (código {result.returncode}); revisa permisos y contexto."
            )
        return json.loads(result.stdout)

    def capture(self) -> Instantanea:
        tiempo = self.now()
        try:
            snap = parse_snapshot(tiempo, {kind: self._get(kind) for kind in KINDS})
        except Exception as exc:  # se registra el hueco; nunca se rellena con otro estado
            snap = Instantanea(tiempo=tiempo, ok=False, error=f"{type(exc).__name__}: {exc}"[:300])
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT OR REPLACE INTO snapshots(t, ok, error, payload) VALUES (?, ?, ?, ?)",
                (_iso(tiempo), int(snap.ok), snap.error, snap.model_dump_json()),
            )
        self.prune()
        return snap

    def prune(self) -> int:
        with sqlite3.connect(self.db_path) as db:
            return db.execute(
                "DELETE FROM snapshots WHERE t < ?", (_iso(self.now() - self.retention),)
            ).rowcount

    def snapshots(self, desde: datetime, hasta: datetime, *, solo_ok: bool = True) -> list[Instantanea]:
        query = "SELECT payload FROM snapshots WHERE t >= ? AND t <= ?" + (" AND ok = 1" if solo_ok else "")
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute(query + " ORDER BY t", (_iso(desde), _iso(hasta))).fetchall()
        return [Instantanea.model_validate_json(row[0]) for row in rows]

    def spec_at(self, servicio: str, t: datetime) -> Carga | None:
        """Configuración vigente de `servicio` en `t`: la última instantánea válida en o antes de `t`."""
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute(
                "SELECT payload FROM snapshots WHERE t <= ? AND ok = 1 ORDER BY t DESC", (_iso(t),)
            ).fetchall()
        for row in rows:
            carga = Instantanea.model_validate_json(row[0]).carga(servicio)
            if carga is not None:
                return carga
        return None

    def huecos(self, desde: datetime, hasta: datetime, max_gap: timedelta) -> list[tuple[datetime, datetime]]:
        """Intervalos sin instantánea válida más largos que `max_gap` (frescura, A15)."""
        marcas = [desde, *(s.tiempo for s in self.snapshots(desde, hasta)), hasta]
        return [(a, b) for a, b in zip(marcas, marcas[1:]) if b - a > max_gap]

    def run_forever(self, interval: float, *, iterations: int | None = None, sleep=time.sleep) -> None:
        done = 0
        while iterations is None or done < iterations:
            started = time.monotonic()
            self.capture()
            done += 1
            sleep(max(0.0, interval - (time.monotonic() - started)))


def main(argv: list[str] | None = None) -> int:
    from .settings import Settings

    parser = argparse.ArgumentParser(
        prog="tider-recorder", description="Registrador de estado K8s, solo lectura."
    )
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--once", action="store_true", help="Toma una sola instantánea y termina.")
    args = parser.parse_args(argv)
    settings = Settings.from_env(args.env_file)
    recorder = Recorder.from_settings(settings)
    if args.once:
        snap = recorder.capture()
        print(json.dumps({"t": _iso(snap.tiempo), "ok": snap.ok, "error": snap.error}))
        return 0 if snap.ok else 1
    recorder.run_forever(settings.recorder_interval_seconds)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
