import { test, expect, mockData } from "./fixtures";

test.describe("Config Page", () => {
  test("displays connection list with badges", async ({ page }) => {
    await page.goto("/config");

    // Both connections visible (scoped to main to avoid nav selector match)
    const main = page.locator("main");
    await expect(main.getByText("production")).toBeVisible();
    await expect(main.getByText("staging")).toBeVisible();

    // Dialect icons (replaced text badges with SVG DialectIcon components)
    // Check for the presence of connection rows which contain DialectIcon components
    const productionRow = main.locator("[class*='rounded-lg border']").filter({ hasText: "production" });
    const stagingRow = main.locator("[class*='rounded-lg border']").filter({ hasText: "staging" });
    await expect(productionRow).toBeVisible();
    await expect(stagingRow).toBeVisible();
  });

  test("empty state when no connections", async ({ page, bicpMock }) => {
    bicpMock.on("connections/list", () => mockData.CONNECTIONS_EMPTY);
    await page.goto("/config");

    await expect(
      page.getByText("No database connections configured yet."),
    ).toBeVisible();
  });

  test("create connection flow", async ({ page, bicpMock }) => {
    await page.goto("/config");

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
    await page.goto("/config");

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
    await page.goto("/config");

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
    await page.goto("/config");
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
    await page.goto("/config");
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
    await page.goto("/config");

    // Set up dialog handler BEFORE triggering delete
    page.on("dialog", (dialog) => dialog.accept());

    // Click delete on production (not inside edit mode)
    await page.getByRole("button", { name: "Delete" }).first().click();

    // Verify delete was called
    const calls = bicpMock.getCalls("connections/delete");
    expect(calls.length).toBeGreaterThanOrEqual(1);
  });

  test("switch connection", async ({ page, bicpMock }) => {
    await page.goto("/config");

    // Staging has a "Switch" button
    await page.getByRole("button", { name: "Switch" }).click();

    const calls = bicpMock.getCalls("connections/switch");
    expect(calls.length).toBeGreaterThanOrEqual(1);
  });

  test("server error on connection list", async ({ page, bicpMock }) => {
    bicpMock.onError("connections/list", -32603, "Internal server error");
    await page.goto("/config");

    await expect(
      page.getByText(/error/i).or(page.getByText(/failed/i)),
    ).toBeVisible({ timeout: 5000 });
  });

  // ── API Connections ─────────────────────────────────────────

  test("displays API connections section", async ({ page, bicpMock }) => {
    bicpMock.on("connections/list", () => mockData.CONNECTIONS_WITH_API);
    await page.goto("/config");

    const main = page.locator("main");

    // API connection visible
    await expect(main.getByText("stripe-api")).toBeVisible();

    // Sync button visible for API connections
    await expect(main.getByRole("button", { name: "Sync Data" })).toBeVisible();
  });

  test("API empty state shows add button", async ({ page, bicpMock }) => {
    bicpMock.on("connections/list", () => mockData.CONNECTIONS_HAPPY);
    await page.goto("/config");

    await expect(
      page.getByText("No API connections configured yet."),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /add your first api/i }),
    ).toBeVisible();
  });

  test("create API connection flow", async ({ page, bicpMock }) => {
    await page.goto("/config");

    // Click "+ Add API Connection" from the empty state
    await page
      .getByRole("button", { name: /add.*api/i })
      .first()
      .click();

    // Fill the form
    await page.getByPlaceholder("my-api").fill("stripe-test");
    await page
      .getByPlaceholder("https://api.example.com/v1")
      .fill("https://api.stripe.com/v1");

    // Select auth type (bearer is default)
    await page.getByPlaceholder("API_KEY").fill("STRIPE_API_KEY");

    // Create
    await page.getByRole("button", { name: "Create" }).click();

    // Verify the create call
    const calls = bicpMock.getCalls("connections/create");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params).toMatchObject({
      name: "stripe-test",
      connectorType: "api",
      baseUrl: "https://api.stripe.com/v1",
    });
  });

  test("edit API connection shows config", async ({ page, bicpMock }) => {
    bicpMock.on("connections/list", () => mockData.CONNECTIONS_WITH_API);
    bicpMock.on("connections/get", (params) => {
      if (params?.name === "stripe-api") return mockData.CONNECTION_GET_API;
      return mockData.CONNECTION_GET_PRODUCTION;
    });
    await page.goto("/config");

    // The stripe-api connection row contains its name; click Edit in that row
    const stripeRow = page
      .locator("[class*='rounded-lg border']")
      .filter({ hasText: "stripe-api" })
      .first();
    await stripeRow.getByRole("button", { name: "Edit" }).click();

    // Verify connections/get was called with the right name
    const getCalls = bicpMock.getCalls("connections/get");
    expect(getCalls.some((c) => c.params?.name === "stripe-api")).toBe(true);

    // Base URL field should be visible with the configured URL
    const urlInput = page.getByPlaceholder("https://api.example.com/v1");
    await expect(urlInput).toBeVisible();
    const value = await urlInput.inputValue();
    expect(value).toBe("https://api.stripe.com/v1");
  });

  test("discover API endpoints", async ({ page, bicpMock }) => {
    bicpMock.on("connections/list", () => mockData.CONNECTIONS_WITH_API);
    await page.goto("/config");

    // Click Discover Endpoints button
    await page.getByRole("button", { name: "Discover Endpoints" }).click();

    // Verify discover was called
    const calls = bicpMock.getCalls("connections/discover");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params).toMatchObject({ name: "stripe-api" });

    // Success message should appear
    await expect(page.getByText(/found 3 endpoint/i)).toBeVisible({
      timeout: 5000,
    });
  });

  test("sync API connection", async ({ page, bicpMock }) => {
    bicpMock.on("connections/list", () => mockData.CONNECTIONS_WITH_API);
    await page.goto("/config");

    // Click Sync Data button
    await page.getByRole("button", { name: "Sync Data" }).click();

    // Verify sync was called
    const calls = bicpMock.getCalls("connections/sync");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params).toMatchObject({ name: "stripe-api" });

    // Success message should appear
    await expect(page.getByText(/synced 2 endpoints/i)).toBeVisible({
      timeout: 5000,
    });
  });

  // ── Agent Configuration ─────────────────────────────────────

  test("displays detected agents with action buttons", async ({ page }) => {
    await page.goto("/config");

    // Agent Configuration section title
    await expect(page.getByText("Agent Configuration")).toBeVisible();

    // All three agents visible (names only, badges removed in rebrand)
    await expect(page.getByText("Claude Desktop")).toBeVisible();
    await expect(page.getByText("Claude Code")).toBeVisible();
    await expect(page.getByText("Codex CLI")).toBeVisible();

    // Claude Desktop is configured - should have Remove and Edit Config buttons
    const desktopRow = page.getByTestId("agent-claude-desktop");
    await expect(desktopRow.getByRole("button", { name: "Remove" })).toBeVisible();
    await expect(desktopRow.getByRole("button", { name: "Edit Config" })).toBeVisible();

    // Claude Code is installed but not configured - should have Add button
    const codeRow = page.getByTestId("agent-claude-code");
    await expect(codeRow.getByRole("button", { name: "Add" })).toBeVisible();

    // Codex is not installed - should have no action buttons (agent row exists but disabled/grayed out)
    const codexRow = page.getByTestId("agent-codex");
    await expect(codexRow).toBeVisible();
    await expect(codexRow.getByRole("button", { name: "Add" })).not.toBeVisible();
    await expect(codexRow.getByRole("button", { name: "Remove" })).not.toBeVisible();
  });

  test("add db-mcp to agent", async ({ page, bicpMock }) => {
    await page.goto("/config");

    // Claude Code has an "Add" button (installed but not configured)
    const codeRow = page.getByTestId("agent-claude-code");
    await codeRow.getByRole("button", { name: "Add" }).click();

    // Verify configure was called
    const calls = bicpMock.getCalls("agents/configure");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params).toMatchObject({ agentId: "claude-code" });
  });

  test("remove db-mcp from agent", async ({ page, bicpMock }) => {
    await page.goto("/config");

    // Claude Desktop has a "Remove" button (configured)
    const desktopRow = page.getByTestId("agent-claude-desktop");
    await desktopRow.getByRole("button", { name: "Remove" }).click();

    // Verify remove was called
    const calls = bicpMock.getCalls("agents/remove");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params).toMatchObject({ agentId: "claude-desktop" });
  });

  test("edit config opens editor directly", async ({ page, bicpMock }) => {
    await page.goto("/config");

    const desktopRow = page.getByTestId("agent-claude-desktop");

    // Click "Edit Config" — opens textarea immediately
    await desktopRow.getByRole("button", { name: "Edit Config" }).click();

    const editor = page.getByTestId("snippet-editor-claude-desktop");
    await expect(editor).toBeVisible();
    const value = await editor.inputValue();
    expect(value).toContain("db-mcp");

    // Modify and save
    await editor.fill(
      '{\n  "db-mcp": {\n    "command": "/new/path",\n    "args": ["start"]\n  }\n}',
    );
    await desktopRow.getByRole("button", { name: "Save" }).click();

    // Verify config-write was called
    const calls = bicpMock.getCalls("agents/config-write");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params?.agentId).toBe("claude-desktop");
    expect(calls[0].params?.snippet).toContain("/new/path");
  });

  test("edit config cancel closes editor", async ({ page }) => {
    await page.goto("/config");

    const desktopRow = page.getByTestId("agent-claude-desktop");
    await desktopRow.getByRole("button", { name: "Edit Config" }).click();
    await expect(
      page.getByTestId("snippet-editor-claude-desktop"),
    ).toBeVisible();

    // Cancel closes editor
    await desktopRow.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByTestId("snippet-editor-claude-desktop"),
    ).not.toBeVisible();
  });

  test("edit config shows validation error on bad input", async ({
    page,
    bicpMock,
  }) => {
    bicpMock.on("agents/config-write", () => mockData.AGENTS_WRITE_INVALID);
    await page.goto("/config");

    const desktopRow = page.getByTestId("agent-claude-desktop");
    await desktopRow.getByRole("button", { name: "Edit Config" }).click();
    await page.getByTestId("snippet-editor-claude-desktop").fill("{bad json}");
    await desktopRow.getByRole("button", { name: "Save" }).click();

    // Error displayed, editor stays open
    const errorEl = page.getByTestId("save-error-claude-desktop");
    await expect(errorEl).toBeVisible();
    await expect(errorEl).toContainText("Invalid JSON");
    await expect(
      page.getByTestId("snippet-editor-claude-desktop"),
    ).toBeVisible();
  });

  test("empty agents list", async ({ page, bicpMock }) => {
    bicpMock.on("agents/list", () => mockData.AGENTS_LIST_EMPTY);
    await page.goto("/config");

    await expect(page.getByText("No agents detected.")).toBeVisible();
  });

  test("not-installed agents have no action buttons", async ({ page }) => {
    await page.goto("/config");

    // Codex is not installed — should have no Add/Remove/Edit buttons
    const codexRow = page.getByTestId("agent-codex");
    await expect(
      codexRow.getByRole("button", { name: "Add" }),
    ).not.toBeVisible();
    await expect(
      codexRow.getByRole("button", { name: "Remove" }),
    ).not.toBeVisible();
    await expect(
      codexRow.getByRole("button", { name: "Edit Config" }),
    ).not.toBeVisible();
  });
});
