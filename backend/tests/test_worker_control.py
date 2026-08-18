from __future__ import annotations

import asyncio
from pathlib import Path
import json
import time
from types import SimpleNamespace
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from across_agents_assistant.worker_control import (
    ListenerConfiguration,
    WorkerCoordinatorPresenceCache,
    WorkerControlError,
    WorkerNetworkRuntimeManager,
    WorkerTrustStore,
    merge_coordinator_presence,
    reset_worker_trust_store_for_tests,
)


class Clock:
    def __init__(self):
        self.value = 1_800_000_000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def test_live_coordinator_presence_clears_stale_host_drain_after_worker_update():
    host = {
        "nodes": [{"node_id": "node-updated", "state": "draining", "draining": True}],
        "health": {"online_count": 0, "incompatible_count": 0},
    }
    live = {
        "nodes": [{
            "node_id": "node-updated",
            "state": "online_idle",
            "draining": False,
            "transport": "direct",
        }]
    }

    merged = merge_coordinator_presence(host, live)

    assert merged["nodes"][0]["state"] == "online_idle"
    assert merged["nodes"][0]["draining"] is False
    assert merged["health"]["online_count"] == 1


def capability(node_id="node-test", **overrides):
    value = {
        "schema_version": "across-node-capability/1.0",
        "node_id": node_id,
        "worker_version": "0.10.3",
        "protocol_versions": ["across-worker-session/1.0"],
        "os": "macos",
        "os_version": "13.7.8",
        "architecture": "x86_64",
        "cpu_count": 8,
        "memory_bytes": 16 * 1024**3,
        "disk_available_bytes": 100 * 1024**3,
        "executors": ["bounded-process"],
        "isolation_level": "bounded",
        "verification_status": "verified",
        "capability_source": "local-probe",
    }
    value.update(overrides)
    return value


def identity(node_id="node-test"):
    public_key_pem = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    import hashlib

    fingerprint = hashlib.sha256(json.dumps({"public_key": public_key_pem}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "node_id": node_id,
        "display_name": "Remote Worker",
        "algorithm": "ed25519",
        "fingerprint": fingerprint,
        "public_key_pem": public_key_pem,
    }


def submit(store, pairing, *, node_id="node-test"):
    return store.submit_pairing(
        {
            "enrollment_id": pairing["enrollment_id"],
            "pairing_code": pairing["pairing_code"],
            "public_identity": identity(node_id),
            "capability_summary": capability(node_id),
        }
    )


def test_pairing_is_single_use_expires_and_never_persists_raw_code(tmp_path):
    clock = Clock()
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json", clock=clock)
    pairing = store.create_pairing()
    raw_code = pairing["pairing_code"]
    pending = submit(store, pairing)
    assert pending["state"] == "pending_approval"
    assert raw_code not in (tmp_path / "worker.json").read_text()
    assert raw_code not in (tmp_path / "secrets.json").read_text()
    assert (tmp_path / "secrets.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(WorkerControlError, match="rejected"):
        submit(store, pairing)
    expired = store.create_pairing()
    clock.advance(601)
    with pytest.raises(WorkerControlError, match="rejected"):
        submit(store, expired)


def test_approval_presence_drain_revoke_and_remove_are_explicit(tmp_path):
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    store.configure_listener({"enabled": True, "bind_host": "127.0.0.1", "port": 39463})
    pairing = store.create_pairing()
    pending = submit(store, pairing)
    with pytest.raises(WorkerControlError, match="does not match"):
        store.approve("node-test", "000000")
    approved = store.approve("node-test", pending["verification_code"])
    assert approved["state"] == "offline"
    assert approved["transport"] == "direct"
    online = store.update_presence("node-test", state_value="online_idle", transport="direct", quality={"rtt_ms": 4})
    assert online["state"] == "online_idle"
    assert store.action("node-test", "drain")["node"]["state"] == "draining"
    assert store.action("node-test", "revoke")["node"]["state"] == "revoked"
    assert store.action("node-test", "remove")["removed"] is True
    assert store.snapshot()["nodes"] == []


def test_approved_activation_can_only_be_polled_by_device_key_and_nonce_is_single_use(tmp_path):
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    store.configure_listener({"enabled": True, "bind_host": "127.0.0.1", "port": 39463})
    pairing = store.create_pairing()
    key = Ed25519PrivateKey.generate()
    public_key_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    import hashlib

    public_identity = {
        "node_id": "node-proof",
        "display_name": "Proof Worker",
        "algorithm": "ed25519",
        "fingerprint": hashlib.sha256(json.dumps({"public_key": public_key_pem}, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "public_key_pem": public_key_pem,
    }
    pending = store.submit_pairing(
        {
            "enrollment_id": pairing["enrollment_id"],
            "pairing_code": pairing["pairing_code"],
            "public_identity": public_identity,
            "capability_summary": capability("node-proof"),
        }
    )
    store.approve("node-proof", pending["verification_code"])
    proof = {
        "schema_version": "across-worker-activation-proof/1.0",
        "node_id": "node-proof",
        "enrollment_id": pairing["enrollment_id"],
        "nonce": "nonce-proof-1234567890",
    }
    signature = __import__("base64").urlsafe_b64encode(
        key.sign(json.dumps(proof, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    ).decode().rstrip("=")
    activation = store.activation_for_worker(signature=signature, **{key: value for key, value in proof.items() if key != "schema_version"})
    assert activation["status"] == "approved"
    assert activation["activation"]["transport"] == "direct"
    with pytest.raises(WorkerControlError, match="already used"):
        store.activation_for_worker(signature=signature, **{key: value for key, value in proof.items() if key != "schema_version"})


def test_approved_worker_rotates_expired_identity_without_pairing_again(tmp_path):
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    store.configure_listener({"enabled": True, "bind_host": "127.0.0.1", "port": 39463})
    pairing = store.create_pairing()
    device_key = Ed25519PrivateKey.generate()
    public_key_pem = device_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    import hashlib
    import base64

    pending = store.submit_pairing(
        {
            "enrollment_id": pairing["enrollment_id"],
            "pairing_code": pairing["pairing_code"],
            "public_identity": {
                "node_id": "node-renewal",
                "display_name": "Renewal Worker",
                "algorithm": "ed25519",
                "fingerprint": hashlib.sha256(json.dumps({"public_key": public_key_pem}, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                "public_key_pem": public_key_pem,
            },
            "capability_summary": capability("node-renewal"),
        }
    )
    approved = store.approve("node-renewal", pending["verification_code"])
    original_fingerprint = approved["certificate_fingerprint"]

    def signed_proof(generation, nonce):
        proof = {
            "schema_version": "across-worker-identity-renewal-proof/1.0",
            "node_id": "node-renewal",
            "current_generation": generation,
            "nonce": nonce,
        }
        signature = base64.urlsafe_b64encode(
            device_key.sign(json.dumps(proof, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        ).decode().rstrip("=")
        return {**{key: value for key, value in proof.items() if key != "schema_version"}, "signature": signature}

    renewed = store.renew_identity_for_worker(**signed_proof(1, "renewal-nonce-1234567890"))
    assert renewed["status"] == "renewed"
    assert renewed["node"]["session_generation"] == 2
    assert renewed["node"]["certificate_fingerprint"] != original_fingerprint
    assert renewed["activation"]["session_generation"] == 2
    assert renewed["activation"]["certificate_not_after"] > time.time() + 7 * 24 * 60 * 60

    retried = store.renew_identity_for_worker(**signed_proof(1, "renewal-retry-1234567890"))
    assert retried["status"] == "already_renewed"
    assert retried["activation"]["session_generation"] == 2

    wrong_key = Ed25519PrivateKey.generate()
    invalid = {
        "schema_version": "across-worker-identity-renewal-proof/1.0",
        "node_id": "node-renewal",
        "current_generation": 2,
        "nonce": "renewal-wrong-key-123456",
    }
    invalid_signature = base64.urlsafe_b64encode(
        wrong_key.sign(json.dumps(invalid, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    ).decode().rstrip("=")
    with pytest.raises(WorkerControlError, match="rejected"):
        store.renew_identity_for_worker(
            signature=invalid_signature,
            **{key: value for key, value in invalid.items() if key != "schema_version"},
        )

    store.action("node-renewal", "revoke")
    with pytest.raises(WorkerControlError, match="cannot be renewed"):
        store.renew_identity_for_worker(**signed_proof(3, "renewal-revoked-12345678"))


def test_listener_requires_explicit_binding_and_relay_requires_https_without_credentials(tmp_path, monkeypatch):
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    with pytest.raises(WorkerControlError, match="explicit"):
        store.configure_listener({"enabled": True, "bind_host": "0.0.0.0", "port": 9443})
    with pytest.raises(WorkerControlError, match="port"):
        store.configure_listener({"enabled": True, "bind_host": "192.0.2.10", "port": 65535})
    listener = store.configure_listener({"enabled": True, "bind_host": "192.0.2.10", "port": 9443})
    assert listener["tls_minimum"] == "1.3"
    assert listener["mutual_authentication"] is True
    with pytest.raises(WorkerControlError, match="credential-free"):
        store.configure_relay({"enabled": True, "endpoint": "https://user:password@example.com"})
    relay = store.configure_relay({"enabled": True, "endpoint": "https://relay.example.com"})
    assert relay["stores_job_content"] is False
    catalog = tmp_path / "worker-release.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "across-worker-release-catalog/1.0",
                "published": True,
                "version": "0.10.3",
                "bootstrap": {"url": "https://github.com/fantasyce/across-orchestrator/releases/download/v0.10.3/install-worker.py", "sha256": "a" * 64},
                "assets": {
                    "linux-arm64": {"url": "https://github.com/fantasyce/across-orchestrator/releases/download/v0.10.3/across-worker-linux-arm64.tar.gz", "sha256": "b" * 64}
                },
            }
        )
    )
    monkeypatch.setenv("ACROSS_WORKER_RELEASE_CATALOG", str(catalog))
    pairing = store.create_pairing()
    install = store.install_command(pairing, platform_name="linux-arm64")
    assert install["argv"][0:2] == ["/bin/sh", "-c"]
    assert "https://192.0.2.10:9443" in install["shell_command"]
    assert "https://192.0.2.10:9445" in install["shell_command"]
    assert "b" * 64 in install["shell_command"]
    assert install["source_verified"] is True
    assert install["contains_long_term_secret"] is False


def test_relay_approval_issues_bound_e2e_session_without_exposing_it_in_public_state(tmp_path):
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    store.configure_relay({"enabled": True, "endpoint": "https://relay.example.com:443"})
    pairing = store.create_pairing()
    pending = submit(store, pairing)
    approved = store.approve("node-test", pending["verification_code"])
    activation = approved["activation"]
    assert activation["transport"] == "relay"
    assert activation["endpoint"] == "https://relay.example.com:443"
    assert activation["relay_session_id"].startswith("relay-")
    assert activation["relay_peer_node_id"].startswith("node-host-")
    assert len(activation["relay_session_key"]) >= 43
    public = json.dumps(store.snapshot(), sort_keys=True)
    assert activation["relay_session_key"] not in public
    assert activation["relay_session_id"] not in public


def test_direct_approval_carries_relay_fallback_and_combined_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "aaa-home"))
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    store.configure_listener({"enabled": True, "bind_host": "127.0.0.1", "port": 39473})
    store.configure_relay({"enabled": True, "endpoint": "https://relay.example.com:9444"})
    pairing = store.create_pairing()
    pending = submit(store, pairing)
    approved = store.approve("node-test", pending["verification_code"])
    assert approved["activation"]["transport"] == "direct"
    assert approved["activation"]["relay_endpoint"] == "https://relay.example.com:9444"
    directives = store.relay_transport_directives()
    assert directives[0]["node_id"] == "node-test"
    assert directives[0]["relay_session_key"] == approved["activation"]["relay_session_key"]
    assert approved["activation"]["relay_session_key"] not in json.dumps(store.snapshot())

    spawned = []

    class FakeProcess:
        def __init__(self):
            self.pid = 44000 + len(spawned)
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    def fake_popen(argv, **kwargs):
        process = FakeProcess()
        spawned.append((argv, kwargs, process))
        return process

    manager = WorkerNetworkRuntimeManager(
        store,
        orchestrator_command=["/usr/bin/true"],
        gateway_command=["/usr/bin/true", "worker-model-gateway"],
        enrollment_command=["/usr/bin/true", "worker-enrollment-gateway"],
        popen=fake_popen,
    )
    status = manager.reconcile()
    assert status["status"] == "running"
    assert status["listener_running"] is True
    assert status["relay_running_count"] == 1
    assert len(spawned) == 5
    assert spawned[0][0][1] == "worker-control-server"
    manager.shutdown()


def test_worker_network_runtime_owns_listener_and_secretless_gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "aaa-home"))
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    store.configure_listener({"enabled": True, "bind_host": "127.0.0.1", "port": 39443})
    spawned = []

    class FakeProcess:
        def __init__(self, pid):
            self.pid = pid
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    def fake_popen(argv, **kwargs):
        spawned.append((argv, kwargs))
        return FakeProcess(42000 + len(spawned))

    manager = WorkerNetworkRuntimeManager(
        store,
        orchestrator_command=["/usr/bin/true"],
        gateway_command=["/usr/bin/true", "worker-model-gateway"],
        enrollment_command=["/usr/bin/true", "worker-enrollment-gateway"],
        popen=fake_popen,
    )
    status = manager.reconcile()
    assert status["status"] == "running"
    assert status["host_credentials_copied"] is False
    control_argv = spawned[0][0]
    gateway_argv = spawned[1][0]
    enrollment_argv = spawned[2][0]
    listener_argv = spawned[3][0]
    assert control_argv[0:2] == ["/usr/bin/true", "worker-control-server"]
    assert gateway_argv[0:2] == ["/usr/bin/true", "worker-model-gateway"]
    assert gateway_argv[gateway_argv.index("--port") + 1] == "39444"
    assert enrollment_argv[0:2] == ["/usr/bin/true", "worker-enrollment-gateway"]
    assert enrollment_argv[enrollment_argv.index("--port") + 1] == "39445"
    assert listener_argv[1] == "worker-listener"
    assert listener_argv[listener_argv.index("--host") + 1] == "127.0.0.1"
    assert listener_argv[listener_argv.index("--model-gateway-url") + 1] == "https://127.0.0.1:39444/invoke"
    lease = json.loads(manager._lease_path.read_text())
    assert lease["host_socket"].endswith("across-agents.sock")
    assert lease["policy"] == {"raw_credentials_allowed": False, "secrets_included": False}
    assert "api_key" not in json.dumps(lease).lower()
    assert manager.reconcile()["listener_pid"] == 42004
    assert manager.reconcile()["control_server_pid"] == 42001
    assert len(spawned) == 4
    manager.shutdown()
    assert not manager._lease_path.exists()


def test_worker_network_runtime_starts_private_relay_session_without_key_in_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "aaa-home"))
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    store.configure_relay({"enabled": True, "endpoint": "https://relay.example.com"})
    pairing = store.create_pairing()
    pending = submit(store, pairing)
    approved = store.approve("node-test", pending["verification_code"])
    spawned = []

    class FakeProcess:
        def __init__(self):
            self.pid = 43000 + len(spawned)
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    def fake_popen(argv, **kwargs):
        process = FakeProcess()
        spawned.append((argv, kwargs, process))
        return process

    manager = WorkerNetworkRuntimeManager(store, orchestrator_command=["/usr/bin/true"], popen=fake_popen)
    status = manager.reconcile()
    assert status["status"] == "running"
    assert status["relay_running_count"] == 1
    assert spawned[0][0][1] == "worker-control-server"
    argv = spawned[1][0]
    assert argv[1] == "worker-relay-session"
    assert approved["activation"]["relay_session_key"] not in argv
    key_path = Path(argv[argv.index("--session-key-file") + 1])
    assert key_path.stat().st_mode & 0o777 == 0o600
    assert key_path.read_text().strip() == approved["activation"]["relay_session_key"]
    manager.shutdown()
    assert not key_path.exists()


def test_worker_network_runtime_reports_missing_managed_orchestrator(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "aaa-home"))
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    store.configure_listener({"enabled": True, "bind_host": "127.0.0.1", "port": 39453})
    manager = WorkerNetworkRuntimeManager(store, orchestrator_command=[str(tmp_path / "missing")])
    status = manager.reconcile()
    assert status["status"] == "degraded"
    assert status["last_error"] == "managed_orchestrator_missing"
    assert status["listener_running"] is False


def test_worker_network_runtime_nowait_status_does_not_block_during_reconcile(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "aaa-home"))
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    store.configure_listener({"enabled": True, "bind_host": "127.0.0.1", "port": 39463})
    manager = WorkerNetworkRuntimeManager(store, orchestrator_command=["/usr/bin/true"])

    lock_held = Event()
    release_lock = Event()

    def hold_runtime_lock():
        with manager._lock:
            lock_held.set()
            release_lock.wait(timeout=2)

    thread = Thread(target=hold_runtime_lock)
    thread.start()
    assert lock_held.wait(timeout=0.5)
    try:
        started_at = time.perf_counter()
        status = manager.status_nowait()
    finally:
        release_lock.set()
        thread.join(timeout=1)

    assert time.perf_counter() - started_at < 0.05
    assert status["status"] == "starting"
    assert status["reconcile_in_progress"] is True


def test_public_snapshot_redacts_keys_paths_and_verification_code(tmp_path):
    store = WorkerTrustStore(tmp_path / "worker.json", tmp_path / "secrets.json")
    pairing = store.create_pairing()
    pending = submit(store, pairing)
    snapshot = store.snapshot()
    rendered = json.dumps(snapshot)
    assert pending["verification_code"] not in rendered
    assert "public_key_pem" not in rendered
    assert "pairing_code" not in rendered
    assert "/Users/" not in rendered


def test_corrupt_store_recovers_without_exposing_corrupt_contents(tmp_path):
    path = tmp_path / "worker.json"
    path.write_text('{"private_key":"secret"')
    store = WorkerTrustStore(path, tmp_path / "secrets.json")
    snapshot = store.snapshot()
    assert snapshot["health"]["status"] == "ok"
    assert snapshot["recovery"]["status"] == "recovered_from_corruption"
    assert '"private_key"' not in json.dumps(snapshot)
    assert list(tmp_path.glob("worker.corrupt-*.json"))


def test_worker_control_api_lifecycle_uses_isolated_store(tmp_path, monkeypatch):
    from across_agents_assistant import api_server

    synchronized = []
    presence_wait_budgets = []

    class FakeRuntime:
        def __init__(self):
            self.reconcile_calls = 0

        def status(self):
            return {"status": "stopped"}

        def reconcile(self):
            self.reconcile_calls += 1
            return {"status": "running"}

    class FakeOrchestrator:
        def call(self, action, payload=None):
            synchronized.append((action, payload))
            if action == "node.import_approved":
                return {"state": "offline"}
            if action == "snapshot":
                return {
                    "nodes": [
                            {
                                "node_id": "node-test",
                                "state": "online_idle",
                                "transport": "direct",
                                "transport_quality": {"rtt_ms": 3},
                                "current_job": {"job_id": "job-live", "title": "Remote simulation", "state": "running"},
                                "recent_result": {"job_id": "job-prev", "state": "completed", "finished_at": 1230.0},
                                "last_seen_at": 1234.5,
                                "capability_manifest": {
                                    **capability(),
                                "worker_version": "0.10.5",
                            },
                        }
                    ]
                }
            return {"status": "ok"}

    monkeypatch.setattr(api_server, "WorkerOrchestratorClient", FakeOrchestrator)
    runtime = FakeRuntime()
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: runtime)

    def coordinator_snapshot(*, wait_for_refresh_seconds=0.0):
        presence_wait_budgets.append(wait_for_refresh_seconds)
        return FakeOrchestrator().call("snapshot")

    monkeypatch.setattr(
        api_server,
        "get_worker_presence_cache",
        lambda: SimpleNamespace(snapshot=coordinator_snapshot),
    )
    monkeypatch.setenv("ACROSS_AGENTS_WORKER_CONTROL_FILE", str(tmp_path / "api-worker.json"))
    monkeypatch.setenv("ACROSS_AGENTS_WORKER_SECRET_FILE", str(tmp_path / "api-secrets.json"))
    reset_worker_trust_store_for_tests()
    from across_agents_assistant.api_server import app

    client = TestClient(app)
    empty = client.get("/api/worker-control")
    assert empty.status_code == 200
    assert empty.json()["health"]["node_count"] == 0
    listener = client.post("/api/worker-control/listener", json={"enabled": True, "bind_host": "127.0.0.1", "port": 9443})
    assert listener.status_code == 200
    pairing = client.post("/api/worker-control/pairings", json={"platform": "macos-x86_64"})
    assert pairing.status_code == 200
    payload = pairing.json()
    submitted = client.post(
        "/api/worker-control/pairings/submit",
        json={
            "enrollment_id": payload["enrollment_id"],
            "pairing_code": payload["pairing_code"],
            "public_identity": identity(),
            "capability_summary": capability(),
        },
    )
    assert submitted.status_code == 200
    assert submitted.json()["verification_code"] not in json.dumps(client.get("/api/worker-control").json())
    host_code = client.get("/api/worker-control/nodes/node-test/verification-code")
    assert host_code.status_code == 200
    assert host_code.json()["verification_code"] == submitted.json()["verification_code"]
    approved = client.post(
        "/api/worker-control/nodes/node-test/approve",
        json={"verification_code": host_code.json()["verification_code"]},
    )
    assert approved.status_code == 200
    assert approved.json()["coordinator_registered"] is True
    live = client.get("/api/worker-control").json()
    assert live["nodes"][0]["state"] == "online_idle"
    assert live["nodes"][0]["last_seen_at"] == 1234.5
    assert live["nodes"][0]["current_job"]["job_id"] == "job-live"
    assert live["nodes"][0]["recent_result"]["state"] == "completed"
    assert live["nodes"][0]["transport_quality"]["rtt_ms"] == 3
    assert live["nodes"][0]["capability_manifest"]["worker_version"] == "0.10.5"
    assert live["health"]["online_count"] == 1
    assert presence_wait_budgets[-1] == 1.0
    drained = client.post("/api/worker-control/nodes/node-test/actions", json={"action": "drain"})
    assert drained.json()["node"]["state"] == "draining"
    assert [item[0] for item in synchronized if item[0] != "snapshot"] == ["node.import_approved", "node.drain"]
    health = client.get("/api/health").json()
    assert health["worker_control"]["node_count"] == 1
    assert health["worker_control"]["online_count"] == 1


def test_enrollment_gateway_requires_device_signature_and_returns_approved_activation(tmp_path, monkeypatch):
    import across_agents_assistant.worker_enrollment_gateway as enrollment_gateway
    from across_agents_assistant.worker_enrollment_gateway import app as enrollment_app
    from across_agents_assistant.worker_control import get_worker_trust_store
    import base64

    monkeypatch.setenv("ACROSS_AGENTS_WORKER_CONTROL_FILE", str(tmp_path / "gateway-worker.json"))
    monkeypatch.setenv("ACROSS_AGENTS_WORKER_SECRET_FILE", str(tmp_path / "gateway-secrets.json"))
    reset_worker_trust_store_for_tests()
    store = get_worker_trust_store()
    store.configure_listener({"enabled": True, "bind_host": "127.0.0.1", "port": 39473})
    pairing = store.create_pairing()
    private_key = Ed25519PrivateKey.generate()
    public_key_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    import hashlib

    request = {
        "schema_version": "across-worker-join-request/1.0",
        "enrollment_id": pairing["enrollment_id"],
        "pairing_code": pairing["pairing_code"],
        "public_identity": {
            "node_id": "node-gateway",
            "display_name": "Gateway Worker",
            "algorithm": "ed25519",
            "fingerprint": hashlib.sha256(json.dumps({"public_key": public_key_pem}, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "public_key_pem": public_key_pem,
        },
        "capability_summary": capability("node-gateway"),
        "contains_private_key": False,
        "contains_provider_key": False,
    }
    canonical = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    signature = base64.urlsafe_b64encode(private_key.sign(canonical)).decode().rstrip("=")
    client = TestClient(enrollment_app)
    invalid = client.post("/v1/pairings", json={"request": request, "signature": "A" * 64})
    assert invalid.status_code == 403
    submitted = client.post("/v1/pairings", json={"request": request, "signature": signature})
    assert submitted.status_code == 200
    store.approve("node-gateway", submitted.json()["verification_code"])
    proof = {
        "schema_version": "across-worker-activation-proof/1.0",
        "node_id": "node-gateway",
        "enrollment_id": pairing["enrollment_id"],
        "nonce": "gateway-nonce-1234567890",
    }
    proof_signature = base64.urlsafe_b64encode(
        private_key.sign(json.dumps(proof, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    ).decode().rstrip("=")
    activated = client.post("/v1/activations", json={**{key: value for key, value in proof.items() if key != "schema_version"}, "signature": proof_signature})
    assert activated.status_code == 200
    assert activated.json()["status"] == "approved"
    assert activated.json()["activation"]["certificate_pem"].startswith("-----BEGIN CERTIFICATE-----")

    synchronized = []

    class FakeOrchestratorClient:
        def call(self, action, payload=None):
            synchronized.append((action, payload))
            return {"state": "offline"}

    monkeypatch.setattr(enrollment_gateway, "WorkerOrchestratorClient", FakeOrchestratorClient)
    renewal_proof = {
        "schema_version": "across-worker-identity-renewal-proof/1.0",
        "node_id": "node-gateway",
        "current_generation": 1,
        "nonce": "gateway-renewal-1234567890",
    }
    renewal_signature = base64.urlsafe_b64encode(
        private_key.sign(json.dumps(renewal_proof, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    ).decode().rstrip("=")
    renewed = client.post(
        "/v1/identity/renew",
        json={**{key: value for key, value in renewal_proof.items() if key != "schema_version"}, "signature": renewal_signature},
    )
    assert renewed.status_code == 200
    assert renewed.json()["status"] == "renewed"
    assert renewed.json()["activation"]["session_generation"] == 2
    assert synchronized[0][0] == "node.import_approved"
    assert synchronized[0][1]["session_generation"] == 2


def test_worker_presence_cache_refreshes_slow_coordinator_without_blocking_reads():
    started = Event()
    release = Event()

    class SlowOrchestrator:
        def call(self, action, payload=None):
            assert action == "snapshot"
            started.set()
            assert release.wait(1)
            return {
                "nodes": [
                    {
                        "node_id": "node-slow",
                        "state": "online_idle",
                        "transport": "direct",
                    }
                ]
            }

    cache = WorkerCoordinatorPresenceCache(lambda: SlowOrchestrator(), refresh_interval_seconds=60)
    before = time.monotonic()
    assert cache.snapshot() is None
    assert time.monotonic() - before < 0.1
    assert started.wait(1)
    release.set()
    deadline = time.monotonic() + 1
    value = None
    while value is None and time.monotonic() < deadline:
        value = cache.snapshot()
        time.sleep(0.01)
    assert value is not None
    assert value["nodes"][0]["state"] == "online_idle"


def test_worker_presence_cache_can_wait_briefly_for_a_fresh_snapshot():
    class FastOrchestrator:
        def call(self, action, payload=None):
            assert action == "snapshot"
            return {
                "nodes": [
                    {
                        "node_id": "node-fresh",
                        "state": "online_idle",
                        "transport": "direct",
                    }
                ]
            }

    cache = WorkerCoordinatorPresenceCache(lambda: FastOrchestrator())

    value = cache.snapshot(wait_for_refresh_seconds=0.25)

    assert value is not None
    assert value["nodes"][0]["node_id"] == "node-fresh"


def test_worker_presence_cache_default_client_uses_ui_safe_timeout(monkeypatch):
    from across_agents_assistant import worker_control

    observed = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            observed.append({
                "timeout_seconds": kwargs.get("timeout_seconds"),
                "allow_cli_fallback": kwargs.get("allow_cli_fallback"),
            })

        def call(self, action, payload=None):
            assert action == "snapshot"
            return {"nodes": []}

    monkeypatch.setattr(worker_control, "WorkerOrchestratorClient", FakeClient)
    cache = worker_control.WorkerCoordinatorPresenceCache(refresh_interval_seconds=60)

    cache.snapshot(wait_for_refresh_seconds=0.25)

    assert observed == [{
        "timeout_seconds": worker_control.WORKER_PRESENCE_REFRESH_TIMEOUT_SECONDS,
        "allow_cli_fallback": False,
    }]


def test_presence_socket_only_client_does_not_spawn_a_cold_cli_fallback(tmp_path, monkeypatch):
    from across_agents_assistant import worker_control

    invoked = []
    monkeypatch.setattr(worker_control.subprocess, "run", lambda *args, **kwargs: invoked.append((args, kwargs)))
    client = worker_control.WorkerOrchestratorClient(
        command=["across-orchestrator"],
        socket_path=tmp_path / "not-ready.sock",
        allow_cli_fallback=False,
    )

    with pytest.raises(WorkerControlError) as exc:
        client.call("snapshot")

    assert exc.value.code == "orchestrator_unavailable"
    assert invoked == []


def test_worker_model_gateway_reserves_budget_and_never_returns_provider_credentials(monkeypatch):
    from across_agents_assistant import api_server

    calls = []

    class FakeOrchestrator:
        def call(self, action, payload=None):
            calls.append((action, payload))
            if action == "model_grant.begin":
                return {"call_id": "model-call-test"}
            if action == "model_grant.finish":
                return {"calls": 1, "tokens": 5, "cost_usd": 0.0, "active_calls": 0}
            raise AssertionError(action)

    async def fake_chat(**kwargs):
        assert kwargs["scope"] == "worker.model.invoke"
        assert kwargs["max_tokens"] == 20
        assert kwargs["extra_body"] == {"reasoning_split": True, "thinking": {"type": "disabled"}}
        return SimpleNamespace(
            text="bounded annotation",
            model="host-model",
            provider="host-provider",
            finish_reason="stop",
            usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        )

    monkeypatch.setattr(api_server, "WorkerOrchestratorClient", FakeOrchestrator)
    monkeypatch.setattr(api_server, "_chat_with_model_capability", fake_chat)
    monkeypatch.setattr(api_server, "get_gateway", lambda: SimpleNamespace(get_current_provider_id=lambda: "minimax"))
    response = TestClient(api_server.app).post(
        "/api/worker-control/model-gateway/invoke",
        json={
            "grant_id": "grant-test",
            "run_id": "run-test",
            "job_id": "job-test",
            "node_id": "node-test",
            "purpose": "scenario_round_annotation",
            "message": "round summary",
            "max_tokens": 20,
            "token_budget": 32,
            "timeout_seconds": 45,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider_key_exposed"] is False
    assert "api_key" not in json.dumps(body).lower()
    assert [item[0] for item in calls] == ["model_grant.begin", "model_grant.finish"]
    assert calls[0][1]["job_id"] == "job-test"
    assert calls[0][1]["requested_tokens"] == 32
    assert calls[1][1]["outcome"] == "completed"


def test_worker_model_gateway_adapts_when_primary_returns_no_final_text(monkeypatch):
    from across_agents_assistant import api_server

    calls = []

    class FakeOrchestrator:
        def call(self, action, payload=None):
            calls.append((action, payload))
            if action == "model_grant.begin":
                return {"call_id": "model-call-fallback"}
            if action == "model_grant.finish":
                return {"calls": 1, "tokens": payload["tokens"], "cost_usd": 0.0, "active_calls": 0}
            raise AssertionError(action)

    provider_calls = []
    provider_timeouts = []

    async def fake_chat(**kwargs):
        provider_id = kwargs["provider_id"]
        provider_calls.append(provider_id)
        provider_timeouts.append(kwargs["timeout"])
        if provider_id == "minimax":
            return SimpleNamespace(
                text="",
                model="MiniMax-M3",
                provider="minimax",
                finish_reason="length",
                usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                raw={},
            )
        return SimpleNamespace(
            text="bounded final annotation",
            model="agnes-2.0-flash",
            provider="agnes",
            finish_reason="stop",
            usage={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
            raw={},
        )

    api_server._worker_model_provider_preference.clear()
    monkeypatch.setattr(api_server, "WorkerOrchestratorClient", FakeOrchestrator)
    monkeypatch.setattr(api_server, "_chat_with_model_capability", fake_chat)
    monkeypatch.setattr(api_server, "_worker_model_provider_candidates", lambda _purpose: ["minimax", "agnes"])
    response = TestClient(api_server.app).post(
        "/api/worker-control/model-gateway/invoke",
        json={
            "grant_id": "grant-fallback",
            "run_id": "run-fallback",
            "job_id": "job-fallback",
            "node_id": "node-fallback",
            "purpose": "scenario_round_annotation",
            "message": "return compact json",
            "max_tokens": 20,
            "token_budget": 32,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert provider_calls == ["minimax", "minimax", "agnes"]
    assert body["text"] == "bounded final annotation"
    assert body["provider"] == "agnes"
    assert body["usage"]["provider_attempts"] == 3
    assert body["usage"]["providers_attempted"] == ["minimax", "minimax", "agnes"]
    assert calls[-1][1]["tokens"] == 13
    assert all(0 < value <= api_server._WORKER_MODEL_PROVIDER_ATTEMPT_TIMEOUT_SECONDS for value in provider_timeouts)
    assert provider_timeouts[0] < 20
    assert sum(provider_timeouts[:2]) < 55
    assert provider_timeouts[2] > 0


def test_worker_model_gateway_fairly_reserves_deadline_for_later_routes():
    from across_agents_assistant import api_server

    first = api_server._worker_model_attempt_timeout(
        remaining_seconds=55,
        providers_remaining=2,
        empty_retry_available=True,
    )
    after_empty = api_server._worker_model_attempt_timeout(
        remaining_seconds=55 - first,
        providers_remaining=2,
        empty_retry_available=False,
    )
    fallback = api_server._worker_model_attempt_timeout(
        remaining_seconds=55 - first - after_empty,
        providers_remaining=1,
        empty_retry_available=True,
    )
    assert first == pytest.approx(55 / 3)
    assert after_empty == pytest.approx((55 - first) / 2)
    assert fallback > 0
    assert first + after_empty + fallback < 55


def test_worker_model_gateway_retries_empty_provider_once(monkeypatch):
    from across_agents_assistant import api_server

    calls = []

    class FakeOrchestrator:
        def call(self, action, payload=None):
            calls.append((action, payload))
            if action == "model_grant.begin":
                return {"call_id": "model-call-retry"}
            if action == "model_grant.finish":
                return {"calls": 1, "tokens": payload["tokens"], "cost_usd": 0.0, "active_calls": 0}
            raise AssertionError(action)

    provider_calls = []

    async def flaky_empty_provider(**kwargs):
        provider_calls.append(kwargs["provider_id"])
        if len(provider_calls) == 1:
            return SimpleNamespace(
                text="",
                model="MiniMax-M3",
                provider="minimax",
                finish_reason="length",
                usage={"input_tokens": 1, "output_tokens": 0, "total_tokens": 1},
                raw={},
            )
        return SimpleNamespace(
            text="bounded final annotation",
            model="MiniMax-M3",
            provider="minimax",
            finish_reason="stop",
            usage={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
            raw={},
        )

    api_server._worker_model_provider_preference.clear()
    monkeypatch.setattr(api_server, "WorkerOrchestratorClient", FakeOrchestrator)
    monkeypatch.setattr(api_server, "_chat_with_model_capability", flaky_empty_provider)
    monkeypatch.setattr(api_server, "_worker_model_provider_candidates", lambda _purpose: ["minimax", "agnes"])
    response = TestClient(api_server.app).post(
        "/api/worker-control/model-gateway/invoke",
        json={
            "grant_id": "grant-retry",
            "run_id": "run-retry",
            "job_id": "job-retry",
            "node_id": "node-retry",
            "purpose": "scenario_round_annotation",
            "message": "return compact json",
            "max_tokens": 20,
            "token_budget": 32,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert provider_calls == ["minimax", "minimax"]
    assert body["text"] == "bounded final annotation"
    assert body["provider"] == "minimax"
    assert body["usage"]["provider_attempts"] == 2
    assert body["usage"]["providers_attempted"] == ["minimax", "minimax"]
    assert calls[-1][1]["outcome"] == "completed"


def test_worker_model_gateway_reports_empty_response_category(monkeypatch):
    from across_agents_assistant import api_server

    calls = []

    class FakeOrchestrator:
        def call(self, action, payload=None):
            calls.append((action, payload))
            if action == "model_grant.begin":
                return {"call_id": "model-call-empty"}
            if action == "model_grant.finish":
                return {"active_calls": 0}
            raise AssertionError(action)

    async def empty_provider(**_kwargs):
        return SimpleNamespace(
            text="",
            model="MiniMax-M3",
            provider="minimax",
            finish_reason="length",
            usage={"input_tokens": 10, "output_tokens": 0, "total_tokens": 10},
            raw={},
        )

    api_server._worker_model_provider_preference.clear()
    monkeypatch.setattr(api_server, "WorkerOrchestratorClient", FakeOrchestrator)
    monkeypatch.setattr(api_server, "_chat_with_model_capability", empty_provider)
    monkeypatch.setattr(api_server, "_worker_model_provider_candidates", lambda _purpose: ["minimax"])
    response = TestClient(api_server.app).post(
        "/api/worker-control/model-gateway/invoke",
        json={
            "grant_id": "grant-empty",
            "run_id": "run-empty",
            "job_id": "job-empty",
            "node_id": "node-empty",
            "purpose": "scenario_round_annotation",
            "message": "return compact json",
            "max_tokens": 20,
            "token_budget": 32,
        },
    )

    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["category"] == "empty_response"
    assert body["detail"]["provider_failures"] == [
        {
            "provider": "minimax",
            "category": "empty_response",
            "error_type": "EmptyModelResponse",
        },
        {
            "provider": "minimax",
            "category": "empty_response",
            "error_type": "EmptyModelResponse",
        },
    ]
    assert calls[-1][1]["outcome"] == "provider_failure"


def test_worker_model_gateway_shares_one_total_deadline_across_provider_fallbacks(monkeypatch):
    from across_agents_assistant import api_server

    calls = []

    class FakeOrchestrator:
        def call(self, action, payload=None):
            calls.append((action, payload))
            if action == "model_grant.begin":
                return {"call_id": "model-call-deadline"}
            if action == "model_grant.finish":
                return {"active_calls": 0}
            raise AssertionError(action)

    async def slow_provider(**_kwargs):
        await asyncio.sleep(0.5)
        return SimpleNamespace(
            text="too late",
            model="slow",
            provider="slow",
            finish_reason="stop",
            usage={"total_tokens": 1},
            raw={},
        )

    monkeypatch.setattr(api_server, "WorkerOrchestratorClient", FakeOrchestrator)
    monkeypatch.setattr(api_server, "_chat_with_model_capability", slow_provider)
    monkeypatch.setattr(api_server, "_worker_model_provider_candidates", lambda _purpose: ["slow-a", "slow-b"])
    monkeypatch.setattr(api_server, "_WORKER_MODEL_FINALIZATION_RESERVE_SECONDS", 4.75)
    response = TestClient(api_server.app).post(
        "/api/worker-control/model-gateway/invoke",
        json={
            "grant_id": "grant-deadline",
            "run_id": "run-deadline",
            "job_id": "job-deadline",
            "node_id": "node-deadline",
            "purpose": "scenario_round_annotation",
            "message": "bounded request",
            "timeout_seconds": 5,
        },
    )
    assert response.status_code == 502
    assert [item[0] for item in calls] == ["model_grant.begin", "model_grant.finish"]
    assert calls[-1][1]["outcome"] == "provider_failure"


@pytest.mark.asyncio
async def test_worker_model_gateway_finalizes_grant_when_request_is_cancelled(monkeypatch):
    from across_agents_assistant import api_server

    calls = []

    class FakeOrchestrator:
        def call(self, action, payload=None):
            calls.append((action, payload))
            if action == "model_grant.begin":
                return {"call_id": "model-call-cancelled"}
            if action == "model_grant.finish":
                return {"active_calls": 0}
            raise AssertionError(action)

    async def cancelled_chat(**_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(api_server, "WorkerOrchestratorClient", FakeOrchestrator)
    monkeypatch.setattr(api_server, "_chat_with_model_capability", cancelled_chat)
    request = api_server.WorkerModelInvokeRequest(
        grant_id="grant-cancelled",
        run_id="run-cancelled",
        job_id="job-cancelled",
        node_id="node-cancelled",
        message="cancel this request",
    )

    with pytest.raises(asyncio.CancelledError):
        await api_server.invoke_worker_model_gateway_core(request)

    assert [item[0] for item in calls] == ["model_grant.begin", "model_grant.finish"]
    assert calls[-1][1]["outcome"] == "provider_failure"


def test_worker_model_gateway_does_not_finalize_twice_after_usage_rejection(monkeypatch):
    from across_agents_assistant import api_server

    calls = []

    class RejectingOrchestrator:
        def call(self, action, payload=None):
            calls.append((action, payload))
            if action == "model_grant.begin":
                return {"call_id": "model-call-over-budget"}
            if action == "model_grant.finish":
                raise WorkerControlError("budget exceeded", code="orchestrator_operation_failed", status_code=502)
            raise AssertionError(action)

    async def successful_chat(**_kwargs):
        return SimpleNamespace(
            text="too much usage",
            model="host-model",
            provider="host-provider",
            finish_reason="stop",
            usage={"total_tokens": 999},
            raw={},
        )

    monkeypatch.setattr(api_server, "WorkerOrchestratorClient", RejectingOrchestrator)
    monkeypatch.setattr(api_server, "_chat_with_model_capability", successful_chat)
    response = TestClient(api_server.app).post(
        "/api/worker-control/model-gateway/invoke",
        json={
            "grant_id": "grant-over-budget",
            "run_id": "run-over-budget",
            "job_id": "job-over-budget",
            "node_id": "node-over-budget",
            "message": "bounded request",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"]["category"] == "policy"
    assert [item[0] for item in calls] == ["model_grant.begin", "model_grant.finish"]
