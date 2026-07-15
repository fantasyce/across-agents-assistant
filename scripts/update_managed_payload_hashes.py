from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        raise SystemExit("usage: update_managed_payload_hashes.py PAYLOAD_ROOT")
    root = Path(argv[0]).expanduser().resolve()
    manifest_path = root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    node = root / payload["runtimes"]["node"]["path"] / payload["runtimes"]["node"]["executable"]
    orchestrator = root / payload["plugins"]["across-orchestrator"]["executable"]
    payload["runtimes"]["node"]["sha256"] = sha256(node)
    payload["plugins"]["across-orchestrator"]["sha256"] = sha256(orchestrator)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
