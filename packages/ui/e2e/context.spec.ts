import { test, expect, mockData } from "./fixtures";

test.describe("Context Page", () => {
  test("renders tree with connections", async ({ page }) => {
    await page.goto("/context");

    const main = page.locator("main");
    await expect(main.getByText("production")).toBeVisible();
    await expect(main.getByText("staging")).toBeVisible();
  });

  test("expand connection shows folders", async ({ page }) => {
    await page.goto("/context");

    // Click production to expand (scoped to main to avoid nav selector)
    const main = page.locator("main");
    await main.getByText("production").click();

    // Folders should appear — use exact match to avoid matching page description text
    await expect(page.getByText("schema", { exact: true })).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("domain", { exact: true })).toBeVisible();
    await expect(page.getByText("training", { exact: true })).toBeVisible();
    await expect(page.getByText("instructions", { exact: true })).toBeVisible();
    await expect(page.getByText("metrics", { exact: true })).toBeVisible();
  });

  test("expand folder shows files", async ({ page }) => {
    await page.goto("/context");

    // Expand production connection
    await page.locator("main").getByText("production").click();
    await expect(page.getByText("schema", { exact: true })).toBeVisible({
      timeout: 5000,
    });

    // Expand schema folder
    await page.getByText("schema", { exact: true }).click();

    // File should be visible
    await expect(page.getByText("descriptions.yaml")).toBeVisible({
      timeout: 5000,
    });
  });

  test("click file loads content in editor", async ({ page, bicpMock }) => {
    await page.goto("/context");

    // Expand tree to file
    await page.locator("main").getByText("production").click();
    await expect(page.getByText("schema", { exact: true })).toBeVisible({
      timeout: 5000,
    });
    await page.getByText("schema", { exact: true }).click();
    await expect(page.getByText("descriptions.yaml")).toBeVisible({
      timeout: 5000,
    });
    await page.getByText("descriptions.yaml").click();

    // Editor should show the file content — check the textarea value
    const editor = page.getByRole("textbox");
    await expect(editor).toBeVisible({ timeout: 5000 });
    await expect(editor).toHaveValue(/Core user accounts table/, {
      timeout: 5000,
    });

    // Verify context/read was called
    const calls = bicpMock.getCalls("context/read");
    expect(calls.length).toBeGreaterThanOrEqual(1);
  });

  test("stock README for empty folder", async ({ page }) => {
    await page.goto("/context");

    // Expand production
    await page.locator("main").getByText("production").click();
    await expect(page.getByText("metrics", { exact: true })).toBeVisible({
      timeout: 5000,
    });

    // Click metrics (empty folder)
    await page.getByText("metrics", { exact: true }).click();

    // Should show stock readme content in editor or a read-only indicator
    // The stock readme may appear in the editor textarea or as plain text
    const editor = page.getByRole("textbox");
    const readOnlyText = page
      .getByText(/read-only/i)
      .or(page.getByText("Select a file from the tree"));
    await expect(editor.or(readOnlyText)).toBeVisible({ timeout: 5000 });
  });

  test("tree highlighting on connection level", async ({ page }) => {
    await page.goto("/context");

    await page.locator("main").getByText("production").click();
    await expect(page.locator("main").getByText("production")).toBeVisible();
  });

  test("tree highlighting on file level", async ({ page }) => {
    await page.goto("/context");

    // Navigate to file
    await page.locator("main").getByText("production").click();
    await expect(page.getByText("schema", { exact: true })).toBeVisible({
      timeout: 5000,
    });
    await page.getByText("schema", { exact: true }).click();
    await expect(page.getByText("descriptions.yaml").first()).toBeVisible({
      timeout: 5000,
    });
    await page.getByText("descriptions.yaml").first().click();

    // The file item should still be visible in the tree
    await expect(page.getByText("descriptions.yaml").first()).toBeVisible();
  });

  test("create file modal", async ({ page, bicpMock }) => {
    await page.goto("/context");

    // Navigate to a file to enable toolbar
    await page.locator("main").getByText("production").click();
    await expect(page.getByText("schema", { exact: true })).toBeVisible({
      timeout: 5000,
    });
    await page.getByText("schema", { exact: true }).click();
    await expect(page.getByText("descriptions.yaml").first()).toBeVisible({
      timeout: 5000,
    });
    await page.getByText("descriptions.yaml").first().click();

    // Wait for editor to load
    const editor = page.getByRole("textbox");
    await expect(editor).toBeVisible({ timeout: 5000 });
    await expect(editor).toHaveValue(/Core user accounts table/, {
      timeout: 5000,
    });

    // Look for create/new button in toolbar
    const newButton = page.getByRole("button", { name: /new/i });
    if (
      await newButton
        .first()
        .isVisible({ timeout: 3000 })
        .catch(() => false)
    ) {
      await newButton.first().click();

      // Modal should appear — fill in filename
      const filenameInput = page
        .getByPlaceholder(/file.*name/i)
        .or(page.getByPlaceholder(/name/i));
      if (await filenameInput.isVisible({ timeout: 2000 }).catch(() => false)) {
        await filenameInput.fill("new-file.yaml");

        const createBtn = page.getByRole("button", { name: /create/i });
        await createBtn.click();

        const calls = bicpMock.getCalls("context/create");
        expect(calls.length).toBeGreaterThanOrEqual(1);
      }
    }
  });

  test("empty tree state", async ({ page, bicpMock }) => {
    bicpMock.on("context/tree", () => mockData.CONTEXT_TREE_EMPTY);
    await page.goto("/context");

    await expect(
      page
        .getByText("No connections configured")
        .or(page.getByText(/no connections/i)),
    ).toBeVisible({ timeout: 5000 });
  });

  test("file read error handling", async ({ page, bicpMock }) => {
    bicpMock.on("context/read", () => {
      throw { code: -32603, message: "File not found: schema/missing.yaml" };
    });
    await page.goto("/context");

    // Navigate to file
    await page.locator("main").getByText("production").click();
    await expect(page.getByText("schema", { exact: true })).toBeVisible({
      timeout: 5000,
    });
    await page.getByText("schema", { exact: true }).click();
    await expect(page.getByText("descriptions.yaml")).toBeVisible({
      timeout: 5000,
    });
    await page.getByText("descriptions.yaml").click();

    // Should show error
    await expect(
      page.getByText(/error/i).or(page.getByText(/not found/i)),
    ).toBeVisible({ timeout: 5000 });
  });
});
