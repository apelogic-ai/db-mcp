#!/bin/bash
# Build UI and run the backend server locally

set -e

cd "$(dirname "$0")/.."

echo "Building UI..."
cd packages/ui
bun install --frozen-lockfile 2>/dev/null || bun install
bun run build

echo "Copying to static directory..."
rm -rf ../core/src/db_mcp/static
cp -r dist ../core/src/db_mcp/static

echo "Starting backend server..."
cd ../core
uv run python -m db_mcp.ui_server
