import { test, expect } from "@playwright/test";

test.describe("E2E: static navigation", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      const count = Number(window.sessionStorage.getItem("doc-load-count") || "0");
      window.sessionStorage.setItem("doc-load-count", String(count + 1));
    });
  });

  test("connection tabs keep pretty routes without full document reload", async ({
    page,
    request,
  }, testInfo) => {
    const fileName = `nav-files-${Date.now()}`;
    const dir = testInfo.outputPath(`nav-file-connector-${Date.now()}`);
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require("path");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "sample.csv"), "id,name\n1,alice\n2,bob\n", "utf8");

    const createResponse = await request.post("/api/connections/create", {
      data: {
        name: fileName,
        connectorType: "file",
        directory: dir,
        setActive: true,
      },
    });
    expect(createResponse.ok()).toBeTruthy();
    const createPayload = await createResponse.json();
    expect(createPayload.error).toBeUndefined();
    expect(createPayload).toMatchObject({
      success: true,
      name: fileName,
    });

    await page.goto(`/connection/${fileName}`, { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(new RegExp(`/connection/${fileName}/?$`), { timeout: 15_000 });
    await expect(page.evaluate(() => window.sessionStorage.getItem("doc-load-count"))).resolves.toBe(
      "1",
    );

    await page.getByRole("link", { name: "Insights" }).click();
    await expect(page).toHaveURL(new RegExp(`/connection/${fileName}/insights/?$`), { timeout: 15_000 });
    await expect(page.evaluate(() => window.sessionStorage.getItem("doc-load-count"))).resolves.toBe(
      "1",
    );

    await page.getByRole("link", { name: "Knowledge" }).click();
    await expect(page).toHaveURL(new RegExp(`/connection/${fileName}/knowledge/?$`), { timeout: 15_000 });
    await expect(page.evaluate(() => window.sessionStorage.getItem("doc-load-count"))).resolves.toBe(
      "1",
    );
  });
});
