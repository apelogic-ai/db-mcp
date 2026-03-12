import { defineConfig, devices } from "@playwright/test";

// Real E2E runs against the db-mcp UI server (python), not the Next dev server.
// It will create real connectors via BICP and hit real external services.

const port = process.env.PW_PORT ? parseInt(process.env.PW_PORT, 10) : 18080;

export default defineConfig({
  testDir: "./e2e",
  // Real-server E2E runs against the staged static bundle served by the Python UI server.
  testMatch: /(real-config|static-navigation)\.spec\.ts/,

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
      `./scripts/stage_ui_static.sh --build --label playwright-real; ` +
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
