#!/bin/bash
# Build UI and run the backend server locally

set -e

cd "$(dirname "$0")/.."

echo "Building UI..."
cd packages/ui
bun install --frozen-lockfile 2>/dev/null || bun install
cd ../..
bash ./scripts/stage_ui_static.sh --build --label dev-sh

echo "Starting backend server..."
cd packages/core

# Open browser after short delay
(sleep 2 && open http://localhost:8080) &

uv run python -m db_mcp.ui_server
