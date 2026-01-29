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

  test("displays Knowledge Flow Insights card", async ({ page }) => {
    await page.goto("/insights");

    const main = page.locator("main");
    await expect(
      main.getByText("Knowledge Flow Insights").first(),
    ).toBeVisible();
    await expect(
      main.getByText("Are there SQL mistakes?").first(),
    ).toBeVisible();
    await expect(
      main.getByText("Are we capturing new knowledge?").first(),
    ).toBeVisible();
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
    await expect(main.getByRole("button", { name: "Save" })).toBeVisible();
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
    await expect(main.getByRole("button", { name: "Save" })).toBeVisible();
    await main.getByRole("button", { name: "Save" }).click();

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
});
