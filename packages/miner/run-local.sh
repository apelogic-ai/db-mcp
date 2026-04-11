#!/bin/bash
# Run both miner components locally for hand-testing.
#
# Terminal 1: ./run-local.sh ingestor
# Terminal 2: ./run-local.sh agent
# Terminal 3: ./run-local.sh status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$HOME/.miner/lakehouse"
STATE_DIR="$HOME/.miner"
PORT=19900

case "${1:-help}" in
  ingestor)
    echo "Starting ingestor on http://localhost:$PORT"
    echo "Lakehouse: $DATA_DIR"
    echo ""
    mkdir -p "$DATA_DIR"
    cd "$SCRIPT_DIR/ingestor"
    bun src/server.ts --port $PORT --data-dir "$DATA_DIR"
    ;;

  agent)
    echo "Starting agent scan..."
    echo "State: $STATE_DIR"
    echo "Shipping to: http://localhost:$PORT/api/ingest"
    echo ""
    cd "$SCRIPT_DIR/agent"
    bun src/cli.ts scan \
      --state-dir "$STATE_DIR" \
      --developer "$(git config --global user.email || echo unknown)"
    ;;

  status)
    echo "=== Lakehouse contents ==="
    echo ""
    if [ -d "$DATA_DIR/raw" ]; then
      for agent_dir in "$DATA_DIR/raw"/*/; do
        agent=$(basename "$agent_dir")
        jsonl_count=$(ls "$agent_dir"/*.jsonl 2>/dev/null | wc -l | tr -d ' ')
        meta_count=$(ls "$agent_dir"/*.meta.json 2>/dev/null | wc -l | tr -d ' ')
        echo "  $agent: $jsonl_count batch(es)"
        for meta in "$agent_dir"/*.meta.json; do
          [ -f "$meta" ] || continue
          dev=$(python3 -c "import json; print(json.load(open('$meta')).get('developer','?'))")
          entries=$(python3 -c "import json; print(json.load(open('$meta')).get('entryCount',0))")
          echo "    $dev: $entries entries"
        done
      done
    else
      echo "  (empty — run agent first)"
    fi
    echo ""
    echo "=== Agent state ==="
    if [ -f "$STATE_DIR/shipper-cursors.json" ]; then
      echo "  Tracked files: $(python3 -c "import json; print(len(json.load(open('$STATE_DIR/shipper-cursors.json'))))")"
    else
      echo "  (no state yet)"
    fi
    ;;

  help|*)
    echo "Usage: $0 {ingestor|agent|status}"
    echo ""
    echo "  ingestor  — start the HTTP ingestor server"
    echo "  agent     — run a one-shot agent scan + ship"
    echo "  status    — show lakehouse contents"
    ;;
esac
