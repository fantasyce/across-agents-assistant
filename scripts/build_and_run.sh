#!/bin/bash

set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
APP_NAME="Across Agents Assistant"
APP_PATH="$PROJECT_ROOT/build/$APP_NAME.app"
INSTALL_PATH="/Applications/$APP_NAME.app"

# A formal local candidate must exercise the same current producer sources that
# the developer is validating. Public/reproducible builds still use the pinned
# released archives when build_app.sh is invoked directly; this convenience
# path deliberately prefers adjacent producer checkouts and records their
# provenance as local candidates in the bundled catalog.
if [[ -z "${ACROSS_BUILD_CONTEXT_SOURCE_ROOT:-}" && \
      -f "$PROJECT_ROOT/../across-context/package.json" && \
      -d "$PROJECT_ROOT/../across-context/src" ]]; then
    export ACROSS_BUILD_CONTEXT_SOURCE_ROOT="$PROJECT_ROOT/../across-context"
fi
if [[ -z "${ACROSS_BUILD_AUTOPILOT_SOURCE_ROOT:-}" && \
      -f "$PROJECT_ROOT/../across-autopilot/package.json" && \
      -d "$PROJECT_ROOT/../across-autopilot/src" ]]; then
    export ACROSS_BUILD_AUTOPILOT_SOURCE_ROOT="$PROJECT_ROOT/../across-autopilot"
fi
if [[ -z "${ACROSS_BUILD_ORCHESTRATOR_SOURCE_ROOT:-}" && \
      -f "$PROJECT_ROOT/../across-orchestrator/pyproject.toml" && \
      -d "$PROJECT_ROOT/../across-orchestrator/src/across_orchestrator" ]]; then
    export ACROSS_BUILD_ORCHESTRATOR_SOURCE_ROOT="$PROJECT_ROOT/../across-orchestrator"
fi

echo "=== 1. Stopping existing app and bundled sidecars ==="
descendant_pids() {
  local parent_pid="$1"
  local child_pid
  for child_pid in $(pgrep -P "$parent_pid" 2>/dev/null || true); do
    descendant_pids "$child_pid"
    echo "$child_pid"
  done
}

stop_matching() {
  local pattern="$1"
  local pids
  local all_pids
  local pid
  local remaining
  pids=$(pgrep -f "$pattern" 2>/dev/null || true)
  [ -z "$pids" ] && return 0
  all_pids=$(
    for pid in $pids; do
      descendant_pids "$pid"
    done
    printf '%s\n' $pids
  )
  all_pids=$(printf '%s\n' $all_pids | awk 'NF && !seen[$1]++')
  kill $all_pids 2>/dev/null || true
  # The packaged backend owns optional Worker and plugin children. Give its
  # lifespan shutdown enough time to drain them before using SIGKILL.
  for _ in $(seq 1 100); do
    remaining=""
    for pid in $all_pids; do
      if kill -0 "$pid" 2>/dev/null; then
        remaining="$remaining $pid"
      fi
    done
    [ -z "$remaining" ] && return 0
    sleep 0.1
  done
  kill -9 $remaining 2>/dev/null || true
}

stop_matching "/Applications/$APP_NAME.app/Contents/MacOS/AcrossAgentsAssistant"
stop_matching "$PROJECT_ROOT/build/$APP_NAME.app/Contents/MacOS/AcrossAgentsAssistant"
stop_matching "$APP_NAME.app/Contents/Resources/backend/backend"
# A previously force-killed backend may have left its Worker supervisor
# re-parented to launchd. Remove only the formal AAA control-server command;
# Codex/plugin MCP processes and remote Workers are deliberately out of scope.
stop_matching "worker-control-server --socket $HOME/.across/run/across-agents-assistant/worker-control.sock"
rm -f "$HOME/.across/run/across-agents-assistant/across-agents.lock" \
      "$HOME/.across/run/across-agents-assistant/across-agents.sock" \
      "$HOME/.across/run/across-agents-assistant/worker-control.sock"

echo "=== 2. Building app bundle ==="
"$PROJECT_ROOT/build_app.sh"

echo "=== 3. Installing local build to /Applications ==="
rm -rf "$INSTALL_PATH"
/usr/bin/ditto "$APP_PATH" "$INSTALL_PATH"
xattr -cr "$INSTALL_PATH" || true

echo "=== 4. Opening clean app ==="
open "$INSTALL_PATH"

echo "=== Done. Running $INSTALL_PATH ==="
