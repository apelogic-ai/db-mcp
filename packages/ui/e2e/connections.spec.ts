import { test, expect } from "./fixtures";

test.describe("Connections", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      const count = Number(window.sessionStorage.getItem("doc-load-count") || "0");
      window.sessionStorage.setItem("doc-load-count", String(count + 1));
    });
  });

  test("connections landing page opens the active connection workspace", async ({ page }) => {
    await page.goto("/connections");

    await expect(page).toHaveURL(/\/connection(\/production\/?|\?name=production)$/);
    await expect(page.getByRole("heading", { name: "Connections" })).toBeVisible();
    await expect(page.getByRole("link", { name: "production" })).toBeVisible();
    await expect(page.getByRole("link", { name: "staging" })).toBeVisible();
  });

  test("new connection wizard renders the three setup steps", async ({ page }) => {
    await page.goto("/connection/new#connect");

    await expect(page.getByRole("heading", { name: "Connections" })).toBeVisible();
    await expect(page.getByText("1. Connect and Test")).toBeVisible();
    await expect(page.getByText("2. Discover")).toBeVisible();
    await expect(page.getByText("3. Sample Data")).toBeVisible();
  });

  test("connect step shows the shared summary card and opens connector config editor", async ({
    page,
  }) => {
    await page.goto("/connection/new?name=production#connect");

    await expect(page.getByText("Status")).toBeVisible();
    await expect(page.getByText("Connect", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Discover", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Sample", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Edit" })).toBeVisible();

    await page.getByRole("button", { name: "Edit" }).click();

    await expect(page.getByText("Connection-specific configuration")).toBeVisible();
    await expect(page.locator("textarea")).toContainText("type: sql");
  });

  test("connect step can create connector.yaml when it does not exist", async ({
    page,
    bicpMock,
  }) => {
    let connectorExists = false;

    bicpMock.on("context/read", (params) => {
      if (params.path === "connector.yaml") {
        return connectorExists
          ? {
              success: true,
              content: "type: sql\ndatabase_url: postgresql://admin:s3cret@db.example.com:5432/analytics\n",
            }
          : { success: false, error: "not found" };
      }
      if (params.path === "schema/descriptions.yaml") {
        return { success: false, error: "not found" };
      }
      return { success: true, content: "", isStockReadme: false };
    });
    bicpMock.on("context/create", () => {
      connectorExists = true;
      return { success: true };
    });

    await page.goto("/connection/new?name=production#connect");

    await expect(page.getByRole("button", { name: "Create", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Create", exact: true }).click();

    await expect
      .poll(() => bicpMock.getLastCall("context/create")?.params?.path)
      .toBe("connector.yaml");
    await expect(page.locator("textarea")).toBeVisible();
  });

  test("connect step can create connector.yaml before the connection is saved", async ({
    page,
    bicpMock,
  }) => {
    let connectorExists = false;

    bicpMock.on("context/read", (params) => {
      if (params.connection === "top-ledger" && params.path === "connector.yaml") {
        return connectorExists
          ? {
              success: true,
              content: "type: sql\ndatabase_url: trino://user@host:8443/catalog\n",
            }
          : { success: false, error: "not found" };
      }
      return { success: false, error: "not found" };
    });
    bicpMock.on("context/create", (params) => {
      if (params.connection === "top-ledger" && params.path === "connector.yaml") {
        connectorExists = true;
      }
      return { success: true };
    });

    await page.goto("/connection/new#connect");
    await page.getByPlaceholder("my-connection").fill("top-ledger");
    await page
      .getByPlaceholder("trino://user:pass@host:443/catalog/schema")
      .fill("trino://user@host:8443/catalog");

    await expect(page.getByRole("button", { name: "Create", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Create", exact: true }).click();

    await expect
      .poll(() => bicpMock.getLastCall("context/create")?.params?.connection)
      .toBe("top-ledger");
    await expect(page.locator("textarea")).toBeVisible();
  });

  test("connect step tests draft sql connections with connector.yaml overrides", async ({
    page,
    bicpMock,
  }) => {
    let connectorExists = false;

    bicpMock.on("context/read", (params) => {
      if (params.connection === "top-ledger" && params.path === "connector.yaml") {
        return connectorExists
          ? {
              success: true,
              content:
                'type: sql\ndialect: trino\nconnect_args:\n  http_scheme: "http"\n  verify: false\n',
            }
          : { success: false, error: "not found" };
      }
      return { success: false, error: "not found" };
    });
    bicpMock.on("context/create", (params) => {
      if (params.connection === "top-ledger" && params.path === "connector.yaml") {
        connectorExists = true;
      }
      return { success: true };
    });
    bicpMock.on("connections/test", (params) => {
      if (
        params.databaseUrl === "trino://apegpt@84.32.32.87:8443/iceberg/solana" &&
        typeof params.connectArgs === "object"
      ) {
        return { success: true, message: "Connection successful", dialect: "trino" };
      }
      return { success: false, error: "Expected merged sql test payload" };
    });

    await page.goto("/connection/new#connect");
    await page.getByPlaceholder("my-connection").fill("top-ledger");
    await page
      .getByPlaceholder("trino://user:pass@host:443/catalog/schema")
      .fill("trino://apegpt@84.32.32.87:8443/iceberg/solana");

    await page.getByRole("button", { name: "Create", exact: true }).click();
    await expect(page.locator("textarea")).toBeVisible();

    await page.getByRole("button", { name: "Test", exact: true }).click();

    await expect
      .poll(() => bicpMock.getLastCall("connections/test")?.params?.databaseUrl)
      .toBe("trino://apegpt@84.32.32.87:8443/iceberg/solana");
    await expect(bicpMock.getLastCall("connections/test")?.params?.connectArgs).toEqual({
      http_scheme: "http",
      verify: false,
    });
    await expect(page.getByText("Connection successful")).toBeVisible();
  });

  test("connect step persists draft sql connections via update on next", async ({
    page,
    bicpMock,
  }) => {
    let connectorExists = false;

    bicpMock.on("context/read", (params) => {
      if (params.connection === "top-ledger" && params.path === "connector.yaml") {
        return connectorExists
          ? {
              success: true,
              content:
                "type: sql\n" +
                "database_url: trino://yaml-user@host:8443/catalog\n" +
                "capabilities:\n" +
                "  connect_args:\n" +
                '    http_scheme: "http"\n' +
                "    verify: false\n",
            }
          : { success: false, error: "not found" };
      }
      return { success: false, error: "not found" };
    });
    bicpMock.on("context/create", (params) => {
      if (params.connection === "top-ledger" && params.path === "connector.yaml") {
        connectorExists = true;
      }
      return { success: true };
    });
    bicpMock.on("connections/test", () => ({
      success: true,
      message: "Connection successful",
      dialect: "trino",
    }));

    await page.goto("/connection/new#connect");
    await page.getByPlaceholder("my-connection").fill("top-ledger");
    await page
      .getByPlaceholder("trino://user:pass@host:443/catalog/schema")
      .fill("trino://form-user@host:8443/catalog");

    await page.getByRole("button", { name: "Create", exact: true }).click();
    await expect(page.locator("textarea")).toBeVisible();

    await page.getByRole("button", { name: "Test", exact: true }).click();
    await expect(page.getByText("Connection successful")).toBeVisible();

    await page.getByRole("button", { name: /Next/ }).click();

    await expect
      .poll(() => bicpMock.getLastCall("connections/update")?.params?.name)
      .toBe("top-ledger");
    await expect(bicpMock.getLastCall("connections/update")?.params?.databaseUrl).toBe(
      "trino://yaml-user@host:8443/catalog",
    );
  });

  test("discover step hydrates existing schema state for saved connections", async ({
    page,
    bicpMock,
  }) => {
    bicpMock.on("context/read", (params) => {
      if (params.path === "schema/descriptions.yaml") {
        return {
          success: true,
          content: `version: 1.0.0
provider_id: production
dialect: sqlite
generated_at: '2026-03-04T22:09:39.143977Z'
tables:
- name: Album
  schema: main
  catalog: null
  full_name: main.Album
  description: null
  status: pending
- name: Artist
  schema: main
  catalog: null
  full_name: main.Artist
  description: null
  status: pending
`,
        };
      }
      return { success: false, error: "not found" };
    });

    await page.goto("/connection/new?name=production#discover");

    await expect(page.getByRole("button", { name: "Re-discover" })).toBeVisible();
    await expect(page.getByText("Loaded existing schema snapshot")).toBeVisible();
    await expect(page.getByText("Found 1 schema")).toBeVisible();
    await expect(page.getByText("2 tables", { exact: true })).toBeVisible();
  });

  test("discover step persists discovered schema for saved connections", async ({
    page,
    bicpMock,
  }) => {
    await page.goto("/connection/new?name=production#discover");

    await page.getByRole("button", { name: "Discover", exact: true }).click();

    await expect
      .poll(() => bicpMock.getLastCall("connections/save-discovery")?.params?.name)
      .toBe("production");
  });

  test("sample step uses clicked table selection without null qualifiers", async ({
    page,
    bicpMock,
  }) => {
    bicpMock.on("schema/catalogs", () => ({
      success: true,
      catalogs: [null],
    }));
    bicpMock.on("schema/schemas", () => ({
      success: true,
      schemas: [{ name: "main", catalog: null, tableCount: 1 }],
    }));
    bicpMock.on("schema/tables", () => ({
      success: true,
      tables: [{ name: "Album", description: "Albums" }],
    }));
    bicpMock.on("schema/columns", () => ({
      success: true,
      columns: [{ name: "AlbumId", type: "INTEGER", nullable: false, description: null, isPrimaryKey: true }],
    }));

    await page.goto("/connection/new?name=production#sample");

    await expect(page.locator('[data-path="__default__/main"]')).toBeVisible();
    await page.locator('[data-path="__default__/main"]').click({ force: true });
    await expect(page.locator('[data-path="__default__/main/Album"]')).toBeVisible();
    await page.locator('[data-path="__default__/main/Album"]').click({ force: true });
    await expect(page.getByText("select * from main.Album limit 5;")).toBeVisible();

    await page.getByRole("button", { name: "Sample Data", exact: true }).click();
    await expect(page.getByText("Sampled 2 rows from main.public.users")).toBeVisible();
    await expect(page.getByText("Method not found")).toHaveCount(0);
    await expect
      .poll(() => bicpMock.getLastCall("connections/complete-onboarding")?.params?.name)
      .toBe("production");
  });

  test("connection detail route opens the overview shell", async ({ page }) => {
    await page.goto("/connection?name=production");

    await expect(page.getByRole("link", { name: "production" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Overview" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Insights" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Knowledge" })).toBeVisible();
    await expect(page.getByText("Recommended Actions")).toBeVisible();
  });

  test("connection insights route renders scoped insights", async ({ page }) => {
    await page.goto("/connection/insights?name=production");

    await expect(page.getByRole("link", { name: "production" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Insights" })).toBeVisible();
    await expect(page.getByText("Semantic Layer")).toBeVisible();
  });

  test("connection knowledge route renders scoped knowledge", async ({ page }) => {
    await page.goto("/connection/knowledge?name=production");

    await expect(page.getByRole("link", { name: "production" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Knowledge", exact: true })).toBeVisible();
    await expect(page.getByText("Knowledge Vault")).toBeVisible();
    await expect(page.getByText("Select a file from the tree to view or edit.")).toBeVisible();
  });

  test("drawer selection switches connections", async ({ page }) => {
    await page.goto("/connection?name=production");

    await page.getByRole("link", { name: "staging" }).click();
    await expect(page).toHaveURL(/\/connection\/(staging\/?)?(\?name=staging)?$/);
  });

  test("action menu routes completed connections to re-configure", async ({ page }) => {
    await page.goto("/connection?name=production");

    await page.getByRole("button", { name: "Connection actions" }).click();
    await page.getByRole("link", { name: "Re-configure" }).click();

    await expect(page).toHaveURL(/\/connection\/new\/\?name=production#sample$/);
  });

  test("action menu shows configure for incomplete connections", async ({ page }) => {
    await page.goto("/connection?name=staging");

    await page.getByRole("button", { name: "Connection actions" }).click();
    await expect(page.getByRole("link", { name: "Configure" })).toBeVisible();
  });

  test("action menu duplicates the current connection", async ({ page, bicpMock }) => {
    let connectionsList = {
      connections: [
        {
          name: "production",
          isActive: true,
          hasSchema: true,
          hasDomain: true,
          hasCredentials: true,
          dialect: "postgresql",
          onboardingPhase: "complete",
          connectorType: "sql",
        },
        {
          name: "staging",
          isActive: false,
          hasSchema: true,
          hasDomain: false,
          hasCredentials: true,
          dialect: "clickhouse",
          onboardingPhase: "review",
          connectorType: "sql",
        },
      ],
      activeConnection: "production",
    };

    bicpMock.on("connections/list", () => connectionsList);
    bicpMock.on("connections/get", (params) => {
      const requestedName = params.name as string;
      return {
        success: true,
        name: requestedName,
        connectorType: "sql",
        databaseUrl: "postgresql://admin:s3cret@db.example.com:5432/analytics",
      };
    });
    bicpMock.on("connections/create", (params) => {
      const copyName = params.name as string;
      connectionsList = {
        ...connectionsList,
        connections: [
          ...connectionsList.connections,
          {
            name: copyName,
            isActive: false,
            hasSchema: true,
            hasDomain: true,
            hasCredentials: true,
            dialect: "postgresql",
            onboardingPhase: "complete",
            connectorType: "sql",
          },
        ],
      };
      return { success: true, name: copyName, dialect: "postgresql" };
    });

    await page.goto("/connection?name=production");
    await page.getByRole("button", { name: "Connection actions" }).click();
    await page.getByRole("button", { name: "Duplicate" }).click();

    await expect(page).toHaveURL(/\/connection\/(production-copy\/?)?(\?name=production-copy)?$/);
    await expect
      .poll(() => bicpMock.getLastCall("connections/create")?.params?.name)
      .toBe("production-copy");
  });

  test("action menu delete confirms before removing the connection", async ({ page, bicpMock }) => {
    let connectionsList = {
      connections: [
        {
          name: "production",
          isActive: true,
          hasSchema: true,
          hasDomain: true,
          hasCredentials: true,
          dialect: "postgresql",
          onboardingPhase: "complete",
          connectorType: "sql",
        },
        {
          name: "staging",
          isActive: false,
          hasSchema: true,
          hasDomain: false,
          hasCredentials: true,
          dialect: "clickhouse",
          onboardingPhase: "review",
          connectorType: "sql",
        },
      ],
      activeConnection: "production",
    };

    bicpMock.on("connections/list", () => connectionsList);
    bicpMock.on("connections/delete", (params) => {
      const deletedName = params.name as string;
      connectionsList = {
        connections: connectionsList.connections.filter((connection) => connection.name !== deletedName),
        activeConnection: "staging",
      };
      return { success: true };
    });

    await page.goto("/connection?name=production");
    await page.getByRole("button", { name: "Connection actions" }).click();
    await page.getByRole("button", { name: "Delete" }).click();

    await expect(page.getByText("Delete connection?")).toBeVisible();
    await page.getByRole("button", { name: "Delete connection" }).click();

    await expect(page).toHaveURL(/\/connection\/(staging\/?)?(\?name=staging)?$/);
    await expect
      .poll(() => bicpMock.getLastCall("connections/delete")?.params?.name)
      .toBe("production");
  });
});
