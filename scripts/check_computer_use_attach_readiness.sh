#!/usr/bin/env bash
set -euo pipefail

OUTPUT="${1:-}"

chrome_status="unknown"
if pgrep -x "Google Chrome" >/dev/null 2>&1; then
  chrome_status="running"
else
  chrome_status="not_running"
fi

ax_status="unknown"
if command -v osascript >/dev/null 2>&1; then
  if osascript -e 'tell application "System Events" to count processes' >/dev/null 2>&1; then
    ax_status="accessible"
  else
    ax_status="not_accessible"
  fi
fi

screen_status="manual_verification_required"

payload="$(
python3 - "$chrome_status" "$ax_status" "$screen_status" <<'PY'
import json
import sys

chrome, ax, screen = sys.argv[1:4]
blocking_product_capability = False
status = "passed" if ax == "accessible" else "attention"
print(json.dumps({
    "schema_version": "across-aaa-computer-use-attach-diagnostic/1.0",
    "status": status,
    "validation_only": True,
    "blocking_product_capability": blocking_product_capability,
    "checks": {
        "chrome_process": chrome,
        "accessibility": ax,
        "screen_capture": screen,
    },
    "next_step": "Use Computer Use manually to attach and click through the UI when frontend validation is required.",
}, indent=2, sort_keys=True))
PY
)"

if [[ -n "$OUTPUT" ]]; then
  mkdir -p "$(dirname "$OUTPUT")"
  printf '%s\n' "$payload" > "$OUTPUT"
else
  printf '%s\n' "$payload"
fi
