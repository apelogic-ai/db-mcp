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
    // Use .first() because empty-state shows both "+ Add Database" and
    // "+ Add Your First Database" buttons.
    await page
      .getByRole("button", { name: /add.*database/i })
      .first()
      .click();
    await page.getByPlaceholder("my-database").fill(dbName);
    await page
      .getByPlaceholder("postgresql://user:pass@host:5432/database")
      .fill(POSTGRES_URL);
    await page.getByRole("button", { name: "Create" }).click();

    // Ensure it shows up in the list (dialect is now shown as DialectIcon SVG, not text)
    const main = page.locator("main");
    const dbRow = page
      .locator("[class*='rounded-lg border']")
      .filter({ hasText: dbName })
      .first();
    await expect(dbRow).toBeVisible({ timeout: 15_000 });
    // DialectIcon component is present but we just verify the connection row exists
    // since the dialect is represented by SVG icon, not text

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
    await page.getByPlaceholder("API_KEY").fill("API_KEY");

    await page.getByRole("button", { name: "Create" }).click();
    await expect(main.getByText(apiName)).toBeVisible({ timeout: 15_000 });

    // ── File connector (mock directory) ──────────────────────────────
    const dir = testInfo.outputPath(`file-connector-${Date.now()}`);

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
    await page
      .getByRole("button", { name: /add.*file/i })
      .first()
      .click();
    await page.getByPlaceholder("my-data-files").fill(fileName);
    await page.getByPlaceholder("/path/to/your/data").fill(dir);
    await page.getByRole("button", { name: "Create" }).click();

    await expect(main.getByText(fileName)).toBeVisible({ timeout: 15_000 });
  });
});
