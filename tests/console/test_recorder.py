from datetime import timedelta
from pathlib import Path

import yaml

from tider.console.evidence.gke import from_snapshots
from tider.console.recorder import KINDS, Recorder, main

from .pilot_fakes import FakeCluster, FakeKubectl, record, utc

ROOT = Path(__file__).resolve().parents[2]


def test_recorder_stores_and_reads_snapshots_with_services(tmp_path):
    rec = record(Recorder, tmp_path / "rec.db", FakeCluster(), utc(18, 30), utc(18, 32))
    snaps = rec.snapshots(utc(18, 30), utc(18, 32))
    assert len(snaps) == 5 and all(s.ok for s in snaps)
    snap = snaps[0]
    assert {c.nombre for c in snap.cargas} >= {"paymentservice", "shippingservice", "loadgenerator"}
    pay = next(s for s in snap.services if s.nombre == "paymentservice")
    assert (pay.cluster_ip, pay.puertos) == ("10.49.5.115", [50051])
    assert snap.endpoints_listos("paymentservice") == 1 and snap.endpoints_listos("loadgenerator") is None
    assert rec.snapshots(utc(18, 31), utc(18, 31, 30))[0].tiempo == utc(18, 31)


def test_recorder_only_issues_read_only_kubectl_get(tmp_path):
    cluster = FakeCluster()
    record(Recorder, tmp_path / "rec.db", cluster, utc(18, 30), utc(18, 31))
    assert cluster.calls and len(cluster.calls) == 3 * len(KINDS)
    for args in cluster.calls:
        assert args[0] == "kubectl" and args[args.index("get") - 1].startswith("--request-timeout")
        assert args[-2:] == ["-o", "json"] and "--kubeconfig" in args
        mutating = {
            "apply",
            "delete",
            "patch",
            "scale",
            "edit",
            "replace",
            "rollout",
            "set",
            "label",
            "annotate",
        }
        assert not mutating & set(args)


def test_failed_capture_is_recorded_as_gap_never_as_current_state(tmp_path):
    now = [utc(18, 30)]
    rec = Recorder(
        tmp_path / "rec.db",
        "boutique",
        run=FakeKubectl(FakeCluster(), lambda: now[0], fail_kinds={"services"}),
        now=lambda: now[0],
        retention=timedelta(days=3650),
    )
    snap = rec.capture()
    assert not snap.ok and "services" in snap.error and "forbidden" not in snap.error
    assert rec.snapshots(utc(18, 29), utc(18, 31)) == []
    assert len(rec.snapshots(utc(18, 29), utc(18, 31), solo_ok=False)) == 1
    assert rec.huecos(utc(18, 29), utc(18, 31), timedelta(seconds=20)) == [(utc(18, 29), utc(18, 31))]


def test_spec_at_returns_configuration_in_force_and_detects_config_change(tmp_path):
    def overrides(t, name):
        if name == "cartservice":
            addr = "redis-cart:6380" if t >= utc(18, 31) else "redis-cart:6379"
            return {
                "env": [{"name": "REDIS_ADDR", "value": addr}],
                "generation": 2 if t >= utc(18, 31) else 1,
            }
        return {}

    rec = record(Recorder, tmp_path / "rec.db", FakeCluster(overrides=overrides), utc(18, 30), utc(18, 32))
    assert rec.spec_at("cartservice", utc(18, 30, 45)).direcciones == {"REDIS_ADDR": "redis-cart:6379"}
    assert rec.spec_at("cartservice", utc(18, 31, 5)).direcciones == {"REDIS_ADDR": "redis-cart:6380"}
    assert rec.spec_at("cartservice", utc(18, 29)) is None and rec.spec_at("nada", utc(18, 31)) is None
    _, _, _, cambios = from_snapshots(rec.snapshots(utc(18, 30), utc(18, 32)), "boutique")
    (cambio,) = cambios
    assert (
        cambio.tipo == "config_cambiada" and cambio.servicio == "cartservice" and cambio.tiempo == utc(18, 31)
    )
    assert '"REDIS_ADDR":["redis-cart:6379","redis-cart:6380"]' in cambio.texto_original


def test_retention_prunes_old_snapshots(tmp_path):
    now = [utc(10, 0)]
    rec = Recorder(
        tmp_path / "rec.db",
        "boutique",
        run=FakeKubectl(FakeCluster(), lambda: now[0]),
        now=lambda: now[0],
        retention=timedelta(hours=48),
    )
    rec.capture()
    now[0] += timedelta(hours=49)
    rec.capture()
    assert len(rec.snapshots(utc(0, 0), now[0], solo_ok=False)) == 1


def test_main_once_uses_settings(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RECORDER_DB_PATH", str(tmp_path / "r.db"))
    monkeypatch.setattr("tider.console.recorder.default_run", FakeKubectl(FakeCluster(), lambda: utc(18, 30)))
    assert main(["--once"]) == 0
    assert '"ok": true' in capsys.readouterr().out


def test_reader_rbac_is_read_only_and_covers_services():
    docs = list(yaml.safe_load_all((ROOT / "deploy" / "reader-rbac.yaml").read_text()))
    role = next(d for d in docs if d["kind"] == "Role")
    granted = {(g, r) for rule in role["rules"] for g in rule["apiGroups"] for r in rule["resources"]}
    assert {
        ("", "pods"),
        ("", "services"),
        ("", "events"),
        ("apps", "deployments"),
        ("apps", "statefulsets"),
        ("apps", "replicasets"),
        ("discovery.k8s.io", "endpointslices"),
    } == granted
    assert all(set(rule["verbs"]) <= {"get", "list"} for rule in role["rules"])
    assert not any("secrets" in rule["resources"] for rule in role["rules"])
    binding = next(d for d in docs if d["kind"] == "RoleBinding")
    assert binding["subjects"][0]["name"] == "tider-reader" and binding["roleRef"]["kind"] == "Role"
