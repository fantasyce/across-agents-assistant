#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== git whitespace check =="
git diff --check

echo "== forbidden tracked files =="
forbidden_tracked="$(
  git ls-files | grep -E '(^docs/|^\.claude/|^\.superpowers/|\.dmg$|\.p12$|\.pem$|\.key$|\.cer$|\.mobileprovision$|\.db$|\.sqlite3?$)' || true
)"
if [[ -n "$forbidden_tracked" ]]; then
  echo "$forbidden_tracked"
  echo "Forbidden local, private, credential, database, or package artifacts are tracked." >&2
  exit 1
fi

echo "== sensitive text scan =="
SENSITIVE_PATTERN='(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}|(^|[^A-Za-z0-9])[A-Z0-9_]*API_KEY=|/Users/fanhcy|BEGIN (RSA|OPENSSH|PRIVATE) KEY|Apple Developer|com\.apple\.developer\.team-identifier'
if command -v rg >/dev/null 2>&1; then
  sensitive_hits="$(
    rg -n --hidden \
      --glob '!.git/**' \
      --glob '!backend/.venv/**' \
      --glob '!docs/**' \
      --glob '!build/**' \
      --glob '!dist/**' \
      --glob '!macOS-Client/.build/**' \
      --glob '!macOS-Client/build/**' \
      --glob '!scripts/open_source_check.sh' \
      --glob '!assets/readme/*.png' \
      --glob '!*.icns' \
      --glob '!*.png' \
      --glob '!*.jpg' \
      --glob '!*.jpeg' \
      --glob '!*.webp' \
      "$SENSITIVE_PATTERN" . || true
  )"
else
  sensitive_hits="$(
    git grep -n -E -I "$SENSITIVE_PATTERN" -- \
      . \
      ':(exclude)docs/**' \
      ':(exclude)build/**' \
      ':(exclude)dist/**' \
      ':(exclude)macOS-Client/.build/**' \
      ':(exclude)macOS-Client/build/**' \
      ':(exclude)scripts/open_source_check.sh' \
      ':(exclude)assets/readme/*.png' \
      ':(exclude)*.icns' \
      ':(exclude)*.png' \
      ':(exclude)*.jpg' \
      ':(exclude)*.jpeg' \
      ':(exclude)*.webp' || true
  )"
fi
if [[ -n "$sensitive_hits" ]]; then
  echo "$sensitive_hits"
  echo "Potential secret, private path, or signing metadata found in publishable files." >&2
  exit 1
fi

echo "== README image assets =="
missing_assets=0
while IFS= read -r asset_path; do
  [[ -z "$asset_path" || "$asset_path" == http* ]] && continue
  if [[ ! -f "$asset_path" ]]; then
    echo "Missing README asset: $asset_path" >&2
    missing_assets=1
  fi
done < <(perl -ne 'while (/src="([^"]+)"/g) { print "$1\n" }' README.md)
if [[ "$missing_assets" -ne 0 ]]; then
  exit 1
fi

echo "== third-party icon release statuses =="
python3 - <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path("macOS-Client/Sources/Assets/icons/agent-icon-sources.json")
if not manifest_path.exists():
    raise SystemExit(0)

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
blocked_statuses = {"review-before-release"}
blocked = [
    entry
    for entry in manifest.get("bundled_icons", [])
    if entry.get("redistribution_status") in blocked_statuses
]
if blocked:
    for entry in blocked:
        print(
            f"{entry.get('agent_id')}: unresolved icon redistribution status "
            f"{entry.get('redistribution_status')}",
            file=sys.stderr,
        )
    raise SystemExit(1)
PY

echo "== shell syntax =="
bash -n build_app.sh scripts/*.sh

echo "Open-source check passed."
