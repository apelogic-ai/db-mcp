import { defineConfig, devices } from "@playwright/test";

// Real E2E runs against the db-mcp UI server (python), not the Next dev server.
// It will create real connectors via BICP and hit real external services.

const port = process.env.PW_PORT ? parseInt(process.env.PW_PORT, 10) : 18080;

export default defineConfig({
  testDir: "./e2e",
  // Only run the real-config spec by default (avoid the mocked suite).
  testMatch: /real-config\.spec\.ts/,

  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "line" : "html",

  use: {
    baseURL: `http://127.0.0.1:${port}`,
    colorScheme: "dark",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    // IMPORTANT: This assumes the repo has a python env capable of running db-mcp.
    // In CI you should install deps first (uv / pip / etc.).
    // We also isolate HOME so connections/config don't leak between runs.
    command:
      `bash -lc 'set -euo pipefail; ` +
      `export HOME="${process.env.PW_HOME || "/tmp/db-mcp-e2e-home"}"; ` +
      `mkdir -p "$HOME"; ` +
      `cd ../..; ` +
      `rm -rf packages/core/src/db_mcp/static; ` +
      `mkdir -p packages/core/src/db_mcp/static; ` +
      `mkdir -p packages/core/src/db_mcp/static/_next; ` +
      `cp -R packages/ui/.next/static packages/core/src/db_mcp/static/_next/; ` +
      `cp -R packages/ui/public/. packages/core/src/db_mcp/static/; ` +
      `mkdir -p packages/core/src/db_mcp/static/connections; ` +
      `cp packages/ui/.next/server/app/connections.html packages/core/src/db_mcp/static/connections/index.html; ` +
      `mkdir -p packages/core/src/db_mcp/static/connection; ` +
      `cp packages/ui/.next/server/app/connection.html packages/core/src/db_mcp/static/connection/index.html; ` +
      `mkdir -p packages/core/src/db_mcp/static/connection/new; ` +
      `cp packages/ui/.next/server/app/connection/new.html packages/core/src/db_mcp/static/connection/new/index.html; ` +
      `mkdir -p packages/core/src/db_mcp/static/connection/insights; ` +
      `cp packages/ui/.next/server/app/connection/insights.html packages/core/src/db_mcp/static/connection/insights/index.html; ` +
      `mkdir -p packages/core/src/db_mcp/static/connection/knowledge; ` +
      `cp packages/ui/.next/server/app/connection/knowledge.html packages/core/src/db_mcp/static/connection/knowledge/index.html; ` +
      `mkdir -p packages/core/src/db_mcp/static/metrics; ` +
      `cp packages/ui/.next/server/app/metrics.html packages/core/src/db_mcp/static/metrics/index.html; ` +
      `mkdir -p packages/core/src/db_mcp/static/traces; ` +
      `cp packages/ui/.next/server/app/traces.html packages/core/src/db_mcp/static/traces/index.html; ` +
      `cp packages/ui/.next/server/app/index.html packages/core/src/db_mcp/static/index.html; ` +
      // Ensure python can import workspace packages when running from source (CI uv workspace).
      `export PYTHONPATH="$PWD/packages/core/src:$PWD/packages/models/src${process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : ""}"; ` +
      // Prefer local venv if present, otherwise fall back to python on PATH.
      `PY=./.venv/bin/python; if [ ! -x "$PY" ]; then PY=python3; fi; ` +
      `$PY -m db_mcp.cli ui --host 127.0.0.1 --port ${port}'`,
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
