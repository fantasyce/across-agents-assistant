from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping
import base64
import fcntl
import hmac
import json
import os
import re
import secrets
import subprocess
import shlex
import socket
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .paths import backend_socket_path, data_file, ecosystem_bin_dir, log_dir, run_dir
from .worker_pki import WorkerCertificateAuthority


WORKER_CONTROL_SCHEMA = "across-aaa-worker-control/1.0"
WORKER_CONTROL_COMMAND_TIMEOUT_SECONDS = 45.0
WORKER_CONTROL_STARTUP_TIMEOUT_SECONDS = 60.0
NODE_STATES = {
    "pending_approval",
    "online_idle",
    "online_busy",
    "draining",
    "offline",
    "incompatible",
    "degraded",
    "revoked",
}
TRANSPORTS = {"local", "direct", "overlay", "relay"}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SECRET_KEYS = re.compile(r"(?:api[_-]?key|authorization|credential|password|private[_-]?key|session[_-]?key|secret|token)$", re.I)
_USER_PATH = re.compile(r"/(?:Users|home)/[^/\s]+")


class WorkerControlError(RuntimeError):
    def __init__(self, message: str, *, code: str = "worker_control_failed", status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _default_store_path() -> Path:
    override = os.environ.get("ACROSS_AGENTS_WORKER_CONTROL_FILE")
    return Path(override).expanduser().resolve() if override else data_file("worker-control.json")


def _default_secret_path() -> Path:
    override = os.environ.get("ACROSS_AGENTS_WORKER_SECRET_FILE")
    return Path(override).expanduser().resolve() if override else data_file("worker-control-secrets.json")


@dataclass(frozen=True)
class ListenerConfiguration:
    enabled: bool = False
    bind_host: str | None = None
    port: int = 0
    certificate_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not self.enabled:
            return
        host = str(self.bind_host or "").strip()
        if not host or host in {"0.0.0.0", "::", "*"}:
            raise WorkerControlError("Network listener requires an explicit interface address.", code="listener_explicit_bind_required")
        if self.port < 1 or self.port > 65533:
            raise WorkerControlError("Network listener port is invalid.", code="listener_port_invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "bind_host": self.bind_host,
            "port": self.port,
            "model_gateway_port": self.port + 1 if self.enabled else 0,
            "enrollment_port": self.port + 2 if self.enabled else 0,
            "certificate_fingerprint": self.certificate_fingerprint,
            "tls_minimum": "1.3" if self.enabled else None,
            "mutual_authentication": bool(self.enabled),
        }


class WorkerTrustStore:
    """AAA-owned node approvals. Secret pairing material lives in a separate 0600 file."""

    def __init__(self, path: str | Path | None = None, secret_path: str | Path | None = None, *, clock=time.time):
        self.path = Path(path).expanduser().resolve() if path else _default_store_path()
        self.secret_path = Path(secret_path).expanduser().resolve() if secret_path else _default_secret_path()
        self.lock_path = self.path.with_suffix(".lock")
        self.clock = clock

    def snapshot(self) -> dict[str, Any]:
        with self._lock():
            state = self._read()
            self._expire_enrollments(state)
            self._write(state)
        return self._public_state(state)

    def create_pairing(self, *, ttl_seconds: int = 600, display_name: str | None = None) -> dict[str, Any]:
        ttl = max(60, min(int(ttl_seconds), 600))
        enrollment_id = f"enrollment-{uuid.uuid4().hex}"
        code = "-".join(f"{secrets.randbelow(10000):04d}" for _ in range(3))
        now = self.clock()
        with self._lock():
            state = self._read()
            secret_state = self._read_secrets()
            state["enrollments"][enrollment_id] = {
                "enrollment_id": enrollment_id,
                "status": "issued",
                "display_name": str(display_name or "").strip()[:120] or None,
                "created_at": now,
                "expires_at": now + ttl,
                "failed_attempts": 0,
                "max_failed_attempts": 5,
                "used_at": None,
                "node_id": None,
            }
            secret_state["pairing_hashes"][enrollment_id] = self._hash_pairing(enrollment_id, code, secret_state)
            self._audit(state, "pairing.created", {"enrollment_id": enrollment_id, "expires_at": now + ttl})
            self._write(state)
            self._write_secrets(secret_state)
        return {
            "schema_version": "across-worker-pairing/1.0",
            "enrollment_id": enrollment_id,
            "pairing_code": code,
            "expires_at": now + ttl,
            "one_time": True,
            "contains_long_term_secret": False,
        }

    def submit_pairing(self, request: Mapping[str, Any]) -> dict[str, Any]:
        enrollment_id = _require_id(request.get("enrollment_id"), "enrollment_id")
        code = str(request.get("pairing_code") or "")
        public_identity = request.get("public_identity")
        capability = request.get("capability_summary")
        if not isinstance(public_identity, Mapping) or not isinstance(capability, Mapping):
            raise WorkerControlError("Pairing identity or capability summary is missing.", code="pairing_payload_invalid")
        node_id = _require_id(public_identity.get("node_id"), "node_id")
        if node_id != capability.get("node_id"):
            raise WorkerControlError("Device identity does not match its capability summary.", code="pairing_identity_mismatch")
        self._validate_capability(capability)
        fingerprint = str(public_identity.get("fingerprint") or "")
        public_key_pem = str(public_identity.get("public_key_pem") or "")
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
        except (ValueError, TypeError, UnicodeError):
            raise WorkerControlError("Device public identity is invalid.", code="pairing_identity_invalid")
        if (
            not isinstance(public_key, Ed25519PublicKey)
            or str(public_identity.get("algorithm") or "") != "ed25519"
            or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
            or fingerprint != _hash_json({"public_key": public_key_pem})
            or "PRIVATE" in public_key_pem
        ):
            raise WorkerControlError("Device public identity is invalid.", code="pairing_identity_invalid")
        with self._lock():
            state = self._read()
            secrets_state = self._read_secrets()
            self._expire_enrollments(state)
            enrollment = state["enrollments"].get(enrollment_id)
            if not enrollment or enrollment.get("status") != "issued" or enrollment.get("used_at") is not None:
                self._audit(state, "pairing.replay_rejected", {"enrollment_id": enrollment_id})
                self._write(state)
                raise WorkerControlError("Pairing request was rejected.", code="pairing_rejected")
            if int(enrollment.get("failed_attempts") or 0) >= int(enrollment.get("max_failed_attempts") or 5):
                enrollment["status"] = "rate_limited"
                self._audit(state, "pairing.rate_limited", {"enrollment_id": enrollment_id})
                self._write(state)
                raise WorkerControlError("Pairing request is rate limited.", code="pairing_rate_limited", status_code=429)
            expected = str(secrets_state["pairing_hashes"].get(enrollment_id) or "")
            supplied = self._hash_pairing(enrollment_id, code, secrets_state)
            if not expected or not hmac.compare_digest(expected, supplied):
                enrollment["failed_attempts"] = int(enrollment.get("failed_attempts") or 0) + 1
                self._audit(state, "pairing.invalid_rejected", {"enrollment_id": enrollment_id, "failed_attempts": enrollment["failed_attempts"]})
                self._write(state)
                raise WorkerControlError("Pairing request was rejected.", code="pairing_rejected")
            verification_code = self._verification_code(enrollment_id, node_id, fingerprint, secrets_state)
            state["nodes"][node_id] = {
                "schema_version": "across-aaa-node/1.0",
                "node_id": node_id,
                "display_name": str(public_identity.get("display_name") or enrollment.get("display_name") or node_id)[:120],
                "state": "pending_approval",
                "fingerprint": fingerprint,
                "public_key_pem": public_key_pem,
                "algorithm": str(public_identity.get("algorithm") or "ed25519"),
                "enrollment_id": enrollment_id,
                "capability_manifest": dict(capability),
                "verification_code": verification_code,
                "approved_at": None,
                "revoked_at": None,
                "last_seen_at": None,
                "transport": "pending",
                "transport_quality": None,
                "current_job": None,
                "recent_result": None,
                "draining": False,
                "session_generation": 0,
            }
            enrollment.update({"status": "pending_approval", "used_at": self.clock(), "node_id": node_id})
            secrets_state["pairing_hashes"].pop(enrollment_id, None)
            self._audit(state, "pairing.submitted", {"enrollment_id": enrollment_id, "node_id": node_id})
            self._write(state)
            self._write_secrets(secrets_state)
        return {"node_id": node_id, "state": "pending_approval", "verification_code": verification_code}

    def approve(self, node_id: str, verification_code: str) -> dict[str, Any]:
        node_id = _require_id(node_id, "node_id")
        with self._lock():
            state = self._read()
            secrets_state = self._read_secrets()
            node = self._node(state, node_id)
            if node.get("state") != "pending_approval":
                raise WorkerControlError("Device is not waiting for approval.", code="node_not_pending")
            if not hmac.compare_digest(str(node.get("verification_code") or ""), str(verification_code or "")):
                self._audit(state, "node.approval_rejected", {"node_id": node_id})
                self._write(state)
                raise WorkerControlError("Device verification code does not match.", code="verification_code_mismatch")
            now = self.clock()
            issued = self._pki().issue_device(node_id=node_id, public_key_pem=str(node["public_key_pem"]))
            listener = state.get("listener") or {}
            relay = state.get("relay") or {}
            relay_session = None
            if relay.get("enabled"):
                host_node_id = str(secrets_state.get("host_node_id") or f"node-host-{secrets.token_hex(8)}")
                secrets_state["host_node_id"] = host_node_id
                relay_session = {
                    "session_id": f"relay-{uuid.uuid4().hex}",
                    "peer_node_id": host_node_id,
                    "session_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
                    "created_at": now,
                    "expires_at": now + 30 * 24 * 60 * 60,
                }
                secrets_state.setdefault("relay_sessions", {})[node_id] = relay_session
            approved_transport = (
                "direct"
                if listener.get("enabled")
                else ("relay" if relay.get("enabled") else "pending")
            )
            node.update(
                {
                    "state": "offline",
                    "transport": approved_transport,
                    "approved_at": now,
                    "identity_expires_at": issued["not_after"],
                    "session_generation": 1,
                    "certificate_serial": issued["serial_number"],
                    "certificate_fingerprint": issued["fingerprint"],
                }
            )
            self._audit(state, "node.approved", {"node_id": node_id})
            self._write(state)
            self._write_secrets(secrets_state)
        listener = state.get("listener") or {}
        relay = state.get("relay") or {}
        endpoint = (
            f"https://{listener.get('bind_host')}:{listener.get('port')}"
            if listener.get("enabled")
            else (str(relay.get("endpoint") or "") or None)
        )
        activation = {
            "schema_version": "across-worker-activation/1.0",
            "node_id": node_id,
            "session_generation": 1,
            "endpoint": endpoint,
            "transport": "direct" if listener.get("enabled") else "relay",
            "certificate_pem": issued["certificate_pem"],
            "ca_certificate_pem": issued["ca_certificate_pem"],
            "certificate_not_after": issued["not_after"],
        }
        if relay_session:
            activation.update(
                {
                    "relay_endpoint": str(relay.get("endpoint") or ""),
                    "relay_session_id": relay_session["session_id"],
                    "relay_peer_node_id": relay_session["peer_node_id"],
                    "relay_session_key": relay_session["session_key"],
                }
            )
        with self._lock():
            secrets_state = self._read_secrets()
            secrets_state.setdefault("activations", {})[node_id] = activation
            self._write_secrets(secrets_state)
        return {
            **_public_node(node),
            "activation": activation,
        }

    def activation_for_worker(
        self,
        *,
        node_id: str,
        enrollment_id: str,
        nonce: str,
        signature: str,
    ) -> dict[str, Any]:
        """Return approval state to the device that owns the submitted Ed25519 key."""
        node_id = _require_id(node_id, "node_id")
        enrollment_id = _require_id(enrollment_id, "enrollment_id")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", str(nonce or "")):
            raise WorkerControlError("Activation nonce is invalid.", code="activation_proof_invalid")
        proof = {
            "schema_version": "across-worker-activation-proof/1.0",
            "node_id": node_id,
            "enrollment_id": enrollment_id,
            "nonce": nonce,
        }
        with self._lock():
            state = self._read()
            secrets_state = self._read_secrets()
            node = self._node(state, node_id)
            if node.get("enrollment_id") != enrollment_id:
                raise WorkerControlError("Activation proof does not match the enrollment.", code="activation_proof_invalid", status_code=403)
            try:
                public_key = serialization.load_pem_public_key(str(node.get("public_key_pem") or "").encode("ascii"))
                if not isinstance(public_key, Ed25519PublicKey):
                    raise ValueError("unsupported key")
                supplied = base64.urlsafe_b64decode(str(signature or "") + "=" * (-len(str(signature or "")) % 4))
                public_key.verify(supplied, _canonical_bytes(proof))
            except (ValueError, TypeError, UnicodeError, InvalidSignature):
                self._audit(state, "activation.proof_rejected", {"node_id": node_id})
                self._write(state)
                raise WorkerControlError("Activation proof was rejected.", code="activation_proof_invalid", status_code=403)
            nonce_hash = _hash_text(nonce)
            used = secrets_state.setdefault("activation_nonces", {}).setdefault(node_id, [])
            if nonce_hash in used:
                raise WorkerControlError("Activation proof was already used.", code="activation_proof_replayed", status_code=409)
            used.append(nonce_hash)
            del used[:-32]
            if node.get("state") == "pending_approval":
                result = {"status": "pending_approval", "node_id": node_id}
            elif node.get("state") == "revoked":
                result = {"status": "revoked", "node_id": node_id}
            else:
                activation = secrets_state.setdefault("activations", {}).get(node_id)
                if not isinstance(activation, dict):
                    raise WorkerControlError("Activation material is unavailable.", code="activation_unavailable", status_code=409)
                result = {"status": "approved", "node_id": node_id, "activation": dict(activation)}
            self._audit(state, "activation.polled", {"node_id": node_id, "status": result["status"]})
            self._write(state)
            self._write_secrets(secrets_state)
            return result

    def renew_identity_for_worker(
        self,
        *,
        node_id: str,
        current_generation: int,
        nonce: str,
        signature: str,
    ) -> dict[str, Any]:
        """Rotate an approved Worker certificate using proof from its stable device key.

        The enrollment gateway intentionally does not require a currently valid TLS
        client certificate. This lets an approved device recover after downtime that
        spans certificate expiry, while the signed proof still prevents a node-id-only
        request from gaining access.
        """
        node_id = _require_id(node_id, "node_id")
        generation = int(current_generation)
        if generation < 1:
            raise WorkerControlError("Worker identity generation is invalid.", code="identity_renewal_invalid")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", str(nonce or "")):
            raise WorkerControlError("Identity renewal nonce is invalid.", code="identity_renewal_invalid")
        proof = {
            "schema_version": "across-worker-identity-renewal-proof/1.0",
            "node_id": node_id,
            "current_generation": generation,
            "nonce": nonce,
        }
        with self._lock():
            state = self._read()
            secrets_state = self._read_secrets()
            node = self._node(state, node_id)
            if not node.get("approved_at") or node.get("state") in {"pending_approval", "revoked"}:
                raise WorkerControlError("Worker identity cannot be renewed.", code="identity_renewal_forbidden", status_code=403)
            try:
                public_key = serialization.load_pem_public_key(str(node.get("public_key_pem") or "").encode("ascii"))
                if not isinstance(public_key, Ed25519PublicKey):
                    raise ValueError("unsupported key")
                supplied = base64.urlsafe_b64decode(str(signature or "") + "=" * (-len(str(signature or "")) % 4))
                public_key.verify(supplied, _canonical_bytes(proof))
            except (ValueError, TypeError, UnicodeError, InvalidSignature):
                self._audit(state, "identity.renewal_proof_rejected", {"node_id": node_id})
                self._write(state)
                raise WorkerControlError("Identity renewal proof was rejected.", code="identity_renewal_proof_invalid", status_code=403)

            nonce_hash = _hash_text(nonce)
            used = secrets_state.setdefault("identity_renewal_nonces", {}).setdefault(node_id, [])
            if nonce_hash in used:
                raise WorkerControlError("Identity renewal proof was already used.", code="identity_renewal_replayed", status_code=409)
            used.append(nonce_hash)
            del used[:-32]

            stored_generation = int(node.get("session_generation") or 0)
            if generation == stored_generation - 1:
                activation = secrets_state.setdefault("activations", {}).get(node_id)
                if not isinstance(activation, dict) or int(activation.get("session_generation") or 0) != stored_generation:
                    raise WorkerControlError("Worker identity renewal is stale.", code="identity_renewal_stale", status_code=409)
                renewed = False
            elif generation == stored_generation:
                issued = self._pki().issue_device(node_id=node_id, public_key_pem=str(node["public_key_pem"]))
                previous_serial = str(node.get("certificate_serial") or "")
                if previous_serial:
                    revoked = state.setdefault("revoked_certificate_serials", [])
                    if previous_serial not in revoked:
                        revoked.append(previous_serial)
                        del revoked[:-5000]
                stored_generation += 1
                node.update(
                    {
                        "state": "offline",
                        "identity_expires_at": issued["not_after"],
                        "identity_renewed_at": self.clock(),
                        "session_generation": stored_generation,
                        "certificate_serial": issued["serial_number"],
                        "certificate_fingerprint": issued["fingerprint"],
                    }
                )
                activation = self._activation_material(
                    state=state,
                    secrets_state=secrets_state,
                    node_id=node_id,
                    issued=issued,
                    session_generation=stored_generation,
                )
                secrets_state.setdefault("activations", {})[node_id] = activation
                self._audit(
                    state,
                    "identity.renewed",
                    {"node_id": node_id, "session_generation": stored_generation, "identity_expires_at": issued["not_after"]},
                )
                renewed = True
            else:
                raise WorkerControlError("Worker identity renewal is stale.", code="identity_renewal_stale", status_code=409)
            self._write(state)
            self._write_secrets(secrets_state)
            return {
                "status": "renewed" if renewed else "already_renewed",
                "node": _public_node(node),
                "activation": dict(activation),
            }

    def _activation_material(
        self,
        *,
        state: Mapping[str, Any],
        secrets_state: dict[str, Any],
        node_id: str,
        issued: Mapping[str, Any],
        session_generation: int,
    ) -> dict[str, Any]:
        listener = state.get("listener") or {}
        relay = state.get("relay") or {}
        endpoint = (
            f"https://{listener.get('bind_host')}:{listener.get('port')}"
            if listener.get("enabled")
            else (str(relay.get("endpoint") or "") or None)
        )
        activation = {
            "schema_version": "across-worker-activation/1.0",
            "node_id": node_id,
            "session_generation": int(session_generation),
            "endpoint": endpoint,
            "transport": "direct" if listener.get("enabled") else "relay",
            "certificate_pem": issued["certificate_pem"],
            "ca_certificate_pem": issued["ca_certificate_pem"],
            "certificate_not_after": issued["not_after"],
        }
        if relay.get("enabled"):
            now = self.clock()
            sessions = secrets_state.setdefault("relay_sessions", {})
            relay_session = sessions.get(node_id) if isinstance(sessions.get(node_id), Mapping) else None
            if not relay_session or float(relay_session.get("expires_at") or 0) <= now + 60:
                host_node_id = str(secrets_state.get("host_node_id") or f"node-host-{secrets.token_hex(8)}")
                secrets_state["host_node_id"] = host_node_id
                relay_session = {
                    "session_id": f"relay-{uuid.uuid4().hex}",
                    "peer_node_id": host_node_id,
                    "session_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
                    "created_at": now,
                    "expires_at": now + 30 * 24 * 60 * 60,
                }
                sessions[node_id] = relay_session
            activation.update(
                {
                    "relay_endpoint": str(relay.get("endpoint") or ""),
                    "relay_session_id": relay_session["session_id"],
                    "relay_peer_node_id": relay_session["peer_node_id"],
                    "relay_session_key": relay_session["session_key"],
                }
            )
        return activation

    def update_presence(
        self,
        node_id: str,
        *,
        state_value: str,
        transport: str,
        quality: Mapping[str, Any] | None = None,
        current_job: Mapping[str, Any] | None = None,
        recent_result: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if state_value not in NODE_STATES - {"pending_approval", "revoked"}:
            raise WorkerControlError("Device state is invalid.", code="node_state_invalid")
        if transport not in TRANSPORTS:
            raise WorkerControlError("Device transport is invalid.", code="node_transport_invalid")
        with self._lock():
            state = self._read()
            node = self._node(state, node_id)
            if not node.get("approved_at") or node.get("state") == "revoked":
                raise WorkerControlError("Device is not approved.", code="node_not_approved", status_code=403)
            node.update(
                {
                    "state": "draining" if node.get("draining") else state_value,
                    "transport": transport,
                    "transport_quality": _safe_public(dict(quality or {})),
                    "current_job": _safe_public(dict(current_job or {})) or None,
                    "recent_result": _safe_public(dict(recent_result or {})) or None,
                    "last_seen_at": self.clock(),
                }
            )
            self._write(state)
        return _public_node(node)

    def action(self, node_id: str, action: str, *, reason: str | None = None) -> dict[str, Any]:
        action = str(action or "").strip()
        with self._lock():
            state = self._read()
            secrets_state = self._read_secrets()
            node = self._node(state, node_id)
            if action == "drain":
                node["draining"] = True
                node["state"] = "draining"
            elif action == "resume":
                node["draining"] = False
                node["state"] = "offline" if not node.get("last_seen_at") else "online_idle"
            elif action == "update":
                if node.get("state") in {"pending_approval", "revoked"}:
                    raise WorkerControlError("Only approved devices can be updated.", code="node_not_approved", status_code=403)
                node["draining"] = True
                node["state"] = "draining"
            elif action == "revoke":
                node["draining"] = True
                node["state"] = "revoked"
                node["revoked_at"] = self.clock()
                node["revocation_reason"] = str(reason or "host_revoked")[:120]
                node["session_generation"] = int(node.get("session_generation") or 0) + 1
                if node.get("certificate_serial"):
                    state.setdefault("revoked_certificate_serials", []).append(node["certificate_serial"])
                secrets_state.setdefault("relay_sessions", {}).pop(node_id, None)
                secrets_state.setdefault("activations", {}).pop(node_id, None)
                secrets_state.setdefault("activation_nonces", {}).pop(node_id, None)
            elif action == "remove":
                if node.get("state") != "revoked":
                    raise WorkerControlError("Revoke the device before removing it.", code="node_revoke_required")
                state["nodes"].pop(node_id, None)
            else:
                raise WorkerControlError("Device action is unsupported.", code="node_action_unsupported")
            self._audit(state, f"node.{action}", {"node_id": node_id, "reason": reason})
            self._write(state)
            self._write_secrets(secrets_state)
        return {"node_id": node_id, "action": action, "removed": action == "remove", "node": None if action == "remove" else _public_node(node)}

    def configure_listener(self, value: Mapping[str, Any]) -> dict[str, Any]:
        listener = ListenerConfiguration(
            enabled=bool(value.get("enabled")),
            bind_host=str(value.get("bind_host") or "").strip() or None,
            port=int(value.get("port") or 0),
            certificate_fingerprint=str(value.get("certificate_fingerprint") or "").strip() or None,
        )
        if listener.enabled:
            material = self._pki().ensure(str(listener.bind_host))
            listener = ListenerConfiguration(
                enabled=True,
                bind_host=listener.bind_host,
                port=listener.port,
                certificate_fingerprint=material["certificate_fingerprint"],
            )
        with self._lock():
            state = self._read()
            state["listener"] = listener.to_dict()
            self._audit(state, "listener.configured", {"enabled": listener.enabled, "bind_host_hash": _hash_text(listener.bind_host or ""), "port": listener.port})
            self._write(state)
        return listener.to_dict()

    def listener_runtime_config(self) -> dict[str, Any]:
        with self._lock():
            listener = self._read().get("listener") or {}
        if not listener.get("enabled"):
            raise WorkerControlError("Worker listener is disabled.", code="listener_disabled")
        material = self._pki().ensure(str(listener["bind_host"]))
        return {**listener, **material}

    def relay_runtime_configs(self) -> list[dict[str, Any]]:
        """Return private host-side Relay material only to the local runtime manager."""
        with self._lock():
            state = self._read()
            secrets_state = self._read_secrets()
        relay = state.get("relay") or {}
        if not relay.get("enabled"):
            return []
        host_node_id = str(secrets_state.get("host_node_id") or "")
        if not host_node_id:
            return []
        identity = self._pki().ensure_relay_client(node_id=host_node_id)
        sessions = secrets_state.get("relay_sessions") or {}
        configs: list[dict[str, Any]] = []
        for node_id, record in sessions.items():
            node = state.get("nodes", {}).get(node_id) or {}
            if node.get("state") == "revoked" or not node.get("approved_at"):
                continue
            if float(record.get("expires_at") or 0) <= self.clock():
                continue
            configs.append(
                {
                    "endpoint": relay["endpoint"],
                    "host_node_id": host_node_id,
                    "peer_node_id": node_id,
                    "session_id": record["session_id"],
                    "session_key": record["session_key"],
                    **identity,
                }
            )
        return configs

    def configure_relay(self, value: Mapping[str, Any]) -> dict[str, Any]:
        enabled = bool(value.get("enabled"))
        endpoint = str(value.get("endpoint") or "").strip()
        if enabled:
            parsed = urllib.parse.urlparse(endpoint)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise WorkerControlError("Relay requires a credential-free HTTPS endpoint.", code="relay_endpoint_invalid")
        record = {
            "enabled": enabled,
            "endpoint": endpoint if enabled else None,
            "status": "configured" if enabled else "disabled",
            "stores_job_content": False,
            "stores_credentials": False,
        }
        with self._lock():
            state = self._read()
            secrets_state = self._read_secrets()
            state["relay"] = record
            if enabled:
                host_node_id = str(secrets_state.get("host_node_id") or f"node-host-{secrets.token_hex(8)}")
                secrets_state["host_node_id"] = host_node_id
                sessions = secrets_state.setdefault("relay_sessions", {})
                now = self.clock()
                for node_id, node in state.get("nodes", {}).items():
                    if node.get("state") == "revoked" or not node.get("approved_at"):
                        continue
                    prior = sessions.get(node_id) if isinstance(sessions.get(node_id), Mapping) else {}
                    if float(prior.get("expires_at") or 0) > now:
                        continue
                    sessions[node_id] = {
                        "session_id": f"relay-{uuid.uuid4().hex}",
                        "peer_node_id": host_node_id,
                        "session_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
                        "created_at": now,
                        "expires_at": now + 30 * 24 * 60 * 60,
                    }
            self._audit(state, "relay.configured", {"enabled": enabled, "endpoint_hash": _hash_text(endpoint) if endpoint else None})
            self._write(state)
            self._write_secrets(secrets_state)
        return record

    def relay_transport_directives(self) -> list[dict[str, Any]]:
        """Return private switch material for authenticated Coordinator delivery."""
        with self._lock():
            state = self._read()
            secrets_state = self._read_secrets()
        relay = state.get("relay") or {}
        if not relay.get("enabled"):
            return []
        endpoint = str(relay.get("endpoint") or "")
        parsed = urllib.parse.urlparse(endpoint)
        directives: list[dict[str, Any]] = []
        for node_id, session in (secrets_state.get("relay_sessions") or {}).items():
            node = state.get("nodes", {}).get(node_id) or {}
            if node.get("state") == "revoked" or not node.get("approved_at"):
                continue
            if float(session.get("expires_at") or 0) <= self.clock():
                continue
            directives.append(
                {
                    "node_id": node_id,
                    "transport": "relay",
                    "endpoint": endpoint,
                    "server_name": parsed.hostname,
                    "relay_session_id": session["session_id"],
                    "relay_peer_node_id": session["peer_node_id"],
                    "relay_session_key": session["session_key"],
                }
            )
        return directives

    def install_command(self, pairing: Mapping[str, Any], *, platform_name: str) -> dict[str, Any]:
        target = str(platform_name or "").lower()
        if target not in {"macos-x86_64", "macos-arm64", "linux-x86_64", "linux-arm64"}:
            raise WorkerControlError("Worker platform is unsupported.", code="worker_platform_unsupported")
        listener = self.snapshot()["listener"]
        relay = self.snapshot()["relay"]
        endpoint = None
        transport = None
        if listener.get("enabled"):
            endpoint = f"https://{listener['bind_host']}:{listener['port']}"
            transport = "direct"
        elif relay.get("enabled"):
            raise WorkerControlError(
                "Relay pairing requires an approved enrollment transport and is not available from this release catalog.",
                code="relay_enrollment_unavailable",
                status_code=409,
            )
        if not endpoint:
            raise WorkerControlError("Enable a direct listener or Relay before creating an install command.", code="worker_endpoint_unavailable")
        catalog = _worker_release_catalog()
        if not catalog.get("published"):
            raise WorkerControlError("The verified Worker release is not published yet.", code="worker_release_unavailable", status_code=409)
        bootstrap = catalog.get("bootstrap")
        asset = (catalog.get("assets") or {}).get(target)
        if not isinstance(bootstrap, Mapping) or not isinstance(asset, Mapping):
            raise WorkerControlError("The Worker release does not support this platform.", code="worker_release_platform_unavailable", status_code=409)
        bootstrap_url, bootstrap_sha = _verified_release_asset(bootstrap, "bootstrap")
        distribution_url, distribution_sha = _verified_release_asset(asset, target)
        material = self._pki().ensure(str(listener["bind_host"]))
        ca_base64 = base64.urlsafe_b64encode(Path(material["ca_certificate"]).read_bytes()).decode("ascii")
        enrollment_endpoint = f"https://{listener['bind_host']}:{int(listener['port']) + 2}"
        installer_arguments = [
            "python3",
            "${ACROSS_WORKER_BOOTSTRAP}",
            "--distribution-url", distribution_url,
            "--distribution-sha256", distribution_sha,
            "--version", str(catalog.get("version") or ""),
            "--worker-endpoint", endpoint,
            "--enrollment-endpoint", enrollment_endpoint,
            "--enrollment-ca-base64", ca_base64,
            "--transport", transport,
            "--enrollment-id", str(pairing["enrollment_id"]),
            "--pairing-code", str(pairing["pairing_code"]),
        ]
        if pairing.get("display_name"):
            installer_arguments.extend(["--display-name", str(pairing["display_name"])])
        scenario_pack = (catalog.get("workflow_packs") or {}).get("scenario-simulation")
        if isinstance(scenario_pack, Mapping):
            pack_url, pack_sha = _verified_release_asset(scenario_pack, "scenario-simulation")
            installer_arguments.extend(["--pack-url", pack_url, "--pack-sha256", pack_sha])
        checksum_command = (
            f"printf '%s  %s\\n' {shlex.quote(bootstrap_sha)} \"$ACROSS_WORKER_BOOTSTRAP\" | "
            + ("/usr/bin/shasum -a 256 -c -" if target.startswith("macos-") else "sha256sum -c -")
        )
        argument_text = " ".join(
            '"$ACROSS_WORKER_BOOTSTRAP"' if item == "${ACROSS_WORKER_BOOTSTRAP}" else shlex.quote(item)
            for item in installer_arguments
        )
        script = (
            "set -eu; ACROSS_WORKER_BOOTSTRAP=$(mktemp); "
            "trap 'rm -f \"$ACROSS_WORKER_BOOTSTRAP\"' EXIT; "
            f"curl --fail --location --proto '=https' --tlsv1.2 --output \"$ACROSS_WORKER_BOOTSTRAP\" {shlex.quote(bootstrap_url)}; "
            f"{checksum_command}; {argument_text}"
        )
        command = ["/bin/sh", "-c", script]
        return {
            "platform": target,
            "argv": command,
            "shell_command": script,
            "expires_at": pairing["expires_at"],
            "contains_long_term_secret": False,
            "release_version": catalog["version"],
            "source_verified": True,
        }

    def _validate_capability(self, value: Mapping[str, Any]) -> None:
        if value.get("schema_version") != "across-node-capability/1.0":
            raise WorkerControlError("Capability schema is incompatible.", code="capability_schema_incompatible")
        if value.get("os") not in {"macos", "linux"} or value.get("architecture") not in {"x86_64", "arm64"}:
            raise WorkerControlError("Worker platform is unsupported.", code="worker_platform_unsupported")
        if value.get("verification_status") != "verified":
            raise WorkerControlError("Worker capabilities have not been verified.", code="capability_unverified")

    def _node(self, state: Mapping[str, Any], node_id: str) -> dict[str, Any]:
        node = state.get("nodes", {}).get(node_id)
        if not isinstance(node, dict):
            raise WorkerControlError("Device was not found.", code="node_not_found", status_code=404)
        return node

    def _hash_pairing(self, enrollment_id: str, code: str, secret_state: Mapping[str, Any]) -> str:
        key = base64.urlsafe_b64decode(str(secret_state["issuer_secret"]).encode())
        return hmac.new(key, f"{enrollment_id}:{code}".encode(), sha256).hexdigest()

    def _verification_code(self, enrollment_id: str, node_id: str, fingerprint: str, secret_state: Mapping[str, Any]) -> str:
        key = base64.urlsafe_b64decode(str(secret_state["issuer_secret"]).encode())
        value = hmac.new(key, f"{enrollment_id}:{node_id}:{fingerprint}".encode(), sha256).hexdigest()
        return f"{int(value[:8], 16) % 1_000_000:06d}"

    def _expire_enrollments(self, state: dict[str, Any]) -> None:
        now = self.clock()
        for enrollment in state["enrollments"].values():
            if enrollment.get("status") == "issued" and now >= float(enrollment.get("expires_at") or 0):
                enrollment["status"] = "expired"

    def _audit(self, state: dict[str, Any], event: str, payload: Mapping[str, Any]) -> None:
        public = _safe_public(payload)
        state["audit"].append(
            {
                "event_id": f"worker-audit-{uuid.uuid4().hex}",
                "event": event,
                "created_at": self.clock(),
                "payload": public,
                "payload_hash": _hash_json(public),
            }
        )
        state["audit"] = state["audit"][-5000:]

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return _empty_state()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            backup = self.path.with_suffix(f".corrupt-{int(self.clock())}.json")
            try:
                os.replace(self.path, backup)
            except OSError:
                pass
            value = _empty_state()
            value["recovery"] = {"status": "recovered_from_corruption", "at": self.clock(), "backup_name": backup.name}
        if not isinstance(value, dict) or value.get("schema_version") != WORKER_CONTROL_SCHEMA:
            return _empty_state()
        for key, fallback in (("nodes", {}), ("enrollments", {}), ("audit", []), ("listener", ListenerConfiguration().to_dict()), ("relay", {"enabled": False, "status": "disabled"})):
            value.setdefault(key, fallback)
        return value

    def _read_secrets(self) -> dict[str, Any]:
        if self.secret_path.exists():
            try:
                value = json.loads(self.secret_path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value.get("schema_version") == "across-worker-secrets/1.0":
                    return value
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "schema_version": "across-worker-secrets/1.0",
            "issuer_secret": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "pairing_hashes": {},
            "relay_sessions": {},
            "activations": {},
            "activation_nonces": {},
        }

    def _write(self, value: Mapping[str, Any]) -> None:
        _atomic_json(self.path, value, mode=0o600)

    def _write_secrets(self, value: Mapping[str, Any]) -> None:
        _atomic_json(self.secret_path, value, mode=0o600)

    def _public_state(self, state: Mapping[str, Any]) -> dict[str, Any]:
        try:
            catalog = _worker_release_catalog()
            release = {
                "published": bool(catalog.get("published")),
                "version": str(catalog.get("version") or "") or None,
                "platforms": sorted((catalog.get("assets") or {}).keys()) if catalog.get("published") else [],
            }
        except WorkerControlError:
            release = {"published": False, "version": None, "platforms": []}
        return {
            "schema_version": WORKER_CONTROL_SCHEMA,
            "nodes": [_public_node(node) for node in state.get("nodes", {}).values()],
            "pending": [_public_node(node) for node in state.get("nodes", {}).values() if node.get("state") == "pending_approval"],
            "listener": _safe_public(state.get("listener") or {}),
            "relay": _safe_public(state.get("relay") or {}),
            "health": self._health(state),
            "recovery": state.get("recovery"),
            "release": release,
        }

    def host_verification_code(self, node_id: str) -> dict[str, Any]:
        """Return a short pending code only to AAA's local host UI endpoint."""
        with self._lock():
            state = self._read()
            node = self._node(state, _require_id(node_id, "node_id"))
            if node.get("state") != "pending_approval":
                raise WorkerControlError("Device is not waiting for approval.", code="node_not_pending")
            code = str(node.get("verification_code") or "")
            if not re.fullmatch(r"[0-9]{6}", code):
                raise WorkerControlError("Device verification code is unavailable.", code="verification_code_unavailable")
            return {"node_id": node_id, "verification_code": code, "expires_with_pairing": True}

    def _health(self, state: Mapping[str, Any]) -> dict[str, Any]:
        nodes = list(state.get("nodes", {}).values())
        return {
            "status": "ok",
            "node_count": len(nodes),
            "online_count": sum(node.get("state") in {"online_idle", "online_busy", "draining"} for node in nodes),
            "pending_count": sum(node.get("state") == "pending_approval" for node in nodes),
            "incompatible_count": sum(node.get("state") == "incompatible" for node in nodes),
            "listener_enabled": bool(state.get("listener", {}).get("enabled")),
            "relay_enabled": bool(state.get("relay", {}).get("enabled")),
            "secrets_in_public_state": False,
        }

    def _lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        return _FileLock(self.lock_path)

    def _pki(self) -> WorkerCertificateAuthority:
        return WorkerCertificateAuthority(self.secret_path.parent / "worker-pki")


class WorkerOrchestratorClient:
    """Protocol/CLI adapter; AAA never imports Orchestrator implementation modules."""

    def __init__(
        self,
        command: list[str] | None = None,
        *,
        timeout_seconds: float = WORKER_CONTROL_COMMAND_TIMEOUT_SECONDS,
        socket_path: str | Path | None = None,
    ):
        self.command = command or _orchestrator_command()
        self.timeout_seconds = timeout_seconds
        self.socket_path = Path(socket_path).expanduser().resolve() if socket_path else run_dir() / "worker-control.sock"

    def call(self, action: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not _ID.fullmatch(str(action or "")):
            raise WorkerControlError("Orchestrator action is invalid.", code="orchestrator_action_invalid")
        request = json.dumps({"schema_version": "across-worker-control-command/1.0", "action": action, "payload": dict(payload or {})}, sort_keys=True)
        if self.socket_path.exists():
            try:
                return self._call_socket(request)
            except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
                pass
        try:
            completed = subprocess.run(
                [*self.command, "worker-control", "--json"],
                input=request,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=_safe_subprocess_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkerControlError("Across Orchestrator is unavailable.", code="orchestrator_unavailable", status_code=503) from exc
        if completed.returncode != 0:
            raise WorkerControlError("Across Orchestrator rejected the Worker operation.", code="orchestrator_operation_failed", status_code=502)
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise WorkerControlError("Across Orchestrator returned an invalid response.", code="orchestrator_response_invalid", status_code=502) from exc
        if not isinstance(value, dict):
            raise WorkerControlError("Across Orchestrator returned an invalid response.", code="orchestrator_response_invalid", status_code=502)
        return _safe_public(value)

    def _call_socket(self, request: str) -> dict[str, Any]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout_seconds)
            connection.connect(str(self.socket_path))
            connection.sendall(request.encode("utf-8") + b"\n")
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = connection.recv(1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > 64 * 1024 * 1024:
                    raise ValueError("worker control response is too large")
                if chunk.endswith(b"\n"):
                    break
        value = json.loads(b"".join(chunks))
        if not isinstance(value, dict) or value.get("status") == "error":
            raise ValueError("worker control socket rejected the operation")
        return _safe_public(value)


class WorkerCoordinatorPresenceCache:
    """Refresh live Coordinator presence without blocking a read-only UI request.

    The managed Orchestrator executable can have a measurable cold-start cost in
    a packaged app.  Reads return the most recent public snapshot immediately
    while a single daemon thread refreshes it in the background.
    """

    def __init__(
        self,
        client_factory: Callable[[], WorkerOrchestratorClient] = WorkerOrchestratorClient,
        *,
        refresh_interval_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.client_factory = client_factory
        self.refresh_interval_seconds = max(1.0, float(refresh_interval_seconds))
        self.clock = clock
        self._lock = threading.RLock()
        self._snapshot: dict[str, Any] | None = None
        self._refreshed_at = 0.0
        self._refreshing = False
        self._last_error: str | None = None
        self._refresh_finished = threading.Event()
        self._refresh_finished.set()

    def snapshot(self, *, wait_for_refresh_seconds: float = 0.0) -> dict[str, Any] | None:
        start_refresh = False
        with self._lock:
            now = self.clock()
            if not self._refreshing and now - self._refreshed_at >= self.refresh_interval_seconds:
                self._refreshing = True
                self._refresh_finished.clear()
                start_refresh = True
            value = _safe_public(self._snapshot) if self._snapshot is not None else None
        if start_refresh:
            threading.Thread(target=self._refresh, name="across-worker-presence-refresh", daemon=True).start()
        if wait_for_refresh_seconds > 0 and (start_refresh or self._refreshing):
            self._refresh_finished.wait(timeout=max(0.0, min(float(wait_for_refresh_seconds), 1.0)))
            with self._lock:
                value = _safe_public(self._snapshot) if self._snapshot is not None else None
        return value

    def invalidate(self) -> None:
        with self._lock:
            self._refreshed_at = 0.0

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def _refresh(self) -> None:
        value: dict[str, Any] | None = None
        error: str | None = None
        try:
            value = self.client_factory().call("snapshot")
        except WorkerControlError as exc:
            error = exc.code
        except Exception:
            error = "orchestrator_unavailable"
        with self._lock:
            if value is not None:
                self._snapshot = _safe_public(value)
            self._last_error = error
            self._refreshed_at = self.clock()
            self._refreshing = False
            self._refresh_finished.set()


def merge_coordinator_presence(
    host_snapshot: dict[str, Any],
    coordinator_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Overlay live session state without moving approval ownership out of AAA."""
    coordinator_nodes = {
        str(item.get("node_id") or ""): item
        for item in coordinator_snapshot.get("nodes", [])
        if isinstance(item, Mapping) and item.get("node_id")
    }
    nodes = host_snapshot.get("nodes") or []
    for node in nodes:
        if not isinstance(node, dict) or node.get("state") in {"pending_approval", "revoked"}:
            continue
        live = coordinator_nodes.get(str(node.get("node_id") or ""))
        if not live:
            continue
        state = str(live.get("state") or "")
        transport = str(live.get("transport") or "")
        if state in NODE_STATES:
            node["state"] = state
        if transport in TRANSPORTS:
            node["transport"] = transport
        if live.get("last_seen_at") is not None:
            node["last_seen_at"] = live.get("last_seen_at")

    health = host_snapshot.get("health")
    if isinstance(health, dict):
        health["online_count"] = sum(
            item.get("state") in {"online_idle", "online_busy", "draining"}
            for item in nodes
            if isinstance(item, Mapping)
        )
        health["incompatible_count"] = sum(
            item.get("state") == "incompatible"
            for item in nodes
            if isinstance(item, Mapping)
        )
    return host_snapshot


class WorkerNetworkRuntimeManager:
    """Own the explicit Worker listener and narrow model gateway with the AAA backend."""

    def __init__(
        self,
        store: WorkerTrustStore | None = None,
        *,
        orchestrator_command: list[str] | None = None,
        gateway_command: list[str] | None = None,
        enrollment_command: list[str] | None = None,
        popen=subprocess.Popen,
    ):
        self.store = store or get_worker_trust_store()
        self.orchestrator_command = orchestrator_command
        self.gateway_command = gateway_command
        self.enrollment_command = enrollment_command
        self._popen = popen
        self._lock = threading.RLock()
        self._listener_process: Any = None
        self._control_process: Any = None
        self._gateway_process: Any = None
        self._enrollment_process: Any = None
        self._relay_processes: dict[str, Any] = {}
        self._relay_key_paths: set[Path] = set()
        self._signature: str | None = None
        self._last_error: str | None = None
        self._lease_path = run_dir() / "worker-model-host-lease.json"

    def reconcile(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self.store.snapshot()
            listener = snapshot.get("listener") or {}
            relay = snapshot.get("relay") or {}
            if not listener.get("enabled") and not relay.get("enabled"):
                self._stop_locked()
                self._last_error = None
                return self.status()
            try:
                config = self.store.listener_runtime_config() if listener.get("enabled") else None
                configs = self.store.relay_runtime_configs() if relay.get("enabled") else []
                signature = _hash_json(
                    {
                        "mode": "combined" if config and relay.get("enabled") else ("direct" if config else "relay"),
                        "bind_host": config.get("bind_host") if config else None,
                        "port": config.get("port") if config else None,
                        "certificate_fingerprint": config.get("certificate_fingerprint") if config else None,
                        "sessions": [
                            {
                                "endpoint": item["endpoint"],
                                "host_node_id": item["host_node_id"],
                                "peer_node_id": item["peer_node_id"],
                                "session_id": item["session_id"],
                                "session_key_hash": _hash_text(item["session_key"]),
                            }
                            for item in configs
                        ],
                        "orchestrator_command": self.orchestrator_command or _orchestrator_command(),
                        "gateway_command": self.gateway_command or _worker_model_gateway_command(),
                        "enrollment_command": self.enrollment_command or _worker_enrollment_gateway_command(),
                    }
                )
                control_running = self._process_running(self._control_process)
                direct_running = control_running and (not config or (
                    self._process_running(self._listener_process)
                    and self._process_running(self._gateway_process)
                    and self._process_running(self._enrollment_process)
                ))
                relay_running = control_running and all(self._process_running(item) for item in self._relay_processes.values())
                if signature == self._signature and direct_running and relay_running:
                    self._last_error = None
                    return self.status()
                self._stop_locked()
                self._start_control_locked()
                if config:
                    self._start_locked(config, signature)
                if relay.get("enabled"):
                    self._start_relay_locked(configs, signature)
                else:
                    self._signature = signature
                self._last_error = None
            except Exception as exc:
                self._stop_locked()
                self._last_error = _runtime_error_code(exc)
            return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            listener_running = self._process_running(self._listener_process)
            control_running = self._process_running(self._control_process)
            gateway_running = self._process_running(self._gateway_process)
            enrollment_running = self._process_running(self._enrollment_process)
            relay_running = sum(self._process_running(item) for item in self._relay_processes.values())
            snapshot = self.store.snapshot()
            configured = bool(snapshot.get("listener", {}).get("enabled") or snapshot.get("relay", {}).get("enabled"))
            if control_running and listener_running and gateway_running and enrollment_running:
                state = "running"
            elif control_running and snapshot.get("relay", {}).get("enabled") and relay_running == len(self._relay_processes):
                state = "running" if relay_running else "waiting_for_approved_worker"
            elif configured and self._last_error:
                state = "degraded"
            else:
                state = "stopped"
            return {
                "status": state,
                "listener_running": listener_running,
                "control_server_running": control_running,
                "model_gateway_running": gateway_running,
                "enrollment_gateway_running": enrollment_running,
                "listener_pid": int(self._listener_process.pid) if listener_running else None,
                "control_server_pid": int(self._control_process.pid) if control_running else None,
                "model_gateway_pid": int(self._gateway_process.pid) if gateway_running else None,
                "enrollment_gateway_pid": int(self._enrollment_process.pid) if enrollment_running else None,
                "relay_session_count": len(self._relay_processes),
                "relay_running_count": relay_running,
                "last_error": self._last_error,
                "tls_minimum": "1.3" if configured else None,
                "host_credentials_copied": False,
            }

    def _start_control_locked(self) -> None:
        orchestrator = list(self.orchestrator_command or _orchestrator_command())
        executable = Path(orchestrator[0]).expanduser()
        if executable.is_absolute() and not executable.exists():
            raise FileNotFoundError("managed_orchestrator_missing")
        socket_path = run_dir() / "worker-control.sock"
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass
        runtime_logs = log_dir()
        runtime_logs.mkdir(parents=True, exist_ok=True)
        self._control_process = self._spawn(
            [*orchestrator, "worker-control-server", "--socket", str(socket_path)],
            _safe_subprocess_env(),
            runtime_logs / "worker-control-server.log",
        )
        if self._popen is subprocess.Popen:
            # The managed Orchestrator is a self-contained PyInstaller runtime.
            # Its first launch can spend tens of seconds in macOS verification
            # and extraction while the App's other optional services are also
            # restoring.  Keep this work off the UI startup path, but allow a
            # bounded cold start to finish instead of killing a healthy process
            # just before its private socket becomes available.
            deadline = time.monotonic() + WORKER_CONTROL_STARTUP_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if not self._process_running(self._control_process):
                    raise RuntimeError("worker_control_process_exited")
                if socket_path.exists():
                    return
                time.sleep(0.05)
            raise RuntimeError("worker_control_socket_timeout")

    def _start_relay_locked(self, configs: list[Mapping[str, Any]], signature: str) -> None:
        orchestrator = list(self.orchestrator_command or _orchestrator_command())
        executable = Path(orchestrator[0]).expanduser()
        if executable.is_absolute() and not executable.exists():
            raise FileNotFoundError("managed_orchestrator_missing")
        artifacts = data_file("worker-artifacts")
        artifacts.mkdir(parents=True, exist_ok=True)
        runtime_logs = log_dir()
        runtime_logs.mkdir(parents=True, exist_ok=True)
        env = _safe_subprocess_env()
        for config in configs:
            node_id = str(config["peer_node_id"])
            key_path = run_dir() / f"worker-relay-{_hash_text(node_id)[:16]}.key"
            _atomic_text(key_path, str(config["session_key"]) + "\n", mode=0o600)
            self._relay_key_paths.add(key_path)
            argv = [
                *orchestrator,
                "worker-relay-session",
                "--endpoint",
                str(config["endpoint"]),
                "--node-id",
                str(config["host_node_id"]),
                "--peer-node-id",
                node_id,
                "--session-id",
                str(config["session_id"]),
                "--session-key-file",
                str(key_path),
                "--certificate",
                str(config["certificate"]),
                "--private-key",
                str(config["private_key"]),
                "--artifact-root",
                str(artifacts),
                "--model-gateway-unix-socket",
                str(backend_socket_path()),
            ]
            self._relay_processes[node_id] = self._spawn(argv, env, runtime_logs / f"worker-relay-{_hash_text(node_id)[:16]}.log")
        time.sleep(0.05)
        if any(not self._process_running(item) for item in self._relay_processes.values()):
            raise RuntimeError("worker_relay_process_exited")
        self._signature = signature

    def shutdown(self) -> None:
        with self._lock:
            self._stop_locked()
            self._last_error = None

    def _start_locked(self, config: Mapping[str, Any], signature: str) -> None:
        host = str(config["bind_host"])
        port = int(config["port"])
        gateway_port = port + 1
        orchestrator = list(self.orchestrator_command or _orchestrator_command())
        gateway = list(self.gateway_command or _worker_model_gateway_command())
        enrollment = list(self.enrollment_command or _worker_enrollment_gateway_command())
        executable = Path(orchestrator[0]).expanduser()
        if executable.is_absolute() and not executable.exists():
            raise FileNotFoundError("managed_orchestrator_missing")

        artifacts = data_file("worker-artifacts")
        artifacts.mkdir(parents=True, exist_ok=True)
        runtime_logs = log_dir()
        runtime_logs.mkdir(parents=True, exist_ok=True)
        self._write_host_model_lease()
        env = _safe_subprocess_env()
        env["ACROSS_AAA_CANDIDATE_MODEL_LEASE"] = str(self._lease_path)
        gateway_argv = [
            *gateway,
            "--host",
            host,
            "--port",
            str(gateway_port),
            "--certificate",
            str(config["server_certificate"]),
            "--private-key",
            str(config["server_private_key"]),
            "--client-ca",
            str(config["ca_certificate"]),
        ]
        enrollment_argv = [
            *enrollment,
            "--host",
            host,
            "--port",
            str(port + 2),
            "--certificate",
            str(config["server_certificate"]),
            "--private-key",
            str(config["server_private_key"]),
        ]
        listener_argv = [
            *orchestrator,
            "worker-listener",
            "--host",
            host,
            "--port",
            str(port),
            "--certificate",
            str(config["server_certificate"]),
            "--private-key",
            str(config["server_private_key"]),
            "--client-ca",
            str(config["ca_certificate"]),
            "--artifact-root",
            str(artifacts),
            "--transport",
            "direct",
            "--model-gateway-url",
            f"https://{host}:{gateway_port}/invoke",
        ]
        self._gateway_process = self._spawn(gateway_argv, env, runtime_logs / "worker-model-gateway.log")
        self._enrollment_process = self._spawn(enrollment_argv, env, runtime_logs / "worker-enrollment-gateway.log")
        self._listener_process = self._spawn(listener_argv, env, runtime_logs / "worker-listener.log")
        time.sleep(0.05)
        if not self._process_running(self._gateway_process) or not self._process_running(self._enrollment_process) or not self._process_running(self._listener_process):
            raise RuntimeError("worker_network_process_exited")
        self._signature = signature

    def _spawn(self, argv: list[str], env: Mapping[str, str], log_path: Path):
        with log_path.open("ab", buffering=0) as handle:
            return self._popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                env=dict(env),
                start_new_session=True,
                close_fds=True,
            )

    def _write_host_model_lease(self) -> None:
        now = time.time()
        _atomic_json(
            self._lease_path,
            {
                "schema_version": "across-candidate-model-lease/1.0",
                "lease_id": f"worker-host-{uuid.uuid4().hex}",
                "candidate_id": "worker-model-gateway",
                "transport": "unix-socket",
                "host_socket": backend_socket_path(),
                "scopes": ["worker.model.invoke"],
                "issued_at_unix": now,
                "policy": {"secrets_included": False, "raw_credentials_allowed": False},
            },
            mode=0o600,
        )

    def _stop_locked(self) -> None:
        for process in (self._listener_process, self._gateway_process, self._enrollment_process, *self._relay_processes.values(), self._control_process):
            if not self._process_running(process):
                continue
            try:
                process.terminate()
            except OSError:
                pass
            try:
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except OSError:
                    pass
        self._listener_process = None
        self._control_process = None
        self._gateway_process = None
        self._enrollment_process = None
        self._relay_processes = {}
        self._signature = None
        try:
            self._lease_path.unlink()
        except FileNotFoundError:
            pass
        try:
            (run_dir() / "worker-control.sock").unlink()
        except FileNotFoundError:
            pass
        for path in self._relay_key_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self._relay_key_paths.clear()

    @staticmethod
    def _process_running(process: Any) -> bool:
        return process is not None and process.poll() is None


_trust_store: WorkerTrustStore | None = None
_network_runtime: WorkerNetworkRuntimeManager | None = None
_presence_cache: WorkerCoordinatorPresenceCache | None = None


def get_worker_trust_store() -> WorkerTrustStore:
    global _trust_store
    expected = _default_store_path()
    if _trust_store is None or _trust_store.path != expected:
        _trust_store = WorkerTrustStore()
    return _trust_store


def reset_worker_trust_store_for_tests() -> None:
    global _trust_store, _presence_cache
    _trust_store = None
    _presence_cache = None


def get_worker_presence_cache() -> WorkerCoordinatorPresenceCache:
    global _presence_cache
    if _presence_cache is None:
        _presence_cache = WorkerCoordinatorPresenceCache()
    return _presence_cache


def get_worker_network_runtime() -> WorkerNetworkRuntimeManager:
    global _network_runtime
    store = get_worker_trust_store()
    if _network_runtime is None or _network_runtime.store.path != store.path:
        if _network_runtime is not None:
            _network_runtime.shutdown()
        _network_runtime = WorkerNetworkRuntimeManager(store)
    return _network_runtime


def reset_worker_network_runtime_for_tests() -> None:
    global _network_runtime
    if _network_runtime is not None:
        _network_runtime.shutdown()
    _network_runtime = None


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": WORKER_CONTROL_SCHEMA,
        "nodes": {},
        "enrollments": {},
        "listener": ListenerConfiguration().to_dict(),
        "relay": {"enabled": False, "endpoint": None, "status": "disabled", "stores_job_content": False, "stores_credentials": False},
        "audit": [],
        "revoked_certificate_serials": [],
        "recovery": None,
    }


def _public_node(node: Mapping[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in node.items() if key not in {"public_key_pem", "verification_code"}}
    return _safe_public(public)


def _safe_public(value: Any, key: str = "") -> Any:
    if isinstance(value, Mapping):
        return {str(name): _safe_public(item, str(name)) for name, item in value.items() if not _SECRET_KEYS.search(str(name))}
    if isinstance(value, list):
        return [_safe_public(item) for item in value]
    if isinstance(value, str):
        text = _USER_PATH.sub("<user-home>", value)
        text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [redacted]", text)
        text = re.sub(r"(?i)(?:sk|gh[op])[-_][A-Za-z0-9_-]{16,}", "[redacted]", text)
        return text
    return value


def _require_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not _ID.fullmatch(text):
        raise WorkerControlError(f"{field} is invalid.", code="protocol_identifier_invalid")
    return text


def _hash_text(value: str) -> str:
    return sha256(str(value).encode()).hexdigest()


def _hash_json(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _worker_release_catalog() -> dict[str, Any]:
    override = os.environ.get("ACROSS_WORKER_RELEASE_CATALOG")
    path = (
        Path(override).expanduser().resolve()
        if override
        else Path(__file__).resolve().parent / "assets" / "worker-release-catalog.json"
    )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkerControlError("The Worker release catalog is unavailable.", code="worker_release_unavailable", status_code=409) from exc
    if not isinstance(value, dict) or value.get("schema_version") != "across-worker-release-catalog/1.0":
        raise WorkerControlError("The Worker release catalog is incompatible.", code="worker_release_unavailable", status_code=409)
    if value.get("published") and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", str(value.get("version") or "")):
        raise WorkerControlError("The Worker release catalog version is invalid.", code="worker_release_unavailable", status_code=409)
    return value


def _verified_release_asset(value: Mapping[str, Any], label: str) -> tuple[str, str]:
    url = str(value.get("url") or "")
    checksum = str(value.get("sha256") or "")
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or not re.fullmatch(r"[0-9a-f]{64}", checksum)
    ):
        raise WorkerControlError(
            f"The verified Worker {label} release asset is invalid.",
            code="worker_release_unavailable",
            status_code=409,
        )
    return url, checksum


def _atomic_json(path: Path, value: Mapping[str, Any], *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(mode)
    os.replace(temporary, path)


def _atomic_text(path: Path, value: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(mode)
    os.replace(temporary, path)


def _shell_join(argv: list[str]) -> str:
    import shlex

    return shlex.join(argv)


def _orchestrator_command() -> list[str]:
    override = os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_COMMAND")
    if override:
        import shlex

        return shlex.split(override)
    managed = ecosystem_bin_dir() / "across-orchestrator"
    return [str(managed if managed.exists() else "across-orchestrator")]


def _safe_subprocess_env() -> dict[str, str]:
    allowed = {
        "HOME",
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "ACROSS_HOME",
        "ACROSS_BIN_HOME",
        "ACROSS_ORCHESTRATOR_HOME",
        "ACROSS_AGENTS_HOME",
        "ACROSS_AGENTS_WORKER_CONTROL_FILE",
        "ACROSS_AGENTS_WORKER_SECRET_FILE",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def _worker_model_gateway_command() -> list[str]:
    override = os.environ.get("ACROSS_AGENTS_WORKER_MODEL_GATEWAY_COMMAND")
    if override:
        import shlex

        return shlex.split(override)
    if getattr(sys, "frozen", False):
        return [sys.executable, "worker-model-gateway"]
    return [sys.executable, "-m", "across_agents_assistant.worker_model_gateway"]


def _worker_enrollment_gateway_command() -> list[str]:
    override = os.environ.get("ACROSS_AGENTS_WORKER_ENROLLMENT_COMMAND")
    if override:
        import shlex

        return shlex.split(override)
    if getattr(sys, "frozen", False):
        return [sys.executable, "worker-enrollment-gateway"]
    return [sys.executable, "-m", "across_agents_assistant.worker_enrollment_gateway"]


def _runtime_error_code(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return "managed_orchestrator_missing"
    if isinstance(exc, PermissionError):
        return "runtime_permission_denied"
    return "runtime_start_failed"


class _FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.handle = self.path.open("a+")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
