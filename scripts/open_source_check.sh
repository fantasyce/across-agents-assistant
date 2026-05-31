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
SENSITIVE_PATTERN='(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY=|ANTHROPIC_API_KEY=|DEEPSEEK_API_KEY=|MINIMAX_API_KEY=|/Users/fanhcy|BEGIN (RSA|OPENSSH|PRIVATE) KEY|Apple Developer|com\.apple\.developer\.team-identifier'
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

echo "== shell syntax =="
bash -n build_app.sh

echo "Open-source check passed."
