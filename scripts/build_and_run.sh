#!/bin/bash

set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
APP_NAME="Across Agents Assistant"
APP_PATH="$PROJECT_ROOT/build/$APP_NAME.app"
INSTALL_PATH="/Applications/$APP_NAME.app"

echo "=== 1. Stopping existing app and bundled sidecars ==="
pkill -f "/Applications/$APP_NAME.app/Contents/MacOS/AcrossAgentsAssistant" 2>/dev/null || true
pkill -f "$PROJECT_ROOT/build/$APP_NAME.app/Contents/MacOS/AcrossAgentsAssistant" 2>/dev/null || true
pkill -f "$APP_NAME.app/Contents/Resources/backend/backend" 2>/dev/null || true

echo "=== 2. Building app bundle ==="
"$PROJECT_ROOT/build_app.sh"

echo "=== 3. Installing local build to /Applications ==="
rm -rf "$INSTALL_PATH"
/usr/bin/ditto "$APP_PATH" "$INSTALL_PATH"
xattr -cr "$INSTALL_PATH" || true

echo "=== 4. Opening clean app ==="
open "$INSTALL_PATH"

echo "=== Done. Running $INSTALL_PATH ==="
