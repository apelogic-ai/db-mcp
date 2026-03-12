#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
UI_DIR="$REPO_ROOT/packages/ui"
DIST_DIR="$UI_DIR/dist"
STATIC_DIR="$REPO_ROOT/packages/core/src/db_mcp/static"

compute_ui_source_hash() {
  python3 - "$UI_DIR" <<'PY'
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ui_dir = Path(sys.argv[1]).resolve()
targets = [
    ui_dir / "src",
    ui_dir / "public",
    ui_dir / "next.config.js",
    ui_dir / "package.json",
    ui_dir / "postcss.config.js",
    ui_dir / "tailwind.config.js",
    ui_dir / "tsconfig.json",
]

hasher = hashlib.sha256()
for target in targets:
    if target.is_dir():
        paths = sorted(path for path in target.rglob("*") if path.is_file())
    elif target.is_file():
        paths = [target]
    else:
        continue

    for path in paths:
        rel = path.relative_to(ui_dir)
        hasher.update(str(rel).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")

print(hasher.hexdigest())
PY
}

BUILD_UI=0
BUILD_LABEL="manual"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)
      BUILD_UI=1
      shift
      ;;
    --label)
      BUILD_LABEL="${2:-}"
      if [[ -z "$BUILD_LABEL" ]]; then
        echo "Missing value for --label" >&2
        exit 1
      fi
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$BUILD_UI" -eq 1 ]]; then
  (
    cd "$UI_DIR"
    bun run build
  )
fi

if [[ ! -d "$DIST_DIR" ]]; then
  echo "UI build output missing at $DIST_DIR. Run scripts/stage_ui_static.sh --build or build packages/ui first." >&2
  exit 1
fi

rm -rf "$STATIC_DIR"
mkdir -p "$STATIC_DIR"
cp -R "$DIST_DIR"/. "$STATIC_DIR"/

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
GIT_STATUS="$(git -C "$REPO_ROOT" status --short 2>/dev/null || true)"
DIRTY=false
if [[ -n "$GIT_STATUS" ]]; then
  DIRTY=true
fi
BUILT_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
SOURCE_HASH="$(compute_ui_source_hash)"

cat > "$STATIC_DIR/.build-info.json" <<EOF
{
  "source": "packages/ui/dist",
  "stagedBy": "scripts/stage_ui_static.sh",
  "label": "$BUILD_LABEL",
  "gitSha": "$GIT_SHA",
  "dirty": $DIRTY,
  "builtAtUtc": "$BUILT_AT",
  "uiSourceHash": "$SOURCE_HASH"
}
EOF

echo "Staged UI static assets to $STATIC_DIR"
