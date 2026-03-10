import { test, expect, type Page } from "@playwright/test";

const POSTGRES_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql://reader:NWDMCE5xdipIjRrp@hh-pgsql-public.ebi.ac.uk:5432/pfmegrnargs";

const POLYMARKET_BASE_URL =
  process.env.E2E_POLYMARKET_BASE_URL || "https://gamma-api.polymarket.com/";

async function completeConnectStep(page: Page, name: string) {
  await page.getByTestId("connection-name-input").fill(name);
  await page.getByRole("button", { name: /^Test$/ }).click();
  await expect(page.getByText(/Successfully connected/i)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /Next >/i }).click();
}

test.describe("E2E: real config", () => {
  test("can create + test DB/API/File connectors", async ({ page }, testInfo) => {
    const dbName = `mrna-${Date.now()}`;
    const apiName = `polymarket-${Date.now()}`;
    const fileName = `files-${Date.now()}`;

    // Database connector
    await page.goto("/connection/new?type=sql#connect", { waitUntil: "domcontentloaded" });
    await page.getByTestId("connection-url-input").fill(POSTGRES_URL);
    await completeConnectStep(page, dbName);
    await expect(page.getByText(dbName)).toBeVisible({ timeout: 15_000 });

    // API connector
    await page.goto("/connection/new?type=api#connect", { waitUntil: "domcontentloaded" });
    await page.getByTestId("connection-url-input").fill(POLYMARKET_BASE_URL);
    await page.getByRole("combobox").last().selectOption("none");
    await completeConnectStep(page, apiName);
    await expect(page.getByText(apiName)).toBeVisible({ timeout: 15_000 });

    // File connector
    const dir = testInfo.outputPath(`file-connector-${Date.now()}`);
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require("path");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "sample.csv"), "id,name\n1,alice\n2,bob\n", "utf8");

    await page.goto("/connection/new?type=file#connect", { waitUntil: "domcontentloaded" });
    await page.getByTestId("connection-directory-input").fill(dir);
    await completeConnectStep(page, fileName);
    await expect(page.getByText(fileName)).toBeVisible({ timeout: 15_000 });
  });
});
