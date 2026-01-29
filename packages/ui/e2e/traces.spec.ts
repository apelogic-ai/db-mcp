import { test, expect, mockData } from "./fixtures";

test.describe("Traces Page", () => {
  test("renders page header and day sections", async ({ page }) => {
    await page.goto("/traces");

    const main = page.locator("main");
    await expect(main.getByRole("heading", { name: "Traces" })).toBeVisible();
    await expect(
      main.getByText("OpenTelemetry trace viewer for MCP server operations"),
    ).toBeVisible();

    // Today section is auto-expanded
    await expect(main.getByText("Today")).toBeVisible();
  });

  test("displays trace rows with tool name and metadata", async ({
    page,
    bicpMock,
  }) => {
    bicpMock.on("traces/list", () => mockData.TRACES_SIMPLE);
    await page.goto("/traces");

    const main = page.locator("main");

    // Wait for traces to render
    await expect(main.getByText("get_data")).toBeVisible();
    await expect(main.getByText("validate_sql")).toBeVisible();
    await expect(main.getByText("shell")).toBeVisible();

    // SQL preview shown as highlight
    await expect(main.getByText("SELECT * FROM users LIMIT 10")).toBeVisible();

    // Shell command shown as highlight
    await expect(main.getByText("cat schema/descriptions.yaml")).toBeVisible();
  });

  test("expand trace shows span timeline", async ({ page, bicpMock }) => {
    bicpMock.on("traces/list", () => mockData.TRACES_SIMPLE);
    await page.goto("/traces");

    const main = page.locator("main");
    // Click on the get_data trace row
    await main.getByText("get_data").click();

    // SpanTimeline renders span duration labels (e.g. "1200.0ms")
    await expect(main.getByText("1200.0ms")).toBeVisible();
  });

  test("groups consecutive get_result traces and expands on click", async ({
    page,
    bicpMock,
  }) => {
    bicpMock.on("traces/list", () => mockData.TRACES_WITH_POLLING);
    await page.goto("/traces");

    const main = page.locator("main");

    // The 5 consecutive get_result traces should be grouped into one row
    await expect(main.getByText("\u00d75")).toBeVisible(); // ×5

    // The other individual traces should still be visible
    await expect(main.getByText("execute_query")).toBeVisible();
    await expect(main.getByText("run_sql")).toBeVisible();
    await expect(main.getByText("validate_sql")).toBeVisible();

    // Click the grouped row (the one with ×5) to expand it
    await main.getByRole("button", { name: /get_result.*×5/ }).click();

    // Individual trace durations should now be visible inside the expanded group
    await expect(main.getByText("0.2ms").first()).toBeVisible();
  });

  test("hides protocol noise traces", async ({ page, bicpMock }) => {
    bicpMock.on("traces/list", () => mockData.TRACES_WITH_NOISE);
    await page.goto("/traces");

    const main = page.locator("main");

    // Real trace should be visible
    await expect(main.getByText("get_data")).toBeVisible();

    // Noise traces should be hidden
    await expect(main.getByText("tools/list")).not.toBeVisible();
    await expect(main.getByText("initialize")).not.toBeVisible();

    // Hidden count message
    await expect(main.getByText(/2 protocol traces hidden/)).toBeVisible();
  });

  test("empty state when no traces", async ({ page, bicpMock }) => {
    bicpMock.on("traces/list", () => mockData.TRACES_EMPTY);
    await page.goto("/traces");

    await expect(page.getByText("No traces found")).toBeVisible();
  });

  test("refresh button reloads traces", async ({ page, bicpMock }) => {
    bicpMock.on("traces/list", () => mockData.TRACES_SIMPLE);
    await page.goto("/traces");

    const main = page.locator("main");
    await expect(main.getByText("get_data")).toBeVisible();

    // Click refresh
    await page.getByTitle("Refresh traces").click();

    // Verify traces/list was called multiple times
    const calls = bicpMock.getCalls("traces/list");
    expect(calls.length).toBeGreaterThanOrEqual(2);
  });

  test("clear live traces button works", async ({ page, bicpMock }) => {
    bicpMock.on("traces/list", () => mockData.TRACES_SIMPLE);
    await page.goto("/traces");

    const main = page.locator("main");
    await expect(main.getByText("get_data")).toBeVisible();

    // Click clear button
    await page.getByTitle("Clear live traces").click();

    // Verify clear was called
    const calls = bicpMock.getCalls("traces/clear");
    expect(calls.length).toBeGreaterThanOrEqual(1);
  });
});
