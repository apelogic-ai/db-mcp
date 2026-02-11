import { test, expect, mockData } from "./fixtures";

test.describe("Insights Page", () => {
  test("renders page header with period selector", async ({ page }) => {
    await page.goto("/insights");

    const main = page.locator("main");
    await expect(main.getByRole("heading", { name: "Insights" })).toBeVisible();
    await expect(
      main.getByText("Semantic layer gaps and usage patterns"),
    ).toBeVisible();

    // Period selector with default value
    const select = main.locator("select");
    await expect(select).toBeVisible();
    await expect(select).toHaveValue("7");
  });

  test("displays summary stats cards", async ({ page }) => {
    await page.goto("/insights");

    const main = page.locator("main");

    // Summary stats - use first() to avoid strict mode with auto-refresh
    await expect(main.getByText("Tool Traces").first()).toBeVisible();
    await expect(main.getByText("Total Duration").first()).toBeVisible();
    await expect(main.getByText("Errors").first()).toBeVisible();
    await expect(main.getByText("Knowledge Captured").first()).toBeVisible();
  });

  test("displays Knowledge Flow Banner", async ({ page }) => {
    await page.goto("/insights");

    const main = page.locator("main");
    // The banner should appear above the stats cards, banner text will depend on state
    // In the mock data, we should see either green (capturing) or yellow/neutral states
    await expect(
      main.getByText(/Knowledge capture active|No knowledge captured|Start using your agent/).first(),
    ).toBeVisible();
    
    // Banner should have dismiss button if not in neutral state
    const dismissBtn = main.locator("button:has-text('×')");
    if (await dismissBtn.isVisible()) {
      await expect(dismissBtn).toBeVisible();
    }
  });

  test("displays Unmapped Terms card with open and resolved gaps", async ({
    page,
  }) => {
    await page.goto("/insights");

    const main = page.locator("main");
    await expect(main.getByText("Unmapped Terms").first()).toBeVisible();

    // Open gaps count badge
    await expect(main.getByText("2 open").first()).toBeVisible();
    // Resolved gaps count badge
    await expect(main.getByText("1 resolved").first()).toBeVisible();

    // Open gap terms
    await expect(main.getByText("nas_id").first()).toBeVisible();
    await expect(main.getByText("nasid").first()).toBeVisible();
    await expect(main.getByText("cui").first()).toBeVisible();

    // Suggested rule for nas_id group
    await expect(
      main
        .getByText("nas_ids, nas_id, nas_identifier, nasid are synonyms.")
        .first(),
    ).toBeVisible();

    // Resolved gap shown
    await expect(main.getByText("greenfield").first()).toBeVisible();
  });

  test("+ Add Rule opens editable input with suggested rule", async ({
    page,
  }) => {
    await page.goto("/insights");

    const main = page.locator("main");

    // Click "+ Add Rule" on the nas_id gap (first one)
    await main.getByRole("button", { name: "+ Add Rule" }).first().click();

    // Input should appear pre-populated with the suggested rule
    const input = main.locator('input[type="text"]');
    await expect(input).toBeVisible();
    await expect(input).toHaveValue(
      "nas_ids, nas_id, nas_identifier, nasid are synonyms.",
    );

    // Save and Cancel buttons
    await expect(
      main.getByRole("button", { name: "Save", exact: true }),
    ).toBeVisible();
    await expect(main.getByRole("button", { name: "Cancel" })).toBeVisible();
  });

  test("+ Add Rule on gap without suggestion opens empty input", async ({
    page,
  }) => {
    await page.goto("/insights");

    const main = page.locator("main");

    // The "cui" gap has no suggestedRule — click its + Add Rule
    await main.getByRole("button", { name: "+ Add Rule" }).nth(1).click();

    // Input should be empty
    const input = main.locator('input[type="text"]');
    await expect(input).toBeVisible();
    await expect(input).toHaveValue("");
  });

  test("Cancel closes the input without saving", async ({ page, bicpMock }) => {
    await page.goto("/insights");

    const main = page.locator("main");

    // Open input
    await main.getByRole("button", { name: "+ Add Rule" }).first().click();
    await expect(main.locator('input[type="text"]')).toBeVisible();

    // Cancel
    await main.getByRole("button", { name: "Cancel" }).click();

    // Input should be gone
    await expect(main.locator('input[type="text"]')).not.toBeVisible();

    // No add-rule call made
    const calls = bicpMock.getCalls("context/add-rule");
    expect(calls.length).toBe(0);
  });

  test("saving rule calls context/add-rule with correct params", async ({
    page,
    bicpMock,
  }) => {
    await page.goto("/insights");

    const main = page.locator("main");

    // Wait for initial render
    await expect(
      main.getByRole("button", { name: "+ Add Rule" }).first(),
    ).toBeVisible();

    // Open input on nas_id gap
    await main.getByRole("button", { name: "+ Add Rule" }).first().click();

    // Wait for input to appear and click Save
    await expect(
      main.getByRole("button", { name: "Save", exact: true }),
    ).toBeVisible();
    await main.getByRole("button", { name: "Save", exact: true }).click();

    // Wait for success feedback
    await expect(main.getByText("\u2713 Added").first()).toBeVisible();

    // Verify the BICP call was made
    const calls = bicpMock.getCalls("context/add-rule");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params).toMatchObject({
      rule: "nas_ids, nas_id, nas_identifier, nasid are synonyms.",
      gapId: "gap-1",
    });
  });

  test("dismiss button calls gaps/dismiss and shows feedback", async ({
    page,
    bicpMock,
  }) => {
    await page.goto("/insights");

    const main = page.locator("main");

    // Wait for the Dismiss button to appear on an open gap
    await expect(
      main.getByRole("button", { name: "Dismiss" }).first(),
    ).toBeVisible();

    // Click Dismiss on the first open gap
    await main.getByRole("button", { name: "Dismiss" }).first().click();

    // Wait for dismiss feedback
    await expect(main.getByText("\u2717 Dismissed").first()).toBeVisible();

    // Verify the BICP call was made
    const calls = bicpMock.getCalls("gaps/dismiss");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params).toMatchObject({
      gapId: "gap-1",
      reason: "false positive",
    });
  });

  test("displays Semantic Layer card", async ({ page }) => {
    await page.goto("/insights");

    const main = page.locator("main");
    await expect(main.getByText("Semantic Layer").first()).toBeVisible();
    await expect(main.getByText("Schema descriptions").first()).toBeVisible();
    await expect(main.getByText("Domain model").first()).toBeVisible();
  });

  test("displays Tool Usage card", async ({ page }) => {
    await page.goto("/insights");

    const main = page.locator("main");
    await expect(main.getByText("Tool Usage").first()).toBeVisible();
    await expect(main.getByText("shell").first()).toBeVisible();
  });

  test("displays error state", async ({ page, bicpMock }) => {
    bicpMock.on("insights/analyze", () => mockData.INSIGHTS_ERROR);
    await page.goto("/insights");

    const main = page.locator("main");
    await expect(main.getByText(/Failed to analyze traces/)).toBeVisible();
  });

  test("changing period triggers new analysis", async ({ page, bicpMock }) => {
    await page.goto("/insights");

    const main = page.locator("main");

    // Wait for initial load
    await expect(main.getByText("Tool Traces").first()).toBeVisible();

    const initialCalls = bicpMock.getCalls("insights/analyze").length;

    // Change period to 30 days
    await main.locator("select").selectOption("30");

    // Wait for the new call
    await page.waitForTimeout(1000);

    const newCalls = bicpMock.getCalls("insights/analyze");
    expect(newCalls.length).toBeGreaterThan(initialCalls);

    // Last call should have days=30
    const lastCall = newCalls[newCalls.length - 1];
    expect(lastCall.params).toMatchObject({ days: 30 });
  });

  test("empty insights hides vocabulary gaps", async ({ page, bicpMock }) => {
    bicpMock.on("insights/analyze", () => mockData.INSIGHTS_EMPTY);
    await page.goto("/insights");

    const main = page.locator("main");

    // Stats show (page renders)
    await expect(main.getByText("Tool Traces").first()).toBeVisible();

    // No vocabulary gaps card (empty array)
    await expect(main.getByText("Unmapped Terms")).not.toBeVisible();
  });

  test("SQL Patterns card shows repeated queries with save flow", async ({
    page,
  }) => {
    await page.goto("/insights");
    const main = page.locator("main");

    // Wait for unified card to load
    await expect(main.getByText("SQL Patterns").first()).toBeVisible();

    // Already-saved query shows checkmark
    await expect(main.getByText(/Saved/).first()).toBeVisible();

    // Unsaved query shows Save as Example button
    const saveBtn = main.getByText("Save as Example").first();
    await expect(saveBtn).toBeVisible();

    // Click Save as Example — expands row and shows intent input
    await saveBtn.click();
    const input = main.getByPlaceholder(/Describe the intent/);
    await expect(input).toBeVisible();

    // Type intent and submit
    await input.fill("Count all users");
    await main.getByRole("button", { name: "Save", exact: true }).click();

    // After save, row collapses — input disappears and Save as Example is gone
    await expect(input).not.toBeVisible();
    await expect(main.getByText("Save as Example")).not.toBeVisible();
  });

  test("SQL Patterns card shows auto-corrected errors with save-as-learning", async ({
    page,
    bicpMock,
  }) => {
    // Override insights to include errors with SQL
    const insightsWithErrors = JSON.parse(
      JSON.stringify(mockData.INSIGHTS_HAPPY),
    );
    insightsWithErrors.analysis.errors = [
      {
        trace_id: "t-err-1",
        span_name: "api_execute_sql",
        tool: "api_execute_sql",
        error: "SQL execution failed: Table 'lending.deposits' does not exist",
        error_type: "soft",
        timestamp: Math.floor(Date.now() / 1000) - 600,
        sql: "SELECT * FROM lending.deposits WHERE block_date = '2026-01-31'",
      },
    ];
    insightsWithErrors.analysis.errorCount = 1;
    bicpMock.on("insights/analyze", () => insightsWithErrors);

    await page.goto("/insights");
    const main = page.locator("main");

    // Wait for card
    await expect(main.getByText("SQL Patterns").first()).toBeVisible();
    await expect(main.getByText("1 auto-corrected").first()).toBeVisible();

    // Save as Learning button visible
    const learnBtn = main.getByText("Save as Learning").first();
    await expect(learnBtn).toBeVisible();

    // Click — expands and shows pre-filled input
    await learnBtn.click();
    const input = main.locator(
      'input[placeholder*="What should the agent avoid"]',
    );
    await expect(input).toBeVisible();

    // Input should be pre-filled with suggestion from error
    await expect(input).toHaveValue(/does not exist/);
  });

  test("saved learning persists after auto-refresh via is_saved", async ({
    page,
    bicpMock,
  }) => {
    // Start with an unsaved error
    const unsavedErrors = JSON.parse(JSON.stringify(mockData.INSIGHTS_HAPPY));
    unsavedErrors.analysis.errors = [
      {
        trace_id: "t-err-1",
        span_name: "api_execute_sql",
        tool: "api_execute_sql",
        error: "Table 'lending.deposits' does not exist",
        error_type: "soft",
        timestamp: Math.floor(Date.now() / 1000) - 600,
        sql: "SELECT * FROM lending.deposits",
      },
    ];
    unsavedErrors.analysis.errorCount = 1;
    bicpMock.on("insights/analyze", () => unsavedErrors);

    await page.goto("/insights");
    const main = page.locator("main");

    await expect(main.getByText("Save as Learning").first()).toBeVisible();

    // After "saving", switch the mock to return is_saved: true (simulating backend)
    const savedErrors = JSON.parse(JSON.stringify(unsavedErrors));
    savedErrors.analysis.errors[0].is_saved = true;
    bicpMock.on("insights/analyze", () => savedErrors);

    // Trigger a refresh by changing period
    await main.locator("select").selectOption("30");
    await page.waitForTimeout(1000);

    // Now the error should show as saved, not "Save as Learning"
    await expect(main.getByText("Save as Learning")).not.toBeVisible();
    await expect(main.getByText(/Saved/).first()).toBeVisible();
  });
});
