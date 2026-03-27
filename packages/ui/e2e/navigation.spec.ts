import { test, expect } from "./fixtures";

test.describe("Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      const count = Number(window.sessionStorage.getItem("doc-load-count") || "0");
      window.sessionStorage.setItem("doc-load-count", String(count + 1));
    });
  });

  test("root redirects to connections", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/connection\/(production\/?)?(\?name=production)?$/);
  });

  test("root still redirects to connections when no connections exist", async ({
    page,
    bicpMock,
  }) => {
    bicpMock.on("connections/list", () => ({
      connections: [],
      activeConnection: null,
    }));
    await page.goto("/");
    await expect(page).toHaveURL(/\/connection\/new\/#connect$/);
  });

  test("drawer renders connections and advanced links", async ({
    page,
  }) => {
    await page.goto("/connection?name=production");
    await expect(page.getByRole("heading", { name: "Connections" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Advanced" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Metrics" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Traces" })).toBeVisible();
    await expect(page.getByRole("button", { name: /^\+ New$/ })).toBeVisible();
  });

  test("advanced drawer links navigate between utility pages", async ({ page }) => {
    await page.goto("/connection?name=production");

    await page.getByRole("link", { name: "Traces" }).click();
    await expect(page).toHaveURL(/\/traces/);
  });

  test("connection tabs use the active underline state", async ({ page }) => {
    await page.goto("/connection?name=production");
    const overviewLink = page.getByRole("link", { name: "Overview" });
    await expect(overviewLink).toHaveClass(/border-brand/);

    const insightsLink = page.getByRole("link", { name: "Insights" });
    await expect(insightsLink).not.toHaveClass(/border-brand/);
  });

  test("connection tabs keep pretty routes and client-side navigation", async ({ page }) => {
    await page.goto("/connection?name=production");
    await expect(page).toHaveURL(/\/connection\/production\/?$/);
    await expect(page.evaluate(() => window.sessionStorage.getItem("doc-load-count"))).resolves.toBe(
      "1",
    );

    await page.getByRole("link", { name: "Insights" }).click();
    await expect(page).toHaveURL(/\/connection\/production\/insights\/?$/);
    await expect(page.evaluate(() => window.sessionStorage.getItem("doc-load-count"))).resolves.toBe(
      "1",
    );

    await page.getByRole("link", { name: "Knowledge" }).click();
    await expect(page).toHaveURL(/\/connection\/production\/knowledge\/?$/);
    await expect(page.evaluate(() => window.sessionStorage.getItem("doc-load-count"))).resolves.toBe(
      "1",
    );
  });

  test("connection drawer links switch routes", async ({ page }) => {
    await page.goto("/connection?name=production");
    await page.getByRole("link", { name: "staging" }).click();
    await expect(page).toHaveURL(/\/connection\/(staging\/?)?(\?name=staging)?$/);
  });

  test("new connection button opens the wizard", async ({ page }) => {
    await page.goto("/connection?name=production");
    await page.getByRole("button", { name: /^\+ New$/ }).click();
    await expect(page).toHaveURL(/\/connection\/new\/#connect$/);
  });
});
