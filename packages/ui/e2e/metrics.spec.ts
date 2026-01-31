import { test, expect, mockData } from "./fixtures";

test.describe("Metrics Page", () => {
  // ── Catalog Tab ─────────────────────────────────────────────

  test("renders page header", async ({ page }) => {
    await page.goto("/metrics");

    const main = page.locator("main");
    await expect(main.getByRole("heading", { name: "Metrics" })).toBeVisible();
  });

  test("displays catalog tab with metrics", async ({ page }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Catalog tab is active by default (metrics count only)
    await expect(main.getByText("Catalog (2)")).toBeVisible();

    // Candidate count loads on page init
    await expect(main.getByText("Candidates (2)")).toBeVisible();

    // Metrics section
    await expect(main.getByText("2 metrics defined")).toBeVisible();
    await expect(main.getByText("Daily Active Users")).toBeVisible();
    await expect(main.getByText("Total Revenue")).toBeVisible();

    // Tags
    await expect(main.getByText("engagement").first()).toBeVisible();
    await expect(main.getByText("kpi").first()).toBeVisible();
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

    // Dimensions shown inline as badges
    await expect(main.getByText("Dimensions:")).toBeVisible();
    await expect(main.getByText("carrier", { exact: true })).toBeVisible();
    await expect(main.getByText("city", { exact: true })).toBeVisible();

    // Dimension type badge from registry lookup
    await expect(main.getByText("categorical")).toBeVisible();

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

  test("switching to Candidates tab auto-loads candidates", async ({
    page,
    bicpMock,
  }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Switch to Candidates tab
    await main.getByRole("button", { name: "Candidates" }).click();

    // Candidates auto-load on mount — metric candidates appear
    await expect(main.getByText("Metric Candidates (2)")).toBeVisible();
    await expect(main.getByText("Count Sessions")).toBeVisible();
    await expect(main.getByText("Avg Duration")).toBeVisible();

    // Approve and Reject buttons (2 metric candidates)
    const approveButtons = main.getByRole("button", {
      name: "Approve",
      exact: true,
    });
    expect(await approveButtons.count()).toBe(2);

    const rejectButtons = main.getByRole("button", {
      name: "Reject",
      exact: true,
    });
    expect(await rejectButtons.count()).toBe(2);

    // Verify mine calls: page load + tab mount (may double in React strict mode)
    const calls = bicpMock.getCalls("metrics/candidates");
    expect(calls.length).toBeGreaterThanOrEqual(2);
    expect(calls[0].params).toMatchObject({ connection: "production" });
  });

  test("expanding a metric candidate shows editable form", async ({ page }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Switch to Candidates tab, wait for auto-load
    await main.getByRole("button", { name: "Candidates" }).click();
    await expect(main.getByText("Count Sessions")).toBeVisible();

    // Click to expand — opens edit form
    await main.getByText("Count Sessions").click();

    // Form fields appear pre-filled
    const nameInput = main.getByPlaceholder("e.g. daily_active_users");
    await expect(nameInput).toHaveValue("count_sessions");

    // SQL field pre-filled
    const sqlField = main.getByPlaceholder(
      "SELECT COUNT(DISTINCT user_id) FROM ...",
    );
    await expect(sqlField).toHaveValue("SELECT COUNT(*) FROM sessions");

    // Evidence shown
    await expect(main.getByText("example_001.yaml")).toBeVisible();

    // Approve button (green) in the form — use first() since collapsed row also has one
    await expect(
      main.getByRole("button", { name: "Approve", exact: true }).first(),
    ).toBeVisible();
  });

  test("Approve candidate calls metrics/approve", async ({
    page,
    bicpMock,
  }) => {
    await page.goto("/metrics");

    const main = page.locator("main");

    // Switch to Candidates, wait for auto-load
    await main.getByRole("button", { name: "Candidates" }).click();
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

    // Switch to Candidates, wait for auto-load
    await main.getByRole("button", { name: "Candidates" }).click();
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

    // Switch to Candidates tab — auto-mines on mount
    await main.getByRole("button", { name: "Candidates" }).click();

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
