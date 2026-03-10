import { test, expect } from "./fixtures";

test.describe("Navigation", () => {
  test("root redirects to connections", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/connections\/?$/);
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
    await page.goto("/connection/production");
    await expect(page.getByRole("heading", { name: "Connections" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Advanced" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Metrics" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Traces" })).toBeVisible();
    await expect(page.getByRole("link", { name: /^\+ New$/ })).toBeVisible();
  });

  test("advanced drawer links navigate between utility pages", async ({ page }) => {
    await page.goto("/connection/production");

    await page.getByRole("link", { name: "Traces" }).click();
    await expect(page).toHaveURL(/\/traces/);
  });

  test("connection tabs use the active underline state", async ({ page }) => {
    await page.goto("/connection/production");
    const overviewLink = page.getByRole("link", { name: "Overview" });
    await expect(overviewLink).toHaveClass(/border-brand/);

    const insightsLink = page.getByRole("link", { name: "Insights" });
    await expect(insightsLink).not.toHaveClass(/border-brand/);
  });

  test("connection drawer links switch routes", async ({ page }) => {
    await page.goto("/connection/production");
    await page.getByRole("link", { name: "staging" }).click();
    await expect(page).toHaveURL(/\/connection\/staging\/?$/);
  });

  test("new connection button opens the wizard", async ({ page }) => {
    await page.goto("/connection/production");
    await page.getByRole("link", { name: /^\+ New$/ }).click();
    await expect(page).toHaveURL(/\/connection\/new\/#connect$/);
  });
});
