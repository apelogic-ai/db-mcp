import { test, expect, mockData } from "./fixtures";

test.describe("Metrics Page", () => {
  // ── Catalog Tab ─────────────────────────────────────────────

  test("renders page header with connection badge", async ({ page }) => {
    await page.goto("/metrics");

    const main = page.locator("main");
    await expect(
      main.getByRole("heading", { name: "Metrics & Dimensions" }),
    ).toBeVisible();
    await expect(main.getByText("production")).toBeVisible();
  });

  test("displays catalog tab with metrics and dimensions", async ({ page }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Catalog tab is active by default
    await expect(main.getByText("Catalog (4)")).toBeVisible();

    // Metrics section
    await expect(main.getByText("2 metrics defined")).toBeVisible();
    await expect(main.getByText("Daily Active Users")).toBeVisible();
    await expect(main.getByText("Total Revenue")).toBeVisible();

    // Tags
    await expect(main.getByText("engagement").first()).toBeVisible();
    await expect(main.getByText("kpi").first()).toBeVisible();

    // Dimensions section
    await expect(main.getByText("2 dimensions defined")).toBeVisible();
    await expect(main.getByText("Carrier", { exact: true })).toBeVisible();
    await expect(main.getByText("Report Date", { exact: true })).toBeVisible();

    // Dimension type badges
    await expect(main.getByText("categorical")).toBeVisible();
    await expect(main.getByText("temporal")).toBeVisible();

    // Known values
    await expect(main.getByText("tmo")).toBeVisible();
    await expect(main.getByText("helium_mobile")).toBeVisible();
  });

  test("expanding a metric shows SQL and details", async ({ page }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Click on DAU metric row to expand
    await main.getByText("Daily Active Users").click();

    // SQL preview appears
    await expect(
      main.getByText("SELECT COUNT(DISTINCT user_id) FROM sessions"),
    ).toBeVisible();

    // Tables info
    await expect(main.getByText("Tables: sessions")).toBeVisible();

    // Dimensions info
    await expect(main.getByText("Dimensions: carrier, city")).toBeVisible();

    // Notes
    await expect(main.getByText("Excludes test accounts")).toBeVisible();
  });

  test("empty catalog shows placeholder text", async ({ page, bicpMock }) => {
    bicpMock.on("metrics/list", () => mockData.METRICS_LIST_EMPTY);
    await page.goto("/metrics");

    const main = page.locator("main");

    await expect(main.getByText("Catalog (0)")).toBeVisible();
    await expect(
      main.getByText("No metrics defined yet").first(),
    ).toBeVisible();
    await expect(
      main.getByText("No dimensions defined yet").first(),
    ).toBeVisible();
  });

  test("+ Add Metric opens form and submits", async ({ page, bicpMock }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Click Add Metric
    await main.getByRole("button", { name: "+ Add Metric" }).click();

    // Form fields appear
    await expect(main.getByText("New Metric")).toBeVisible();
    await expect(
      main.getByPlaceholder("e.g. daily_active_users"),
    ).toBeVisible();

    // Fill form
    await main.getByPlaceholder("e.g. daily_active_users").fill("new_metric");
    await main
      .getByPlaceholder("What this metric measures")
      .fill("A new test metric");
    await main
      .getByPlaceholder("SELECT COUNT(DISTINCT user_id) FROM ...")
      .fill("SELECT COUNT(*) FROM test_table");

    // Submit
    await main.getByRole("button", { name: "Add Metric", exact: true }).click();

    // Verify the BICP call
    const calls = bicpMock.getCalls("metrics/add");
    expect(calls.length).toBe(1);
    expect(calls[0].params).toMatchObject({
      connection: "production",
      type: "metric",
      data: {
        name: "new_metric",
        description: "A new test metric",
        sql: "SELECT COUNT(*) FROM test_table",
      },
    });
  });

  test("+ Add Dimension opens form and submits", async ({ page, bicpMock }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Click Add Dimension
    await main.getByRole("button", { name: "+ Add Dimension" }).click();

    // Form fields appear
    await expect(main.getByText("New Dimension")).toBeVisible();

    // Fill form - use exact match to avoid "e.g. Carrier" (display name)
    await main.getByPlaceholder("e.g. carrier", { exact: true }).fill("region");
    await main
      .getByPlaceholder("e.g. cdr_agg_day.carrier")
      .fill("users.region");

    // Submit
    await main
      .getByRole("button", { name: "Add Dimension", exact: true })
      .click();

    // Verify the BICP call
    const calls = bicpMock.getCalls("metrics/add");
    expect(calls.length).toBe(1);
    expect(calls[0].params).toMatchObject({
      connection: "production",
      type: "dimension",
      data: {
        name: "region",
        column: "users.region",
      },
    });
  });

  test("Edit button opens form with existing data", async ({ page }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Click Edit on the first metric
    await main.getByRole("button", { name: "Edit" }).first().click();

    // Form appears with pre-filled data
    await expect(main.getByText("Edit: daily_active_users")).toBeVisible();
    const nameInput = main.getByPlaceholder("e.g. daily_active_users");
    await expect(nameInput).toHaveValue("daily_active_users");
  });

  test("Delete metric calls metrics/delete", async ({ page, bicpMock }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Wait for content to load
    await expect(main.getByText("Daily Active Users")).toBeVisible();

    // Click Delete on the first metric
    await main.getByRole("button", { name: "Delete" }).first().click();

    // Verify the BICP call
    const calls = bicpMock.getCalls("metrics/delete");
    expect(calls.length).toBe(1);
    expect(calls[0].params).toMatchObject({
      connection: "production",
      type: "metric",
      name: "daily_active_users",
    });
  });

  test("Cancel button closes add form", async ({ page }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Open form
    await main.getByRole("button", { name: "+ Add Metric" }).click();
    await expect(main.getByText("New Metric")).toBeVisible();

    // Cancel
    await main.getByRole("button", { name: "Cancel" }).click();

    // Form is gone
    await expect(main.getByText("New Metric")).not.toBeVisible();
  });

  // ── Candidates Tab ──────────────────────────────────────────

  test("switching to Candidates tab shows mine button", async ({ page }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Switch to Candidates tab
    await main.getByRole("button", { name: "Candidates" }).click();

    // Mine button is visible
    await expect(
      main.getByRole("button", { name: "Mine Vault" }),
    ).toBeVisible();

    // Description text
    await expect(
      main.getByText("Mine the knowledge vault to discover metric"),
    ).toBeVisible();
  });

  test("Mine Vault returns candidates", async ({ page, bicpMock }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Switch to Candidates tab
    await main.getByRole("button", { name: "Candidates" }).click();

    // Click Mine
    await main.getByRole("button", { name: "Mine Vault" }).click();

    // Metric candidates appear
    await expect(main.getByText("Metric Candidates (2)")).toBeVisible();
    await expect(main.getByText("Count Sessions")).toBeVisible();
    await expect(main.getByText("Avg Duration")).toBeVisible();

    // Dimension candidates section with grouping
    await expect(main.getByText("Dimension Candidates (1)")).toBeVisible();

    // Dimensions are grouped by semantic category — "Location" group visible but collapsed
    await expect(main.getByText("Location", { exact: true })).toBeVisible();

    // "City" not visible until group is expanded
    await expect(main.getByText("City", { exact: true })).not.toBeVisible();

    // Expand the Location group
    await main.getByText("Location", { exact: true }).click();
    await expect(main.getByText("City", { exact: true })).toBeVisible();

    // Confidence badges (metrics visible, dimension now expanded)
    await expect(main.getByText("70%")).toBeVisible();
    await expect(main.getByText("50%")).toBeVisible();
    await expect(main.getByText("60%")).toBeVisible();

    // Source badges
    await expect(main.getByText("examples").first()).toBeVisible();

    // Evidence
    await expect(main.getByText("example_001.yaml").first()).toBeVisible();

    // Approve and Reject buttons: 2 metric + 1 dimension individual (exact to exclude "Approve All")
    const approveButtons = main.getByRole("button", {
      name: "Approve",
      exact: true,
    });
    expect(await approveButtons.count()).toBe(3);

    const rejectButtons = main.getByRole("button", {
      name: "Reject",
      exact: true,
    });
    expect(await rejectButtons.count()).toBe(3);

    // Bulk actions on group header
    await expect(
      main.getByRole("button", { name: "Approve All" }),
    ).toBeVisible();
    await expect(
      main.getByRole("button", { name: "Reject All" }),
    ).toBeVisible();

    // Verify mine call was made
    const calls = bicpMock.getCalls("metrics/candidates");
    expect(calls.length).toBe(1);
    expect(calls[0].params).toMatchObject({ connection: "production" });
  });

  test("Approve candidate calls metrics/approve", async ({
    page,
    bicpMock,
  }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Switch to Candidates, mine
    await main.getByRole("button", { name: "Candidates" }).click();
    await main.getByRole("button", { name: "Mine Vault" }).click();

    // Wait for candidates
    await expect(main.getByText("Count Sessions")).toBeVisible();

    // Approve first metric candidate
    await main.getByRole("button", { name: "Approve" }).first().click();

    // Verify the BICP call
    const calls = bicpMock.getCalls("metrics/approve");
    expect(calls.length).toBe(1);
    expect(calls[0].params).toMatchObject({
      connection: "production",
      type: "metric",
    });
  });

  test("Reject hides the candidate", async ({ page }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Switch to Candidates, mine
    await main.getByRole("button", { name: "Candidates" }).click();
    await main.getByRole("button", { name: "Mine Vault" }).click();

    // Wait for candidates
    await expect(main.getByText("Count Sessions")).toBeVisible();

    // Reject first metric candidate
    await main.getByRole("button", { name: "Reject" }).first().click();

    // The candidate should disappear (only 1 metric candidate left)
    await expect(main.getByText("Metric Candidates (1)")).toBeVisible();
  });

  test("empty mining results shows message", async ({ page, bicpMock }) => {
    bicpMock.on("metrics/candidates", () => mockData.METRICS_CANDIDATES_EMPTY);
    await page.goto("/metrics");

    const main = page.locator("main");

    // Switch to Candidates, mine
    await main.getByRole("button", { name: "Candidates" }).click();
    await main.getByRole("button", { name: "Mine Vault" }).click();

    // Empty message
    await expect(main.getByText("No new candidates found")).toBeVisible();
  });

  // ── No connection ───────────────────────────────────────────

  test("shows message when no active connection", async ({
    page,
    bicpMock,
  }) => {
    bicpMock.on("connections/list", () => mockData.CONNECTIONS_EMPTY);
    await page.goto("/metrics");

    const main = page.locator("main");
    await expect(main.getByText("No active connection")).toBeVisible();
  });
});
