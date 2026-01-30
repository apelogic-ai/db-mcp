import { test, expect } from "./fixtures";

test.describe("Navigation", () => {
  test("root redirects to /connectors", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/connectors/);
  });

  test("all nav items render", async ({ page }) => {
    await page.goto("/connectors");
    const nav = page.locator("nav");
    await expect(nav.getByText("Connectors")).toBeVisible();
    await expect(nav.getByText("Context")).toBeVisible();
    await expect(nav.getByText("Metrics")).toBeVisible();
    await expect(nav.getByText("Traces")).toBeVisible();
    await expect(nav.getByText("Insights")).toBeVisible();
  });

  test("navigate between tabs", async ({ page }) => {
    await page.goto("/connectors");

    await page.getByRole("link", { name: "Context" }).click();
    await expect(page).toHaveURL(/\/context/);

    await page.getByRole("link", { name: "Connectors" }).click();
    await expect(page).toHaveURL(/\/connectors/);
  });

  test("active tab is highlighted", async ({ page }) => {
    await page.goto("/connectors");
    const connectorsLink = page.locator("nav").getByText("Connectors");
    await expect(connectorsLink).toHaveClass(/bg-gray-800/);

    const contextLink = page.locator("nav").getByText("Context");
    await expect(contextLink).not.toHaveClass(/bg-gray-800/);
  });
});
