import { test, expect, mockData } from "./fixtures";

test.describe("Connectors Page", () => {
  test("displays connection list with badges", async ({ page }) => {
    await page.goto("/connectors");

    // Both connections visible (scoped to main to avoid nav selector match)
    const main = page.locator("main");
    await expect(main.getByText("production")).toBeVisible();
    await expect(main.getByText("staging")).toBeVisible();

    // Dialect badges
    await expect(main.getByText("postgresql", { exact: true })).toBeVisible();
    await expect(main.getByText("clickhouse", { exact: true })).toBeVisible();
  });

  test("empty state when no connections", async ({ page, bicpMock }) => {
    bicpMock.on("connections/list", () => mockData.CONNECTIONS_EMPTY);
    await page.goto("/connectors");

    await expect(
      page.getByText("No database connections configured yet."),
    ).toBeVisible();
  });

  test("create connection flow", async ({ page, bicpMock }) => {
    await page.goto("/connectors");

    // Click "+ Add Database" button in the Database section
    await page.getByRole("button", { name: /add database/i }).click();

    // Fill the form fields by placeholder text
    await page.getByPlaceholder("my-database").fill("new-connection");
    await page
      .getByPlaceholder("postgresql://user:pass@host:5432/database")
      .fill("postgresql://user:pass@localhost:5432/mydb");

    // Create button should now be enabled
    await page.getByRole("button", { name: "Create" }).click();

    // Verify the create call was made
    const calls = bicpMock.getCalls("connections/create");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params).toMatchObject({
      name: "new-connection",
    });
  });

  test("edit connection shows masked URL", async ({ page }) => {
    await page.goto("/connectors");

    // Click edit on production
    await page.getByRole("button", { name: "Edit" }).first().click();

    // URL field should be visible with masked password
    const urlInput = page.getByPlaceholder(
      "postgresql://user:pass@host:5432/database",
    );
    await expect(urlInput).toBeVisible();

    // The displayed URL should contain mask characters
    const value = await urlInput.inputValue();
    expect(value).toContain("****");
  });

  test("edit connection prevents save with masked URL", async ({
    page,
    bicpMock,
  }) => {
    await page.goto("/connectors");

    // Enter edit mode
    await page.getByRole("button", { name: "Edit" }).first().click();

    // The Update button should be disabled when URL contains masked value
    const updateButton = page.getByRole("button", { name: "Update" });
    await expect(updateButton).toBeDisabled();

    // Verify no update call was made
    const calls = bicpMock.getCalls("connections/update");
    expect(calls.length).toBe(0);
  });

  test("test connection success", async ({ page }) => {
    await page.goto("/connectors");
    await page.getByRole("button", { name: "Edit" }).first().click();

    // Replace the masked URL with a real one
    const urlInput = page.getByPlaceholder(
      "postgresql://user:pass@host:5432/database",
    );
    await urlInput.clear();
    await urlInput.fill(
      "postgresql://admin:realpass@db.example.com:5432/analytics",
    );

    // Click test
    await page.getByRole("button", { name: "Test" }).click();

    // Success shows a green checkmark SVG (not text)
    // Look for the green check icon that appears after successful test
    await expect(page.locator("svg.text-green-500")).toBeVisible({
      timeout: 5000,
    });
  });

  test("test connection failure", async ({ page, bicpMock }) => {
    bicpMock.on("connections/test", () => mockData.CONNECTION_TEST_FAILURE);
    await page.goto("/connectors");
    await page.getByRole("button", { name: "Edit" }).first().click();

    const urlInput = page.getByPlaceholder(
      "postgresql://user:pass@host:5432/database",
    );
    await urlInput.clear();
    await urlInput.fill(
      "postgresql://admin:wrong@db.example.com:5432/analytics",
    );

    await page.getByRole("button", { name: "Test" }).click();

    // Failure shows visible error text
    await expect(
      page.getByText(/fail/i).or(page.getByText(/error/i)),
    ).toBeVisible();
  });

  test("delete connection with confirmation", async ({ page, bicpMock }) => {
    await page.goto("/connectors");

    // Set up dialog handler BEFORE triggering delete
    page.on("dialog", (dialog) => dialog.accept());

    // Click delete on production (not inside edit mode)
    await page.getByRole("button", { name: "Delete" }).first().click();

    // Verify delete was called
    const calls = bicpMock.getCalls("connections/delete");
    expect(calls.length).toBeGreaterThanOrEqual(1);
  });

  test("switch connection", async ({ page, bicpMock }) => {
    await page.goto("/connectors");

    // Staging has a "Switch" button
    await page.getByRole("button", { name: "Switch" }).click();

    const calls = bicpMock.getCalls("connections/switch");
    expect(calls.length).toBeGreaterThanOrEqual(1);
  });

  test("server error on connection list", async ({ page, bicpMock }) => {
    bicpMock.onError("connections/list", -32603, "Internal server error");
    await page.goto("/connectors");

    await expect(
      page.getByText(/error/i).or(page.getByText(/failed/i)),
    ).toBeVisible({ timeout: 5000 });
  });
});
