#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACROSS_HOME="${ACROSS_HOME:-"$HOME/.across"}"
SOURCE_ROOT="${ACROSS_LOOP_SOURCE_ROOT:-"$(cd "$ROOT_DIR/.." && pwd)"}"
DEST_ROOT="${ACROSS_AUTOPILOT_SOURCE_MIRRORS_DIR:-"$ACROSS_HOME/data/across-autopilot/source-mirrors"}"

REPOS=(
  "across-agents-assistant"
  "across-orchestrator"
  "across-context"
  "across-autopilot"
)

repo_source() {
  local repo="$1"
  local env_name
  env_name="$(printf 'ACROSS_%s_SOURCE_INPUT' "$repo" | sed 's/^ACROSS_across-/ACROSS_/' | tr '[:lower:]-' '[:upper:]_')"
  local value="${!env_name:-}"
  if [[ -n "$value" ]]; then
    printf '%s\n' "$value"
  else
    printf '%s/%s\n' "$SOURCE_ROOT" "$repo"
  fi
}

copy_git_snapshot() {
  local repo="$1"
  local source="$2"
  local target="$3"
  local tmp="${target}.tmp.$$"

  if [[ ! -d "$source/.git" ]]; then
    printf 'Source repo is missing or not a git checkout: %s\n' "$source" >&2
    return 1
  fi

  rm -rf "$tmp"
  mkdir -p "$tmp"

  while IFS= read -r -d '' rel; do
    case "$rel" in
      ""|/*|*"/../"*|../*|*".." )
        continue
        ;;
    esac
    if [[ ! -f "$source/$rel" ]]; then
      continue
    fi
    mkdir -p "$tmp/$(dirname "$rel")"
    cp -p "$source/$rel" "$tmp/$rel"
  done < <(git -C "$source" ls-files -z --cached --others --exclude-standard)

  git -C "$tmp" init -q
  git -C "$tmp" add .
  if ! git -C "$tmp" diff --cached --quiet; then
    git -C "$tmp" \
      -c user.name="Across Source Mirror" \
      -c user.email="source-mirror@example.invalid" \
      commit -q -m "source mirror for $repo"
  fi

  rm -rf "$target"
  mkdir -p "$(dirname "$target")"
  mv "$tmp" "$target"
}

mkdir -p "$DEST_ROOT"

for repo in "${REPOS[@]}"; do
  source="$(repo_source "$repo")"
  target="$DEST_ROOT/$repo"
  printf 'Mirroring %s\n  source: %s\n  target: %s\n' "$repo" "$source" "$target"
  copy_git_snapshot "$repo" "$source" "$target"
done

cat > "$DEST_ROOT/manifest.json" <<JSON
{
  "schema_version": "across-source-mirrors/1.0",
  "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "source_root": "$SOURCE_ROOT",
  "dest_root": "$DEST_ROOT",
  "repos": [
    "across-agents-assistant",
    "across-orchestrator",
    "across-context",
    "across-autopilot"
  ]
}
JSON

printf 'Source mirrors ready: %s\n' "$DEST_ROOT"
