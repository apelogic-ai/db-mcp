import { test, expect } from "./fixtures";

test.describe("Navigation", () => {
  test("root redirects to /config", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/config/);
  });

  test("all nav items render", async ({ page }) => {
    await page.goto("/config");
    const nav = page.locator("nav");
    await expect(nav.getByText("Config")).toBeVisible();
    await expect(nav.getByText("Context")).toBeVisible();
    await expect(nav.getByText("Metrics")).toBeVisible();
    await expect(nav.getByText("Traces")).toBeVisible();
    await expect(nav.getByText("Insights")).toBeVisible();
  });

  test("navigate between tabs", async ({ page }) => {
    await page.goto("/config");

    await page.getByRole("link", { name: "Context" }).click();
    await expect(page).toHaveURL(/\/context/);

    await page.getByRole("link", { name: "Config" }).click();
    await expect(page).toHaveURL(/\/config/);
  });

  test("active tab is highlighted", async ({ page }) => {
    await page.goto("/config");
    const configLink = page.locator("nav").getByText("Config");
    await expect(configLink).toHaveClass(/text-brand/);

    const contextLink = page.locator("nav").getByText("Context");
    await expect(contextLink).not.toHaveClass(/text-brand/);
  });
});
