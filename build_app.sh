#!/bin/bash

# Exit on any error
set -e

PROJECT_ROOT=$(cd "$(dirname "$0")" && pwd)
APP_NAME="Across Agents Assistant"
EXECUTABLE_NAME="AcrossAgentsAssistant"
BUILD_DIR="$PROJECT_ROOT/build"
APP_DIR="$BUILD_DIR/$APP_NAME.app"
APP_VERSION="${APP_VERSION:-$(sed -n 's/^version = "\(.*\)"/\1/p' "$PROJECT_ROOT/backend/pyproject.toml" | head -1)}"

if [ -z "$APP_VERSION" ]; then
    echo "ERROR: Could not resolve app version from backend/pyproject.toml"
    exit 1
fi

"$PROJECT_ROOT/scripts/build_app_icon.sh" >/dev/null

echo "=== 1. Cleaning up previous builds ==="
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# PyInstaller imports application modules while discovering dependencies. Keep
# every build-time side effect away from the installed App's real ~/.across
# state, even when an imported module initializes persistence at import time.
BUILD_RUNTIME_DIR="$BUILD_DIR/build-runtime"
export ACROSS_HOME="$BUILD_RUNTIME_DIR/across-home"
export ACROSS_AGENTS_HOME="$BUILD_RUNTIME_DIR/across-agents-home"
export ACROSS_CONTEXT_HOME="$BUILD_RUNTIME_DIR/across-context-home"
export ACROSS_AUTOPILOT_HOME="$BUILD_RUNTIME_DIR/across-autopilot-home"
export ACROSS_ORCHESTRATOR_HOME="$BUILD_RUNTIME_DIR/across-orchestrator-home"
export ACROSS_AGENTS_DEVELOPER_MODE=1
export ACROSS_ORCHESTRATOR_DEVELOPER_MODE=1
mkdir -p \
    "$ACROSS_HOME" \
    "$ACROSS_AGENTS_HOME" \
    "$ACROSS_CONTEXT_HOME" \
    "$ACROSS_AUTOPILOT_HOME" \
    "$ACROSS_ORCHESTRATOR_HOME"
cleanup_build_runtime() {
    rm -rf "$BUILD_RUNTIME_DIR"
}
trap cleanup_build_runtime EXIT
echo "Build-time runtime state: $BUILD_RUNTIME_DIR"

echo "=== 2. Building Python Backend ==="
cd "$PROJECT_ROOT/backend"

# --- Virtual Environment Setup ---
# Always use a virtual environment to avoid system Python restrictions (PEP 668)
# and ensure consistent dependency management.
# Find Python 3.10+ (required by mcp and other dependencies)
PYTHON_3_10=$(which python3.10 2>/dev/null || which python3.11 2>/dev/null || which python3.12 2>/dev/null)
if [ -z "$PYTHON_3_10" ]; then
    echo "ERROR: Python 3.10+ is required but not found. Please install Python 3.10 or later."
    exit 1
fi
echo "Using Python: $PYTHON_3_10"

VENV_DIR="$PROJECT_ROOT/backend/.venv"
if [ -d "$VENV_DIR" ] && {
    [ ! -f "$VENV_DIR/bin/activate" ] ||
    [ ! -x "$VENV_DIR/bin/python" ] ||
    ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1
}; then
    echo "Virtual environment is incomplete; recreating $VENV_DIR..."
    rm -rf "$VENV_DIR"
fi
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR..."
    "$PYTHON_3_10" -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"
PYTHON_BIN="$VENV_DIR/bin/python"

# Upgrade pip to avoid compatibility issues
echo "Upgrading pip..."
$PYTHON_BIN -m pip install --upgrade pip --quiet

# Install/upgrade PyInstaller (required for building)
echo "Installing PyInstaller..."
$PYTHON_BIN -m pip install pyinstaller --quiet

# Keep PyInstaller and cache writes inside the repository to avoid
# permission issues in sandboxed or restricted environments.
export PYINSTALLER_CONFIG_DIR="$PROJECT_ROOT/build/pyinstaller"
export XDG_CACHE_HOME="$PROJECT_ROOT/build/cache"
mkdir -p "$PYINSTALLER_CONFIG_DIR" "$XDG_CACHE_HOME"

BACKEND_BUNDLE_MODE="${BACKEND_BUNDLE_MODE:-onedir}"
case "$BACKEND_BUNDLE_MODE" in
    onefile)
        PYINSTALLER_BUNDLE_FLAG="--onefile"
        ;;
    onedir)
        PYINSTALLER_BUNDLE_FLAG="--onedir"
        ;;
    *)
        echo "ERROR: BACKEND_BUNDLE_MODE must be 'onefile' or 'onedir' (got '$BACKEND_BUNDLE_MODE')."
        exit 1
        ;;
esac
echo "Backend bundle mode: $BACKEND_BUNDLE_MODE"

# Install project dependencies one by one to avoid a single failure blocking everything.
# build_app.sh runs from backend/, while the dependency manifest lives there.
# Keep this path explicit so candidate workspaces do not accidentally read a
# missing repository-root requirements.txt and produce a broken PyInstaller app.
echo "Installing Python dependencies..."
REQUIREMENTS_FILE="$PROJECT_ROOT/backend/requirements.txt"
while IFS= read -r line || [[ -n "$line" ]]; do
    # Skip empty lines and comments
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    pkg=$(echo "$line" | sed 's/[[:space:]]*#.*//')
    [[ -z "$pkg" ]] && continue
    echo "  Installing $pkg..."
    $PYTHON_BIN -m pip install "$pkg" --quiet 2>/dev/null || {
        echo "    Warning: Failed to install $pkg (may be platform-specific or optional)"
    }
done < "$REQUIREMENTS_FILE"

echo "Installing critical backend runtime dependencies..."
$PYTHON_BIN -m pip install --quiet \
    "anyio>=4.0.0" \
    "fastapi>=0.138.2" \
    "httpx>=0.28.1" \
    "mcp[cli]>=1.28.1" \
    "pydantic>=2.9.0" \
    "starlette>=0.46.0" \
    "uvicorn>=0.49.0"

echo "Verifying critical backend runtime modules..."
PYTHONPATH= "$PYTHON_BIN" - <<'PY'
import importlib
import sys

required = [
    "anyio",
    "fastapi",
    "httpx",
    "mcp",
    "pydantic",
    "starlette",
    "typer",
    "uvicorn",
]
missing = []
for name in required:
    try:
        importlib.import_module(name)
    except Exception as exc:
        missing.append(f"{name}: {exc}")
if missing:
    print("ERROR: critical backend dependencies are missing:", file=sys.stderr)
    for item in missing:
        print(f"  - {item}", file=sys.stderr)
    sys.exit(1)
PY

# Keep generated bytecode out of --collect-all across_agents_assistant.
find src/across_agents_assistant -type d -name "__pycache__" -prune -exec rm -rf {} +
find src/across_agents_assistant -type f -name "*.pyc" -delete

# --- PyInstaller Build ---
# Optimized flags:
# - Remove --collect-all for non-package modules (openai, anthropic, local, appdirs, etc.)
#   These are regular packages, not data-heavy; PyInstaller auto-discovers them.
# - Remove duplicate --collect-all entries (fastapi, anyio appeared twice)
# - Add --exclude-module for broken/unnecessary modules (tkinter, setuptools.tests)
echo "Running PyInstaller..."
PYTHONPATH=src $PYTHON_BIN -m PyInstaller --name "backend" "$PYINSTALLER_BUNDLE_FLAG" --clean --noconfirm \
    --collect-all mcp \
    --collect-all uvicorn \
    --collect-all starlette \
    --collect-all fastapi \
    --collect-all httpx \
    --collect-all httpcore \
    --collect-all anyio \
    --collect-all h11 \
    --collect-all pydantic \
    --collect-all sse_starlette \
    --collect-all faster_whisper \
    --collect-all ctranslate2 \
    --collect-all av \
    --collect-all numpy \
    --collect-all across_agents_assistant \
    --collect-all click \
    --collect-all idna \
    --collect-all certifi \
    --hidden-import AppKit \
    --hidden-import Foundation \
    --hidden-import Vision \
    --hidden-import Quartz \
    --exclude-module tkinter \
    --exclude-module setuptools.tests \
    --exclude-module _tkinter \
    main.py

echo "=== 2.5 Preparing Managed Plugin Payloads ==="
ACROSS_BUILD_PYTHON="$PYTHON_BIN" \
    "$PROJECT_ROOT/scripts/prepare_managed_plugin_payloads.sh" \
    "$BUILD_DIR/plugin-payloads"

echo "=== 3. Building macOS Client (Release) ==="
cd "$PROJECT_ROOT/macOS-Client"
swift build -c release --disable-sandbox --force-resolved-versions --skip-update

echo "=== 4. Creating App Bundle Structure ==="
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

echo "=== 5. Copying Executables and Resources ==="
# Copy Swift executable
cp "$PROJECT_ROOT/macOS-Client/.build/release/AcrossAgentsAssistantClient" "$APP_DIR/Contents/MacOS/$EXECUTABLE_NAME"

# Copy the backend in the selected PyInstaller shape. The app launcher supports
# either Resources/backend as an executable or Resources/backend/backend in a
# one-directory backend bundle.
if [ "$BACKEND_BUNDLE_MODE" = "onefile" ]; then
    cp "$PROJECT_ROOT/backend/dist/backend" "$APP_DIR/Contents/Resources/backend"
    chmod +x "$APP_DIR/Contents/Resources/backend"
else
    rm -rf "$APP_DIR/Contents/Resources/backend"
    /usr/bin/ditto "$PROJECT_ROOT/backend/dist/backend" "$APP_DIR/Contents/Resources/backend"
    chmod +x "$APP_DIR/Contents/Resources/backend/backend"
fi

# Copy SwiftPM resource bundle into the conventional app resources directory.
# App code resolves this bundle from Bundle.main.resourceURL so normal macOS
# code signing does not see unsealed content at the .app bundle root.
RESOURCE_BUNDLE_NAME="AcrossAgentsAssistant_AcrossAgentsAssistantClient.bundle"
RESOURCE_BUNDLE="$PROJECT_ROOT/macOS-Client/.build/release/$RESOURCE_BUNDLE_NAME"
if [ -d "$RESOURCE_BUNDLE" ]; then
    rm -rf "$APP_DIR/Contents/Resources/$RESOURCE_BUNDLE_NAME"
    cp -R "$RESOURCE_BUNDLE" "$APP_DIR/Contents/Resources/"
else
    echo "Error: SwiftPM resource bundle not found: $RESOURCE_BUNDLE" >&2
    exit 1
fi

# Copy App Icon (from backend assets)
if [ -f "$PROJECT_ROOT/backend/assets/app_icon.icns" ]; then
    cp "$PROJECT_ROOT/backend/assets/app_icon.icns" "$APP_DIR/Contents/Resources/app_icon.icns"
fi

# The Plugin Center installs fixed, checksummed producer releases without
# depending on npm, Git, Node, or Python being preinstalled on the user's Mac.
if [ -d "$BUILD_DIR/plugin-payloads" ]; then
    rm -rf "$APP_DIR/Contents/Resources/plugin-payloads"
    /usr/bin/ditto "$BUILD_DIR/plugin-payloads" "$APP_DIR/Contents/Resources/plugin-payloads"
else
    echo "Error: managed plugin payloads were not produced." >&2
    exit 1
fi

# Copy host-side validation helpers used by packaged Loop Engineering runs.
mkdir -p "$APP_DIR/Contents/Resources/scripts"
cp "$PROJECT_ROOT/scripts/candidate_app_lifecycle.sh" "$APP_DIR/Contents/Resources/scripts/candidate_app_lifecycle.sh"
chmod +x "$APP_DIR/Contents/Resources/scripts/candidate_app_lifecycle.sh"

echo "=== 6. Generating Info.plist ==="
cat <<PLIST > "$APP_DIR/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>$EXECUTABLE_NAME</string>
    <key>CFBundleIconFile</key>
    <string>app_icon</string>
    <key>CFBundleIdentifier</key>
    <string>app.acrossagents.assistant</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleVersion</key>
    <string>$APP_VERSION</string>
    <key>CFBundleShortVersionString</key>
    <string>$APP_VERSION</string>
    <key>AcrossStudyProfileIsolationVersion</key>
    <integer>1</integer>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSQuitAlwaysKeepsWindows</key>
    <false/>
    <key>NSScreenCaptureUsageDescription</key>
    <string>Across Agents Assistant needs screen capture permission so AI can understand the current screen when you explicitly request it.</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>Across Agents Assistant uses the microphone only when you press Voice Input, so it can place your words into an editable draft.</string>
    <key>NSSystemExtensionUsageDescription</key>
    <string>Across Agents Assistant needs access to system extensions for local automation features.</string>
    <key>NSAppleEventsUsageDescription</key>
    <string>Across Agents Assistant needs permission to control apps such as Finder, Mail, and Notes when you request automation tasks.</string>
</dict>
</plist>
PLIST

echo "=== 6.5 Signing App ==="
echo "Clearing extended attributes..."
xattr -cr "$APP_DIR" || true

echo "Signing nested Mach-O files..."
SIGNING_IDENTITY="${SIGNING_IDENTITY:--}"
if [ "$SIGNING_IDENTITY" = "-" ]; then
    echo "Using ad-hoc signing for local validation."
else
    echo "Using signing identity: $SIGNING_IDENTITY"
fi

while IFS= read -r -d '' candidate; do
    if file "$candidate" | grep -q "Mach-O"; then
        codesign --force --sign "$SIGNING_IDENTITY" "$candidate"
    fi
done < <(find "$APP_DIR/Contents" -type f -print0)

# Code signing changes Mach-O bytes. Refresh the checksums used when copying
# the bundled Node and Orchestrator executables into ~/.across, then seal that
# manifest with the outer app signature.
PYTHONPATH= "$PYTHON_BIN" "$PROJECT_ROOT/scripts/update_managed_payload_hashes.py" \
    "$APP_DIR/Contents/Resources/plugin-payloads"

if [ "$SIGNING_IDENTITY" = "-" ]; then
    # Recent macOS builds can reject ad-hoc signed GUI apps when restricted
    # entitlements are attached. Keep local validation bundles entitlement-free;
    # real distribution signing should provide SIGNING_IDENTITY.
    codesign --force --sign "$SIGNING_IDENTITY" "$APP_DIR"
else
    codesign --force --options runtime \
        --entitlements "$PROJECT_ROOT/macOS-Client/Entitlements.entitlements" \
        --sign "$SIGNING_IDENTITY" "$APP_DIR"
fi

codesign --verify --deep --strict "$APP_DIR"

echo "=== Done! Local app bundle is ready at $APP_DIR ==="
echo "Note: This build is ad-hoc signed for local development and is not a distributable DMG."
echo "On newer macOS versions, LaunchServices may require a trusted SIGNING_IDENTITY to open packaged GUI apps."
