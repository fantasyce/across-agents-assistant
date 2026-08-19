#!/bin/bash

set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUTPUT_DIR=${1:-}
BUILD_PYTHON=${ACROSS_BUILD_PYTHON:-}
BUILD_CACHE=${ACROSS_BUILD_CACHE:-$HOME/Library/Caches/AcrossAgentsAssistantBuild}
CONTEXT_LOCAL_SOURCE=${ACROSS_BUILD_CONTEXT_SOURCE_ROOT:-}
AUTOPILOT_LOCAL_SOURCE=${ACROSS_BUILD_AUTOPILOT_SOURCE_ROOT:-}
ORCHESTRATOR_LOCAL_SOURCE=${ACROSS_BUILD_ORCHESTRATOR_SOURCE_ROOT:-}

NODE_VERSION="22.17.1"
CONTEXT_VERSION="0.11.0"
CONTEXT_COMMIT="24768104d613c52e081b3ca7a9d5b3dbd6886b72"
CONTEXT_SHA256="7420b75e28adf1da130593dc217d4bd8d2368d6ebe6cd55c7fca43a5161ad974"
AUTOPILOT_VERSION="0.5.2"
AUTOPILOT_COMMIT="b11b6abbd55831a65f18bb6a4fbab5d7dab9bd8e"
AUTOPILOT_SHA256="22d8446afff0aafc797d7ccf573925d5a5f53a5f6a8a45d916ce9967ab79a5ea"
ORCHESTRATOR_VERSION="0.10.5"
ORCHESTRATOR_COMMIT="605a6157a1871e5fd7e35d827c0f51903430761e"
ORCHESTRATOR_SHA256="95323ac89d81cee88a8523232a8b0061a37b3ba4e71802622b16c5411d287877"
CONTEXT_SOURCE_KIND="released-pin"
AUTOPILOT_SOURCE_KIND="released-pin"
ORCHESTRATOR_SOURCE_KIND="released-pin"
CONTEXT_SOURCE_DIRTY=false
AUTOPILOT_SOURCE_DIRTY=false
ORCHESTRATOR_SOURCE_DIRTY=false

if [[ -n "$CONTEXT_LOCAL_SOURCE" ]]; then
    CONTEXT_LOCAL_SOURCE=$(cd "$CONTEXT_LOCAL_SOURCE" && pwd)
    if [[ ! -f "$CONTEXT_LOCAL_SOURCE/package.json" || ! -d "$CONTEXT_LOCAL_SOURCE/src" ]]; then
        echo "ERROR: ACROSS_BUILD_CONTEXT_SOURCE_ROOT is not an Across Context checkout." >&2
        exit 1
    fi
    CONTEXT_VERSION=$(sed -n 's/^[[:space:]]*"version": "\([^"]*\)".*/\1/p' "$CONTEXT_LOCAL_SOURCE/package.json" | head -1)
    CONTEXT_COMMIT=$(git -C "$CONTEXT_LOCAL_SOURCE" rev-parse HEAD)
    CONTEXT_SOURCE_KIND="local-candidate"
    if [[ -n "$(git -C "$CONTEXT_LOCAL_SOURCE" status --porcelain --untracked-files=all)" ]]; then
        CONTEXT_SOURCE_DIRTY=true
    fi
fi

if [[ -n "$AUTOPILOT_LOCAL_SOURCE" ]]; then
    AUTOPILOT_LOCAL_SOURCE=$(cd "$AUTOPILOT_LOCAL_SOURCE" && pwd)
    if [[ ! -f "$AUTOPILOT_LOCAL_SOURCE/package.json" || ! -d "$AUTOPILOT_LOCAL_SOURCE/src" ]]; then
        echo "ERROR: ACROSS_BUILD_AUTOPILOT_SOURCE_ROOT is not an Across Autopilot checkout." >&2
        exit 1
    fi
    AUTOPILOT_VERSION=$(sed -n 's/^[[:space:]]*"version": "\([^"]*\)".*/\1/p' "$AUTOPILOT_LOCAL_SOURCE/package.json" | head -1)
    AUTOPILOT_COMMIT=$(git -C "$AUTOPILOT_LOCAL_SOURCE" rev-parse HEAD)
    AUTOPILOT_SOURCE_KIND="local-candidate"
    if [[ -n "$(git -C "$AUTOPILOT_LOCAL_SOURCE" status --porcelain --untracked-files=all)" ]]; then
        AUTOPILOT_SOURCE_DIRTY=true
    fi
fi

if [[ -n "$ORCHESTRATOR_LOCAL_SOURCE" ]]; then
    ORCHESTRATOR_LOCAL_SOURCE=$(cd "$ORCHESTRATOR_LOCAL_SOURCE" && pwd)
    if [[ ! -f "$ORCHESTRATOR_LOCAL_SOURCE/pyproject.toml" || ! -d "$ORCHESTRATOR_LOCAL_SOURCE/src/across_orchestrator" ]]; then
        echo "ERROR: ACROSS_BUILD_ORCHESTRATOR_SOURCE_ROOT is not an Across Orchestrator checkout." >&2
        exit 1
    fi
    ORCHESTRATOR_VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' "$ORCHESTRATOR_LOCAL_SOURCE/pyproject.toml" | head -1)
    ORCHESTRATOR_COMMIT=$(git -C "$ORCHESTRATOR_LOCAL_SOURCE" rev-parse HEAD)
    ORCHESTRATOR_SOURCE_KIND="local-candidate"
    if [[ -n "$(git -C "$ORCHESTRATOR_LOCAL_SOURCE" status --porcelain --untracked-files=all)" ]]; then
        ORCHESTRATOR_SOURCE_DIRTY=true
    fi
fi

if [[ -z "$OUTPUT_DIR" ]]; then
    echo "Usage: $0 OUTPUT_DIR" >&2
    exit 2
fi
if [[ -z "$BUILD_PYTHON" || ! -x "$BUILD_PYTHON" ]]; then
    echo "ERROR: ACROSS_BUILD_PYTHON must point to the Python used for the app build." >&2
    exit 1
fi

case "$(uname -m)" in
    arm64)
        NODE_ARCH="arm64"
        NODE_SHA256="a983f4f2a7b71512b78d7935b9ccf6b72120a255810070afd635c4146bca7b31"
        NODE_BINARY_SOURCE_SHA256="68353134fb956407a2114dbc0912d27180550c5f2424ce66a404099147f3d749"
        ;;
    x86_64)
        NODE_ARCH="x64"
        NODE_SHA256="b925103150fac0d23a44a45b2d88a01b73e5fff101e5dcfbae98d32c08d4bee3"
        NODE_BINARY_SOURCE_SHA256="264aec9d21f0ccbd9bbac700a98029ed57b7f3d0433352465ba069d7911bb977"
        ;;
    *)
        echo "ERROR: Unsupported macOS architecture: $(uname -m)" >&2
        exit 1
        ;;
esac

download_verified() {
    local url="$1"
    local destination="$2"
    local expected_sha256="$3"
    local actual_sha256=""
    mkdir -p "$(dirname "$destination")"
    if [[ -f "$destination" ]]; then
        actual_sha256=$(shasum -a 256 "$destination" | awk '{print $1}')
    fi
    if [[ "$actual_sha256" != "$expected_sha256" ]]; then
        local temporary="$destination.tmp.$$"
        rm -f "$temporary"
        curl --fail --location --silent --show-error "$url" -o "$temporary"
        actual_sha256=$(shasum -a 256 "$temporary" | awk '{print $1}')
        if [[ "$actual_sha256" != "$expected_sha256" ]]; then
            rm -f "$temporary"
            echo "ERROR: Checksum verification failed for $url" >&2
            exit 1
        fi
        mv "$temporary" "$destination"
    fi
}

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/packages" "$OUTPUT_DIR/runtimes"
mkdir -p "$BUILD_CACHE/downloads" "$BUILD_CACHE/extracted"

echo "Preparing bundled Node runtime $NODE_VERSION ($NODE_ARCH)..."
NODE_ARCHIVE_NAME="node-v$NODE_VERSION-darwin-$NODE_ARCH.tar.gz"
NODE_ARCHIVE="$BUILD_CACHE/downloads/$NODE_ARCHIVE_NAME"
download_verified \
    "https://nodejs.org/dist/v$NODE_VERSION/$NODE_ARCHIVE_NAME" \
    "$NODE_ARCHIVE" \
    "$NODE_SHA256"
NODE_EXTRACTED="$BUILD_CACHE/extracted/node-v$NODE_VERSION-darwin-$NODE_ARCH"
NODE_EXTRACTED_SHA256=""
if [[ -x "$NODE_EXTRACTED/bin/node" ]]; then
    NODE_EXTRACTED_SHA256=$(shasum -a 256 "$NODE_EXTRACTED/bin/node" | awk '{print $1}')
fi
if [[ "$NODE_EXTRACTED_SHA256" != "$NODE_BINARY_SOURCE_SHA256" ]]; then
    rm -rf "$NODE_EXTRACTED"
    tar -xzf "$NODE_ARCHIVE" -C "$BUILD_CACHE/extracted"
fi
NODE_EXTRACTED_SHA256=$(shasum -a 256 "$NODE_EXTRACTED/bin/node" | awk '{print $1}')
if [[ "$NODE_EXTRACTED_SHA256" != "$NODE_BINARY_SOURCE_SHA256" ]]; then
    echo "ERROR: Extracted Node runtime checksum verification failed." >&2
    exit 1
fi
NODE_RUNTIME_DIR="$OUTPUT_DIR/runtimes/node-$NODE_VERSION"
mkdir -p "$NODE_RUNTIME_DIR/bin"
cp "$NODE_EXTRACTED/bin/node" "$NODE_RUNTIME_DIR/bin/node"
chmod +x "$NODE_RUNTIME_DIR/bin/node"
cp "$NODE_EXTRACTED/LICENSE" "$NODE_RUNTIME_DIR/LICENSE"
NODE_BINARY_SHA256=$(shasum -a 256 "$NODE_RUNTIME_DIR/bin/node" | awk '{print $1}')

echo "Preparing pinned plugin source archives..."
CONTEXT_ARCHIVE="$BUILD_CACHE/downloads/across-context-$CONTEXT_VERSION.tar.gz"
AUTOPILOT_ARCHIVE="$BUILD_CACHE/downloads/across-autopilot-$AUTOPILOT_VERSION.tar.gz"
ORCHESTRATOR_ARCHIVE="$BUILD_CACHE/downloads/across-orchestrator-$ORCHESTRATOR_VERSION.tar.gz"
if [[ -n "$CONTEXT_LOCAL_SOURCE" ]]; then
    rm -f "$CONTEXT_ARCHIVE"
    "$BUILD_PYTHON" "$PROJECT_ROOT/scripts/create_deterministic_source_archive.py" \
        --source "$CONTEXT_LOCAL_SOURCE" \
        --output "$CONTEXT_ARCHIVE" \
        --exclude '.git' \
        --exclude 'node_modules' \
        --exclude 'build' \
        --exclude 'dist'
    CONTEXT_SHA256=$(shasum -a 256 "$CONTEXT_ARCHIVE" | awk '{print $1}')
else
    "$BUILD_PYTHON" "$PROJECT_ROOT/scripts/create_pinned_source_archive.py" \
        --repository "https://github.com/fantasyce/across-context.git" \
        --commit "$CONTEXT_COMMIT" \
        --output "$CONTEXT_ARCHIVE" \
        --archive-root across-context \
        --expected-sha256 "$CONTEXT_SHA256" \
        --exclude .git --exclude node_modules --exclude build --exclude dist
fi
if [[ -n "$AUTOPILOT_LOCAL_SOURCE" ]]; then
    rm -f "$AUTOPILOT_ARCHIVE"
    "$BUILD_PYTHON" "$PROJECT_ROOT/scripts/create_deterministic_source_archive.py" \
        --source "$AUTOPILOT_LOCAL_SOURCE" \
        --output "$AUTOPILOT_ARCHIVE" \
        --exclude '.git' \
        --exclude 'node_modules' \
        --exclude 'build' \
        --exclude 'dist'
    AUTOPILOT_SHA256=$(shasum -a 256 "$AUTOPILOT_ARCHIVE" | awk '{print $1}')
else
    "$BUILD_PYTHON" "$PROJECT_ROOT/scripts/create_pinned_source_archive.py" \
        --repository "https://github.com/fantasyce/across-autopilot.git" \
        --commit "$AUTOPILOT_COMMIT" \
        --output "$AUTOPILOT_ARCHIVE" \
        --archive-root across-autopilot \
        --expected-sha256 "$AUTOPILOT_SHA256" \
        --exclude .git --exclude node_modules --exclude build --exclude dist
fi
if [[ -n "$ORCHESTRATOR_LOCAL_SOURCE" ]]; then
    rm -f "$ORCHESTRATOR_ARCHIVE"
    "$BUILD_PYTHON" "$PROJECT_ROOT/scripts/create_deterministic_source_archive.py" \
        --source "$ORCHESTRATOR_LOCAL_SOURCE" \
        --output "$ORCHESTRATOR_ARCHIVE" \
        --exclude '.git' \
        --exclude '.venv' \
        --exclude 'build' \
        --exclude 'dist' \
        --exclude '__pycache__'
    ORCHESTRATOR_SHA256=$(shasum -a 256 "$ORCHESTRATOR_ARCHIVE" | awk '{print $1}')
else
    "$BUILD_PYTHON" "$PROJECT_ROOT/scripts/create_pinned_source_archive.py" \
        --repository "https://github.com/fantasyce/across-orchestrator.git" \
        --commit "$ORCHESTRATOR_COMMIT" \
        --output "$ORCHESTRATOR_ARCHIVE" \
        --archive-root across-orchestrator \
        --expected-sha256 "$ORCHESTRATOR_SHA256" \
        --exclude .git --exclude .venv --exclude build --exclude dist --exclude __pycache__
fi
cp "$CONTEXT_ARCHIVE" "$OUTPUT_DIR/packages/across-context-$CONTEXT_VERSION.tar.gz"
cp "$AUTOPILOT_ARCHIVE" "$OUTPUT_DIR/packages/across-autopilot-$AUTOPILOT_VERSION.tar.gz"
cp "$ORCHESTRATOR_ARCHIVE" "$OUTPUT_DIR/packages/across-orchestrator-$ORCHESTRATOR_VERSION.tar.gz"

echo "Building self-contained Across Orchestrator runtime..."
ORCHESTRATOR_SOURCE_ROOT="$BUILD_CACHE/extracted/across-orchestrator-$ORCHESTRATOR_COMMIT"
if [[ -n "$ORCHESTRATOR_LOCAL_SOURCE" ]]; then
    ORCHESTRATOR_SOURCE_ROOT="$ORCHESTRATOR_LOCAL_SOURCE"
else
    rm -rf "$ORCHESTRATOR_SOURCE_ROOT" "$BUILD_CACHE/extracted/orchestrator-staging"
    mkdir -p "$BUILD_CACHE/extracted/orchestrator-staging"
    tar -xzf "$ORCHESTRATOR_ARCHIVE" -C "$BUILD_CACHE/extracted/orchestrator-staging"
    EXTRACTED_ROOT=$(find "$BUILD_CACHE/extracted/orchestrator-staging" -mindepth 1 -maxdepth 1 -type d | head -1)
    if [[ -z "$EXTRACTED_ROOT" || ! -f "$EXTRACTED_ROOT/pyproject.toml" ]]; then
        echo "ERROR: Across Orchestrator source archive is invalid." >&2
        exit 1
    fi
    mv "$EXTRACTED_ROOT" "$ORCHESTRATOR_SOURCE_ROOT"
    rm -rf "$BUILD_CACHE/extracted/orchestrator-staging"
fi

ORCHESTRATOR_BUILD_ROOT="$PROJECT_ROOT/build/managed-plugin-orchestrator"
rm -rf "$ORCHESTRATOR_BUILD_ROOT"
mkdir -p "$ORCHESTRATOR_BUILD_ROOT/dist" "$ORCHESTRATOR_BUILD_ROOT/work" "$ORCHESTRATOR_BUILD_ROOT/spec"
# Install the producer-declared runtime dependencies into the isolated build
# interpreter before PyInstaller analyzes the local/released source. Worker
# modules are loaded lazily by CLI subcommands, so the host backend dependency
# set alone is not sufficient to produce a working listener binary.
"$BUILD_PYTHON" -m pip install --quiet --disable-pip-version-check "$ORCHESTRATOR_SOURCE_ROOT"
PYTHONPATH="$ORCHESTRATOR_SOURCE_ROOT/src" "$BUILD_PYTHON" - <<'PY'
import cryptography
import psutil
import across_orchestrator.worker_runtime
PY
# PyInstaller serializes hash-backed Python collections into the embedded PKG
# archive. Keep the hash seed and build epoch fixed so rebuilding the same
# Orchestrator source produces the same PKG hash, Mach-O UUID, and executable
# checksum. This prevents a same-version local candidate rebuild from looking
# like a tampered managed runtime.
PYTHONHASHSEED=1 SOURCE_DATE_EPOCH=0 PYTHONPATH= "$BUILD_PYTHON" -m PyInstaller \
    --onefile \
    --clean \
    --noconfirm \
    --name across-orchestrator \
    --distpath "$ORCHESTRATOR_BUILD_ROOT/dist" \
    --workpath "$ORCHESTRATOR_BUILD_ROOT/work" \
    --specpath "$ORCHESTRATOR_BUILD_ROOT/spec" \
    --paths "$ORCHESTRATOR_SOURCE_ROOT/src" \
    --collect-all across_orchestrator \
    "$PROJECT_ROOT/scripts/across_orchestrator_runtime_entry.py" >/dev/null

ORCHESTRATOR_RUNTIME_DIR="$OUTPUT_DIR/runtimes/orchestrator-$ORCHESTRATOR_VERSION"
mkdir -p "$ORCHESTRATOR_RUNTIME_DIR"
cp "$ORCHESTRATOR_BUILD_ROOT/dist/across-orchestrator" "$ORCHESTRATOR_RUNTIME_DIR/across-orchestrator"
chmod +x "$ORCHESTRATOR_RUNTIME_DIR/across-orchestrator"
cp "$ORCHESTRATOR_SOURCE_ROOT/LICENSE" "$ORCHESTRATOR_RUNTIME_DIR/LICENSE"
ORCHESTRATOR_BINARY_SHA256=$(shasum -a 256 "$ORCHESTRATOR_RUNTIME_DIR/across-orchestrator" | awk '{print $1}')

"$ORCHESTRATOR_RUNTIME_DIR/across-orchestrator" plugin-manifest --json >/dev/null
"$ORCHESTRATOR_RUNTIME_DIR/across-orchestrator" health --json >/dev/null
if ! "$ORCHESTRATOR_RUNTIME_DIR/across-orchestrator" serve --help 2>&1 | grep -q -- "--allow-client-project-roots"; then
    echo "ERROR: Bundled Across Orchestrator does not support the AAA client-project-root sidecar contract." >&2
    exit 1
fi
if ! "$ORCHESTRATOR_RUNTIME_DIR/across-orchestrator" worker-control-server --help 2>&1 | grep -q -- "--socket"; then
    echo "ERROR: Bundled Across Orchestrator does not expose the private Worker control server." >&2
    exit 1
fi
if ! "$ORCHESTRATOR_RUNTIME_DIR/across-orchestrator" worker-listener --help 2>&1 | grep -q -- "--model-gateway-url"; then
    echo "ERROR: Bundled Across Orchestrator does not expose the Worker listener contract." >&2
    exit 1
fi

cat > "$OUTPUT_DIR/manifest.json" <<JSON
{
  "schema_version": "across-managed-plugin-payloads/1.0",
  "platform": "macos",
  "architecture": "$(uname -m)",
  "runtimes": {
    "node": {
      "version": "$NODE_VERSION",
      "path": "runtimes/node-$NODE_VERSION",
      "executable": "bin/node",
      "sha256": "$NODE_BINARY_SHA256"
    }
  },
  "plugins": {
    "across-context": {
      "version": "$CONTEXT_VERSION",
      "commit": "$CONTEXT_COMMIT",
      "source_kind": "$CONTEXT_SOURCE_KIND",
      "source_dirty": $CONTEXT_SOURCE_DIRTY,
      "runtime": "node",
      "archive": "packages/across-context-$CONTEXT_VERSION.tar.gz",
      "sha256": "$CONTEXT_SHA256",
      "metadata": "package.json",
      "package_name": "@across/context",
      "entrypoint": "src/cli.js"
    },
    "across-orchestrator": {
      "version": "$ORCHESTRATOR_VERSION",
      "commit": "$ORCHESTRATOR_COMMIT",
      "source_kind": "$ORCHESTRATOR_SOURCE_KIND",
      "source_dirty": $ORCHESTRATOR_SOURCE_DIRTY,
      "runtime": "native",
      "executable": "runtimes/orchestrator-$ORCHESTRATOR_VERSION/across-orchestrator",
      "sha256": "$ORCHESTRATOR_BINARY_SHA256",
      "source_archive": "packages/across-orchestrator-$ORCHESTRATOR_VERSION.tar.gz",
      "source_sha256": "$ORCHESTRATOR_SHA256"
    },
    "across-autopilot": {
      "version": "$AUTOPILOT_VERSION",
      "commit": "$AUTOPILOT_COMMIT",
      "source_kind": "$AUTOPILOT_SOURCE_KIND",
      "source_dirty": $AUTOPILOT_SOURCE_DIRTY,
      "runtime": "node",
      "archive": "packages/across-autopilot-$AUTOPILOT_VERSION.tar.gz",
      "sha256": "$AUTOPILOT_SHA256",
      "metadata": "package.json",
      "package_name": "@across/autopilot",
      "entrypoint": "src/cli.js"
    }
  }
}
JSON

echo "Managed plugin payloads are ready at $OUTPUT_DIR"
