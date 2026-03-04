import { test, expect } from "./fixtures";

test.describe("Navigation", () => {
  test("root redirects to /home when connections exist", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/home\/?$/);
  });

  test("root redirects to onboarding when no connections exist", async ({
    page,
    bicpMock,
  }) => {
    bicpMock.on("connections/list", () => ({
      connections: [],
      activeConnection: null,
    }));
    await page.goto("/");
    await expect(page).toHaveURL(/\/config\/\?wizard=onboarding/);
  });

  test("essentials nav renders core items and advanced group", async ({
    page,
  }) => {
    await page.goto("/home");
    const nav = page.locator("nav");
    await expect(nav.getByText("Home")).toBeVisible();
    await expect(nav.getByText("Setup")).toBeVisible();
    await expect(nav.getByText("Knowledge")).toBeVisible();
    await expect(nav.getByText("Insights")).toBeVisible();
    await expect(nav.locator("summary").filter({ hasText: "Advanced" })).toBeVisible();
    await expect(nav.getByText("Metrics")).not.toBeVisible();
    await expect(nav.getByText("Traces")).not.toBeVisible();
  });

  test("navigate between tabs", async ({ page }) => {
    await page.goto("/home");

    await page.getByRole("link", { name: "Knowledge" }).click();
    await expect(page).toHaveURL(/\/context/);

    await page.getByRole("link", { name: "Setup" }).click();
    await expect(page).toHaveURL(/\/config/);
  });

  test("active tab is highlighted", async ({ page }) => {
    await page.goto("/home");
    const homeLink = page.locator("nav").getByText("Home");
    await expect(homeLink).toHaveClass(/text-brand/);

    const setupLink = page.locator("nav").getByText("Setup");
    await expect(setupLink).not.toHaveClass(/text-brand/);
  });

  test("advanced mode shows metrics and traces in top nav", async ({ page }) => {
    await page.goto("/home");
    const nav = page.locator("nav");

    await nav.getByRole("button", { name: "Advanced" }).click();

    await expect(nav.getByRole("link", { name: "Metrics" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Traces" })).toBeVisible();
  });
});
