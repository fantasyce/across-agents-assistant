#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEVELOPER_DIR="$(/usr/bin/xcode-select -p)"
TESTING_FRAMEWORKS="${DEVELOPER_DIR}/Library/Developer/Frameworks"

swift_test_args=(
  test
  --package-path "${ROOT_DIR}/macOS-Client"
  --enable-swift-testing
)

# Command Line Tools ships Swift Testing outside the compiler's default import
# path. Pass the framework path to every generated target so SwiftPM's runner
# can discover and execute @Test cases instead of merely compiling them.
if [[ -d "${TESTING_FRAMEWORKS}/Testing.framework" ]]; then
  swift_test_args+=(
    -Xswiftc -F
    -Xswiftc "${TESTING_FRAMEWORKS}"
  )
fi

/usr/bin/xcrun swift "${swift_test_args[@]}" "$@"
