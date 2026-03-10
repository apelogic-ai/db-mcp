import { test, expect, mockData } from "./fixtures";

test.describe("Config Page", () => {
  test("config page is agent-focused", async ({ page }) => {
    await page.goto("/config");

    await expect(page.getByRole("heading", { name: "Configuration" })).toBeVisible();
    await expect(page.getByText("Manage agent integration.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Open Connections" })).toBeVisible();

    await expect(page.getByText("Agent Configuration")).toBeVisible();
    await expect(page.getByText("Claude Desktop")).toBeVisible();

    await expect(page.getByText("Database Connections")).not.toBeVisible();
    await expect(page.getByText("File Connections")).not.toBeVisible();
    await expect(page.getByText("API Connections")).not.toBeVisible();
  });

  test("displays detected agents with action buttons", async ({ page }) => {
    await page.goto("/config");

    await expect(page.getByText("Agent Configuration")).toBeVisible();
    await expect(page.getByText("Claude Desktop")).toBeVisible();
    await expect(page.getByText("Claude Code")).toBeVisible();
    await expect(page.getByText("Codex CLI")).toBeVisible();

    const desktopRow = page.getByTestId("agent-claude-desktop");
    await expect(desktopRow.getByRole("button", { name: "Remove" })).toBeVisible();
    await expect(desktopRow.getByRole("button", { name: "Edit Config" })).toBeVisible();

    const codeRow = page.getByTestId("agent-claude-code");
    await expect(codeRow.getByRole("button", { name: "Add" })).toBeVisible();

    const codexRow = page.getByTestId("agent-codex");
    await expect(codexRow).toBeVisible();
    await expect(codexRow.getByRole("button", { name: "Add" })).not.toBeVisible();
  });

  test("add db-mcp to agent", async ({ page, bicpMock }) => {
    await page.goto("/config");

    const codeRow = page.getByTestId("agent-claude-code");
    await codeRow.getByRole("button", { name: "Add" }).click();

    const calls = bicpMock.getCalls("agents/configure");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params).toMatchObject({ agentId: "claude-code" });
  });

  test("remove db-mcp from agent", async ({ page, bicpMock }) => {
    await page.goto("/config");

    const desktopRow = page.getByTestId("agent-claude-desktop");
    await desktopRow.getByRole("button", { name: "Remove" }).click();

    const calls = bicpMock.getCalls("agents/remove");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params).toMatchObject({ agentId: "claude-desktop" });
  });

  test("edit config opens editor directly", async ({ page, bicpMock }) => {
    await page.goto("/config");

    const desktopRow = page.getByTestId("agent-claude-desktop");
    await desktopRow.getByRole("button", { name: "Edit Config" }).click();

    const editor = page.getByTestId("snippet-editor-claude-desktop");
    await expect(editor).toBeVisible();
    const value = await editor.inputValue();
    expect(value).toContain("db-mcp");

    await editor.fill(
      '{\n  "db-mcp": {\n    "command": "/new/path",\n    "args": ["start"]\n  }\n}',
    );
    await desktopRow.getByRole("button", { name: "Save" }).click();

    const calls = bicpMock.getCalls("agents/config-write");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    expect(calls[0].params?.agentId).toBe("claude-desktop");
    expect(calls[0].params?.snippet).toContain("/new/path");
  });

  test("edit config cancel closes editor", async ({ page }) => {
    await page.goto("/config");

    const desktopRow = page.getByTestId("agent-claude-desktop");
    await desktopRow.getByRole("button", { name: "Edit Config" }).click();
    await expect(page.getByTestId("snippet-editor-claude-desktop")).toBeVisible();

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

    const errorEl = page.getByTestId("save-error-claude-desktop");
    await expect(errorEl).toBeVisible();
    await expect(errorEl).toContainText("Invalid JSON");
  });

  test("empty agents list", async ({ page, bicpMock }) => {
    bicpMock.on("agents/list", () => mockData.AGENTS_LIST_EMPTY);
    await page.goto("/config");

    await expect(page.getByText("No agents detected.")).toBeVisible();
  });

  test("not-installed agents have no action buttons", async ({ page }) => {
    await page.goto("/config");

    const codexRow = page.getByTestId("agent-codex");
    await expect(codexRow.getByRole("button", { name: "Add" })).not.toBeVisible();
    await expect(codexRow.getByRole("button", { name: "Remove" })).not.toBeVisible();
    await expect(
      codexRow.getByRole("button", { name: "Edit Config" }),
    ).not.toBeVisible();
  });
});
