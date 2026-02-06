import { test, expect } from "@playwright/test";

// Real E2E test against a running db-mcp UI server (not BICP-mocked).
// This is intended for CI smoke coverage.

const POSTGRES_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql://reader:NWDMCE5xdipIjRrp@hh-pgsql-public.ebi.ac.uk:5432/pfmegrnargs";

const POLYMARKET_BASE_URL =
  process.env.E2E_POLYMARKET_BASE_URL || "https://gamma-api.polymarket.com/";

test.describe("E2E: real config", () => {
  test("can create + test DB/API/File connectors", async ({
    page,
  }, testInfo) => {
    const dbName = `mrna-${Date.now()}`;
    const apiName = `polymarket-${Date.now()}`;
    const fileName = `files-${Date.now()}`;

    await page.goto("/config", { waitUntil: "domcontentloaded" });

    // ── Database connector ───────────────────────────────────────────
    await page.getByRole("button", { name: /add.*database/i }).click();
    await page.getByPlaceholder("my-database").fill(dbName);
    await page
      .getByPlaceholder("postgresql://user:pass@host:5432/database")
      .fill(POSTGRES_URL);
    await page.getByRole("button", { name: "Create" }).click();

    // Ensure it shows up.
    const main = page.locator("main");
    await expect(main.getByText(dbName)).toBeVisible({ timeout: 15_000 });

    // Test DB connection.
    const dbRow = page
      .locator("[class*='rounded-lg border']")
      .filter({ hasText: dbName })
      .first();
    await dbRow.getByRole("button", { name: "Edit" }).click();
    await page.getByRole("button", { name: "Test" }).click();
    await expect(page.getByText(/connected|success|reachable/i)).toBeVisible({
      timeout: 30_000,
    });

    // ── API connector (Polymarket) ───────────────────────────────────
    await page.goto("/config", { waitUntil: "domcontentloaded" });

    await page
      .getByRole("button", { name: /add.*api/i })
      .first()
      .click();
    await page.getByPlaceholder("my-api").fill(apiName);
    await page
      .getByPlaceholder("https://api.example.com/v1")
      .fill(POLYMARKET_BASE_URL);

    // Leave default auth (Bearer) but set env var name so it's valid config.
    // For public APIs, auth may not be required.
    await page.getByPlaceholder("API_KEY").fill("API_KEY");

    await page.getByRole("button", { name: "Create" }).click();
    await expect(main.getByText(apiName)).toBeVisible({ timeout: 15_000 });

    const apiRow = page
      .locator("[class*='rounded-lg border']")
      .filter({ hasText: apiName })
      .first();
    await apiRow.getByRole("button", { name: "Edit" }).click();
    await page.getByRole("button", { name: "Test" }).click();
    await expect(page.getByText(/API reachable|HTTP 200/i)).toBeVisible({
      timeout: 30_000,
    });

    // ── File connector (mock directory) ──────────────────────────────
    // We create a temp directory on the runner and point the UI to it.
    // IMPORTANT: the UI server must run on the same machine as the test.
    const dir = testInfo.outputPath(`file-connector-${Date.now()}`);

    // Create a tiny CSV file into the test output dir via the browser-less Node side.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require("path");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, "sample.csv"),
      "id,name\n1,alice\n2,bob\n",
      "utf8",
    );

    await page.goto("/config", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: /add.*file/i }).click();
    await page.getByPlaceholder("my-data-files").fill(fileName);
    await page.getByPlaceholder("/path/to/your/data").fill(dir);
    await page.getByRole("button", { name: "Create" }).click();

    await expect(main.getByText(fileName)).toBeVisible({ timeout: 15_000 });
  });
});
