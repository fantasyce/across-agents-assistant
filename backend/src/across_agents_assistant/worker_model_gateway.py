from __future__ import annotations

import argparse
import ssl

import uvicorn
from fastapi import FastAPI

from .api_server import WorkerModelInvokeRequest, invoke_worker_model_gateway_core


app = FastAPI(
    title="Across task-bound Model Grant gateway",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "schema_version": "across-worker-model-gateway-health/1.0",
        "status": "ok",
        "provider_credentials_exposed": False,
        "task_grant_required": True,
    }


@app.post("/invoke")
async def invoke(request: WorkerModelInvokeRequest):
    return await invoke_worker_model_gateway_core(request)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the narrow mTLS Worker Model Grant gateway.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--client-ca", required=True)
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
        ssl_ca_certs=args.client_ca,
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        ssl_version=ssl.PROTOCOL_TLS_SERVER,
    )
    config.load()
    if not isinstance(config.ssl, ssl.SSLContext):
        raise RuntimeError("Model Grant gateway TLS context was not created")
    config.ssl.minimum_version = ssl.TLSVersion.TLSv1_3
    config.ssl.maximum_version = ssl.TLSVersion.TLSv1_3
    uvicorn.Server(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
