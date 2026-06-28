#!/bin/bash

set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
APP_NAME="Across Agents Assistant"
APP_PATH="$PROJECT_ROOT/build/$APP_NAME.app"
INSTALL_PATH="/Applications/$APP_NAME.app"

echo "=== 1. Stopping existing app and bundled sidecars ==="
stop_matching() {
  local pattern="$1"
  local pids
  pids=$(pgrep -f "$pattern" 2>/dev/null || true)
  [ -z "$pids" ] && return 0
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 20); do
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    [ -z "$pids" ] && return 0
    sleep 0.1
  done
  kill -9 $pids 2>/dev/null || true
}

stop_matching "/Applications/$APP_NAME.app/Contents/MacOS/AcrossAgentsAssistant"
stop_matching "$PROJECT_ROOT/build/$APP_NAME.app/Contents/MacOS/AcrossAgentsAssistant"
stop_matching "$APP_NAME.app/Contents/Resources/backend/backend"
rm -f "$HOME/.across/run/across-agents-assistant/across-agents.lock" \
      "$HOME/.across/run/across-agents-assistant/across-agents.sock"

echo "=== 2. Building app bundle ==="
"$PROJECT_ROOT/build_app.sh"

echo "=== 3. Installing local build to /Applications ==="
rm -rf "$INSTALL_PATH"
/usr/bin/ditto "$APP_PATH" "$INSTALL_PATH"
xattr -cr "$INSTALL_PATH" || true

echo "=== 4. Opening clean app ==="
open "$INSTALL_PATH"

echo "=== Done. Running $INSTALL_PATH ==="
