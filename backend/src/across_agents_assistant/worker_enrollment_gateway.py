from __future__ import annotations

import argparse
import base64
import ssl
from typing import Any

import uvicorn
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .worker_control import WorkerControlError, WorkerOrchestratorClient, get_worker_trust_store


def _canonical_bytes(value: Any) -> bytes:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class PairingEnvelope(BaseModel):
    request: dict[str, Any]
    signature: str = Field(min_length=32, max_length=256)


class ActivationProof(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    enrollment_id: str = Field(min_length=1, max_length=128)
    nonce: str = Field(min_length=16, max_length=128)
    signature: str = Field(min_length=32, max_length=256)


class IdentityRenewalProof(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    current_generation: int = Field(ge=1)
    nonce: str = Field(min_length=16, max_length=128)
    signature: str = Field(min_length=32, max_length=256)


app = FastAPI(
    title="Across Worker enrollment gateway",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "schema_version": "across-worker-enrollment-health/1.0",
        "status": "ok",
        "pairing_code_required": True,
        "device_signature_required": True,
        "automatic_identity_renewal": True,
        "provider_credentials_exposed": False,
    }


@app.post("/v1/pairings")
async def submit_pairing(envelope: PairingEnvelope):
    request = dict(envelope.request)
    identity = request.get("public_identity")
    if not isinstance(identity, dict):
        raise HTTPException(status_code=400, detail={"code": "pairing_payload_invalid"})
    try:
        public_key = serialization.load_pem_public_key(str(identity.get("public_key_pem") or "").encode("ascii"))
        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError("unsupported key")
        signature = base64.urlsafe_b64decode(envelope.signature + "=" * (-len(envelope.signature) % 4))
        public_key.verify(signature, _canonical_bytes(request))
    except (ValueError, TypeError, UnicodeError, InvalidSignature):
        raise HTTPException(status_code=403, detail={"code": "pairing_signature_invalid"})
    try:
        return get_worker_trust_store().submit_pairing(request)
    except WorkerControlError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code})


@app.post("/v1/activations")
async def poll_activation(proof: ActivationProof):
    try:
        return get_worker_trust_store().activation_for_worker(**proof.model_dump())
    except WorkerControlError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code})


@app.post("/v1/identity/renew")
async def renew_identity(proof: IdentityRenewalProof):
    try:
        result = get_worker_trust_store().renew_identity_for_worker(**proof.model_dump())
        node = result["node"]
        WorkerOrchestratorClient().call(
            "node.import_approved",
            {
                "capability_manifest": node["capability_manifest"],
                "display_name": node.get("display_name"),
                "certificate_fingerprint": node["certificate_fingerprint"],
                "session_generation": node["session_generation"],
                "identity_expires_at": node["identity_expires_at"],
            },
        )
        return result
    except WorkerControlError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the TLS 1.3 Worker enrollment gateway.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--private-key", required=True)
    args = parser.parse_args(argv)
    if args.host in {"", "0.0.0.0", "::", "*"}:
        parser.error("an explicit interface address is required")
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
        access_log=False,
        ssl_certfile=args.certificate,
        ssl_keyfile=args.private_key,
        ssl_cert_reqs=ssl.CERT_NONE,
        ssl_version=ssl.PROTOCOL_TLS_SERVER,
    )
    config.load()
    if not isinstance(config.ssl, ssl.SSLContext):
        raise RuntimeError("Worker enrollment TLS context was not created")
    config.ssl.minimum_version = ssl.TLSVersion.TLSv1_3
    config.ssl.maximum_version = ssl.TLSVersion.TLSv1_3
    uvicorn.Server(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
