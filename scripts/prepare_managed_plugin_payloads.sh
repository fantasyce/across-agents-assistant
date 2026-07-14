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
CONTEXT_VERSION="0.9.0"
CONTEXT_COMMIT="938c70b51ce52975bb385b358f5d6415d8aa6542"
CONTEXT_SHA256="55861128311ef9b602e2bdafb300962f2cf6776d5242cccb5262e87a01a8a9c7"
AUTOPILOT_VERSION="0.3.0"
AUTOPILOT_COMMIT="dfcd681f35feaec4b668adea565dcff3f723cc4f"
AUTOPILOT_SHA256="f3db980d9ea2a9fe9e3d94525e70499787655124227ffad985d9dfae628f7c51"
ORCHESTRATOR_VERSION="0.8.0"
ORCHESTRATOR_COMMIT="c416ae75c112c4268ec01c595ced580f6557a90a"
ORCHESTRATOR_SHA256="a54b338a0d923084ca70d5f40ea96e9258a3712ca34be0b533c1356a571b58f5"

if [[ -n "$CONTEXT_LOCAL_SOURCE" ]]; then
    CONTEXT_LOCAL_SOURCE=$(cd "$CONTEXT_LOCAL_SOURCE" && pwd)
    if [[ ! -f "$CONTEXT_LOCAL_SOURCE/package.json" || ! -d "$CONTEXT_LOCAL_SOURCE/src" ]]; then
        echo "ERROR: ACROSS_BUILD_CONTEXT_SOURCE_ROOT is not an Across Context checkout." >&2
        exit 1
    fi
    CONTEXT_VERSION=$(sed -n 's/^[[:space:]]*"version": "\([^"]*\)".*/\1/p' "$CONTEXT_LOCAL_SOURCE/package.json" | head -1)
    CONTEXT_COMMIT=$(git -C "$CONTEXT_LOCAL_SOURCE" rev-parse HEAD)
fi

if [[ -n "$AUTOPILOT_LOCAL_SOURCE" ]]; then
    AUTOPILOT_LOCAL_SOURCE=$(cd "$AUTOPILOT_LOCAL_SOURCE" && pwd)
    if [[ ! -f "$AUTOPILOT_LOCAL_SOURCE/package.json" || ! -d "$AUTOPILOT_LOCAL_SOURCE/src" ]]; then
        echo "ERROR: ACROSS_BUILD_AUTOPILOT_SOURCE_ROOT is not an Across Autopilot checkout." >&2
        exit 1
    fi
    AUTOPILOT_VERSION=$(sed -n 's/^[[:space:]]*"version": "\([^"]*\)".*/\1/p' "$AUTOPILOT_LOCAL_SOURCE/package.json" | head -1)
    AUTOPILOT_COMMIT=$(git -C "$AUTOPILOT_LOCAL_SOURCE" rev-parse HEAD)
fi

if [[ -n "$ORCHESTRATOR_LOCAL_SOURCE" ]]; then
    ORCHESTRATOR_LOCAL_SOURCE=$(cd "$ORCHESTRATOR_LOCAL_SOURCE" && pwd)
    if [[ ! -f "$ORCHESTRATOR_LOCAL_SOURCE/pyproject.toml" || ! -d "$ORCHESTRATOR_LOCAL_SOURCE/src/across_orchestrator" ]]; then
        echo "ERROR: ACROSS_BUILD_ORCHESTRATOR_SOURCE_ROOT is not an Across Orchestrator checkout." >&2
        exit 1
    fi
    ORCHESTRATOR_VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' "$ORCHESTRATOR_LOCAL_SOURCE/pyproject.toml" | head -1)
    ORCHESTRATOR_COMMIT=$(git -C "$ORCHESTRATOR_LOCAL_SOURCE" rev-parse HEAD)
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
    COPYFILE_DISABLE=1 tar -czf "$CONTEXT_ARCHIVE" \
        --exclude='.git' \
        --exclude='node_modules' \
        --exclude='build' \
        --exclude='dist' \
        -C "$(dirname "$CONTEXT_LOCAL_SOURCE")" \
        "$(basename "$CONTEXT_LOCAL_SOURCE")"
    CONTEXT_SHA256=$(shasum -a 256 "$CONTEXT_ARCHIVE" | awk '{print $1}')
else
    download_verified \
        "https://codeload.github.com/fantasyce/across-context/tar.gz/$CONTEXT_COMMIT" \
        "$CONTEXT_ARCHIVE" \
        "$CONTEXT_SHA256"
fi
if [[ -n "$AUTOPILOT_LOCAL_SOURCE" ]]; then
    rm -f "$AUTOPILOT_ARCHIVE"
    COPYFILE_DISABLE=1 tar -czf "$AUTOPILOT_ARCHIVE" \
        --exclude='.git' \
        --exclude='node_modules' \
        --exclude='build' \
        --exclude='dist' \
        -C "$(dirname "$AUTOPILOT_LOCAL_SOURCE")" \
        "$(basename "$AUTOPILOT_LOCAL_SOURCE")"
    AUTOPILOT_SHA256=$(shasum -a 256 "$AUTOPILOT_ARCHIVE" | awk '{print $1}')
else
    download_verified \
        "https://codeload.github.com/fantasyce/across-autopilot/tar.gz/$AUTOPILOT_COMMIT" \
        "$AUTOPILOT_ARCHIVE" \
        "$AUTOPILOT_SHA256"
fi
if [[ -n "$ORCHESTRATOR_LOCAL_SOURCE" ]]; then
    rm -f "$ORCHESTRATOR_ARCHIVE"
    COPYFILE_DISABLE=1 tar -czf "$ORCHESTRATOR_ARCHIVE" \
        --exclude='.git' \
        --exclude='.venv' \
        --exclude='build' \
        --exclude='dist' \
        --exclude='__pycache__' \
        -C "$(dirname "$ORCHESTRATOR_LOCAL_SOURCE")" \
        "$(basename "$ORCHESTRATOR_LOCAL_SOURCE")"
    ORCHESTRATOR_SHA256=$(shasum -a 256 "$ORCHESTRATOR_ARCHIVE" | awk '{print $1}')
else
    download_verified \
        "https://codeload.github.com/fantasyce/across-orchestrator/tar.gz/$ORCHESTRATOR_COMMIT" \
        "$ORCHESTRATOR_ARCHIVE" \
        "$ORCHESTRATOR_SHA256"
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
PYTHONPATH= "$BUILD_PYTHON" -m PyInstaller \
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
      "runtime": "native",
      "executable": "runtimes/orchestrator-$ORCHESTRATOR_VERSION/across-orchestrator",
      "sha256": "$ORCHESTRATOR_BINARY_SHA256",
      "source_archive": "packages/across-orchestrator-$ORCHESTRATOR_VERSION.tar.gz",
      "source_sha256": "$ORCHESTRATOR_SHA256"
    },
    "across-autopilot": {
      "version": "$AUTOPILOT_VERSION",
      "commit": "$AUTOPILOT_COMMIT",
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
