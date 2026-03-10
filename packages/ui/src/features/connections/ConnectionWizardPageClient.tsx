"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { SchemaExplorer } from "@/components/context/SchemaExplorer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useBICP } from "@/lib/bicp-context";
import { useConnections } from "@/lib/connection-context";
import type {
  ConnectionGetResult,
  ConnectionTestStatus,
  ConnectorType,
  CreateResult,
  DiscoverySummary,
  SampleTableResult,
  TestResult,
  UpdateResult,
  WizardStep,
} from "./types";
import { ConnectionStatusSteps } from "./ConnectionStatusSteps";
import { ConnectionWorkspaceShell } from "./ConnectionWorkspaceShell";
import {
  WIZARD_STEPS,
  buildWizardHref,
  formatTableTarget,
  getConnectionOnboardingTone,
  getPersistedWizardStatuses,
  inferDialect,
  maskDatabaseUrl,
  normalizeDbSegment,
  parseConnectArgsFromUrl,
  parseDbLink,
  parseSqlConnectorOverrides,
  wizardStepFromHash,
} from "./utils";

type TableSelection = {
  catalog: string | null;
  schema: string | null;
  table: string | null;
};

type ParsedSchemaTable = {
  catalog: string | null;
  schema: string | null;
  table: string | null;
};

type DiscoveredTablePayload = {
  catalog: string | null;
  schema: string | null;
  table: string;
  full_name: string;
  columns: Array<{
    name: string;
    type: string | null;
  }>;
};

type ContextReadResult = {
  success: boolean;
  content?: string;
  error?: string;
};

type ContextWriteResult = {
  success: boolean;
  error?: string;
};

type ContextCreateResult = {
  success: boolean;
  error?: string;
};

function parseYamlScalar(value: string): string | null {
  const trimmed = value.trim().replace(/^['"]|['"]$/g, "");
  return normalizeDbSegment(trimmed);
}

function pluralize(label: string, count: number): string {
  return `${label}${count === 1 ? "" : "s"}`;
}

function formatDiscoveryScope(catalog: string | null, schema: string | null): string {
  const parts = [normalizeDbSegment(catalog), normalizeDbSegment(schema)].filter(Boolean);
  return parts.length > 0 ? parts.join(".") : "default schema";
}

function parseExistingSchemaSnapshot(content: string, connectorType: ConnectorType): DiscoverySummary | null {
  const lines = content.split(/\r?\n/);
  const tables: ParsedSchemaTable[] = [];
  let generatedAt: string | null = null;
  let currentTable: ParsedSchemaTable | null = null;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\t/g, "  ");

    const generatedAtMatch = line.match(/^generated_at:\s*(.+)$/);
    if (generatedAtMatch) {
      generatedAt = parseYamlScalar(generatedAtMatch[1]);
      continue;
    }

    const tableMatch = line.match(/^- name:\s*(.+)$/);
    if (tableMatch) {
      if (currentTable?.table) {
        tables.push(currentTable);
      }
      currentTable = {
        catalog: null,
        schema: null,
        table: parseYamlScalar(tableMatch[1]),
      };
      continue;
    }

    if (!currentTable) {
      continue;
    }

    const schemaMatch = line.match(/^  schema:\s*(.+)$/);
    if (schemaMatch) {
      currentTable.schema = parseYamlScalar(schemaMatch[1]);
      continue;
    }

    const catalogMatch = line.match(/^  catalog:\s*(.+)$/);
    if (catalogMatch) {
      currentTable.catalog = parseYamlScalar(catalogMatch[1]);
    }
  }

  if (currentTable?.table) {
    tables.push(currentTable);
  }

  if (tables.length === 0) {
    return null;
  }

  const catalogs = new Set(
    tables.map((table) => normalizeDbSegment(table.catalog)).filter((value): value is string => Boolean(value)),
  );
  const schemas = new Set(
    tables.map((table) => normalizeDbSegment(table.schema)).filter((value): value is string => Boolean(value)),
  );

  const logs: string[] = [];
  logs.push(generatedAt ? `Loaded existing schema snapshot from ${generatedAt}.` : "Loaded existing schema snapshot.");
  if (catalogs.size > 0) {
    logs.push(`Found ${catalogs.size} ${pluralize("catalog", catalogs.size)}`);
  }
  logs.push(`Found ${schemas.size} ${pluralize("schema", schemas.size)}`);
  logs.push(`Found ${tables.length} ${pluralize("table", tables.length)}`);

  return {
    status: "success",
    connectorType,
    catalogCount: catalogs.size > 0 ? catalogs.size : undefined,
    schemaCount: schemas.size,
    tableCount: tables.length,
    sampleTargets: tables.slice(0, 16).map((table) => ({
      catalog: table.catalog,
      schema: table.schema,
      table: table.table,
      label: formatTableTarget(table),
    })),
    logs,
    errors: [],
  };
}

function hasDiscoveryData(state: DiscoverySummary): boolean {
  return Boolean(
    state.sampleTargets?.length ||
      state.endpoints?.length ||
      state.catalogCount !== undefined ||
      state.schemaCount !== undefined ||
      state.tableCount !== undefined ||
      state.endpointCount !== undefined ||
      state.logs.length,
  );
}

function buildConnectorConfigTemplate(options: {
  connectorType: ConnectorType;
  databaseUrl: string;
  directory: string;
  baseUrl: string;
  apiAuthType: string;
  apiTokenEnv: string;
  apiHeaderName: string;
}): string {
  if (options.connectorType === "file") {
    return [
      "type: file",
      "profile: file_local",
      `directory: ${options.directory || "/path/to/data"}`,
      "",
    ].join("\n");
  }

  if (options.connectorType === "api") {
    const lines = [
      "type: api",
      `base_url: ${options.baseUrl || "https://api.example.com/v1"}`,
      "auth:",
      `  type: ${options.apiAuthType || "bearer"}`,
      `  token_env: ${options.apiTokenEnv || "API_KEY"}`,
    ];

    if (options.apiAuthType === "header" && options.apiHeaderName) {
      lines.push(`  header_name: ${options.apiHeaderName}`);
    }

    lines.push(
      "rate_limit:",
      "  requests_per_second: 10.0",
      "pagination:",
      "  type: none",
      "endpoints: []",
      "",
    );
    return lines.join("\n");
  }

  return [
    "type: sql",
    `database_url: ${options.databaseUrl || "postgresql://user:password@host:5432/database"}`,
    "",
  ].join("\n");
}

function summarizeDiscoveryStatus(
  state: DiscoverySummary,
  connection: {
    onboardingPhase?: string | null;
    hasSchema?: boolean;
    hasDiscovery?: boolean;
    hasDomain?: boolean;
    hasCredentials?: boolean;
    connectorType?: ConnectorType;
  } | null,
): DiscoverySummary["status"] {
  if (state.status !== "idle" || hasDiscoveryData(state)) {
    return state.status;
  }

  if (!connection) {
    return "idle";
  }

  const persistedStatuses = getPersistedWizardStatuses({
    onboardingPhase: connection.onboardingPhase ?? null,
    hasSchema: connection.hasSchema ?? false,
    hasDiscovery: connection.hasDiscovery ?? false,
    hasDomain: connection.hasDomain ?? false,
    hasCredentials: connection.hasCredentials ?? false,
    connectorType: connection.connectorType ?? "sql",
  });
  if (persistedStatuses.discover === "done") {
    return "success";
  }
  if (persistedStatuses.discover === "active") {
    return "partial";
  }
  return "idle";
}

export function ConnectionWizardPageClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isInitialized, call } = useBICP();
  const { connections, refreshConnections, switchConnection } = useConnections();

  const existingName = searchParams.get("name");
  const initialType = (searchParams.get("type") as ConnectorType | null) || "sql";

  const [step, setStep] = useState<WizardStep>("connect");
  const [connectorType, setConnectorType] = useState<ConnectorType>(initialType);
  const [connectionName, setConnectionName] = useState(existingName || "");
  const [databaseUrl, setDatabaseUrl] = useState("");
  const [displayDatabaseUrl, setDisplayDatabaseUrl] = useState("");
  const [directory, setDirectory] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiAuthType, setApiAuthType] = useState("bearer");
  const [apiTokenEnv, setApiTokenEnv] = useState("");
  const [apiHeaderName, setApiHeaderName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [resolvedDialect, setResolvedDialect] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<ConnectionTestStatus | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [discoverState, setDiscoverState] = useState<DiscoverySummary>({
    status: "idle",
    connectorType: initialType,
    logs: [],
    errors: [],
  });
  const [sampleSelection, setSampleSelection] = useState<TableSelection>({
    catalog: null,
    schema: null,
    table: null,
  });
  const [sampleLoading, setSampleLoading] = useState(false);
  const [sampleError, setSampleError] = useState<string | null>(null);
  const [sampleRows, setSampleRows] = useState<Array<Record<string, unknown>>>([]);
  const [sampleLogs, setSampleLogs] = useState<string[]>([]);
  const [selectedEndpoint, setSelectedEndpoint] = useState<string | null>(null);
  const [connectorConfigExists, setConnectorConfigExists] = useState(false);
  const [connectorConfigOpen, setConnectorConfigOpen] = useState(false);
  const [connectorConfigLoading, setConnectorConfigLoading] = useState(false);
  const [connectorConfigSaving, setConnectorConfigSaving] = useState(false);
  const [connectorConfigError, setConnectorConfigError] = useState<string | null>(null);
  const [connectorConfigContent, setConnectorConfigContent] = useState("");
  const [connectorConfigOriginal, setConnectorConfigOriginal] = useState("");

  const currentName = existingName || connectionName.trim();
  const currentConnection = useMemo(
    () => connections.find((connection) => connection.name === currentName) || null,
    [connections, currentName],
  );
  const canManageConnectorConfig = Boolean(currentName);
  const connectorConfigDirty = connectorConfigContent !== connectorConfigOriginal;
  const sqlConnectorOverrides = useMemo(
    () =>
      connectorType === "sql" && connectorConfigExists
        ? parseSqlConnectorOverrides(connectorConfigContent || connectorConfigOriginal)
        : {},
    [connectorConfigContent, connectorConfigExists, connectorConfigOriginal, connectorType],
  );

  useEffect(() => {
    const syncStep = () => {
      const nextStep = wizardStepFromHash(window.location.hash);
      if (!existingName && nextStep !== "connect") {
        setStep("connect");
        window.history.replaceState(null, "", buildWizardHref("connect", { type: connectorType }));
        return;
      }
      setStep(nextStep);
    };

    syncStep();
    window.addEventListener("hashchange", syncStep);
    return () => window.removeEventListener("hashchange", syncStep);
  }, [connectorType, existingName]);

  useEffect(() => {
    setConnectorType(initialType);
    setDiscoverState((prev) => ({ ...prev, connectorType: initialType }));
  }, [initialType]);

  const hydrateExistingDiscoveryState = useCallback(
    async (
      name: string,
      type: ConnectorType,
      endpoints?: Array<{ name: string; path: string; method: string }>,
    ) => {
      if (!isInitialized) {
        return;
      }

      if (type === "api") {
        if (!endpoints?.length) {
          return;
        }
        setSelectedEndpoint((prev) => prev || endpoints[0]?.name || null);
        setDiscoverState({
          status: "success",
          connectorType: type,
          endpointCount: endpoints.length,
          endpoints: endpoints.map((endpoint) => ({
            name: endpoint.name,
            path: endpoint.path,
          })),
          logs: [`Loaded ${endpoints.length} saved ${pluralize("endpoint", endpoints.length)}.`],
          errors: [],
        });
        return;
      }

      try {
        const result = await call<{ success: boolean; content?: string; error?: string }>("context/read", {
          connection: name,
          path: "schema/descriptions.yaml",
        });

        if (!result.success || !result.content) {
          return;
        }

        const snapshot = parseExistingSchemaSnapshot(result.content, type);
        if (!snapshot) {
          return;
        }

        setDiscoverState(snapshot);
        const firstTarget = snapshot.sampleTargets?.[0];
        if (firstTarget?.table) {
          setSampleSelection({
            catalog: firstTarget.catalog || null,
            schema: firstTarget.schema || null,
            table: firstTarget.table || null,
          });
        }
      } catch {
        // Best-effort hydration only.
      }
    },
    [call, isInitialized],
  );

  const loadExistingConnection = useCallback(async () => {
    if (!isInitialized || !existingName) {
      return;
    }

    try {
      const result = await call<ConnectionGetResult>("connections/get", {
        name: existingName,
      });
      if (!result.success) {
        setFormError(result.error || "Failed to load connection");
        return;
      }

      const type = result.connectorType || "sql";
      setConnectorType(type);
      setConnectionName(existingName);
      setDatabaseUrl(result.databaseUrl || "");
      setDisplayDatabaseUrl(maskDatabaseUrl(result.databaseUrl || ""));
      setDirectory(result.directory || "");
      setBaseUrl(result.baseUrl || "");
      setApiAuthType(result.auth?.type || "bearer");
      setApiTokenEnv(result.auth?.tokenEnv || "");
      setApiHeaderName(result.auth?.headerName || "");
      setResolvedDialect(inferDialect(type, { databaseUrl: result.databaseUrl }));

      await switchConnection(existingName);
      await hydrateExistingDiscoveryState(existingName, type, result.endpoints);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to load connection");
    }
  }, [call, existingName, hydrateExistingDiscoveryState, isInitialized, switchConnection]);

  useEffect(() => {
    loadExistingConnection();
  }, [loadExistingConnection]);

  useEffect(() => {
    if (!existingName || !currentConnection || !isInitialized) {
      return;
    }

    if (hasDiscoveryData(discoverState)) {
      return;
    }

    hydrateExistingDiscoveryState(existingName, connectorType);
  }, [
    connectorType,
    currentConnection,
    discoverState,
    existingName,
    hydrateExistingDiscoveryState,
    isInitialized,
  ]);

  const refreshConnectorConfigState = useCallback(async () => {
    if (!isInitialized || !currentName || !canManageConnectorConfig) {
      setConnectorConfigExists(false);
      setConnectorConfigOpen(false);
      setConnectorConfigContent("");
      setConnectorConfigOriginal("");
      return;
    }

    try {
      const result = await call<ContextReadResult>("context/read", {
        connection: currentName,
        path: "connector.yaml",
      });

      if (!result.success) {
        setConnectorConfigExists(false);
        if (!connectorConfigOpen) {
          setConnectorConfigContent("");
          setConnectorConfigOriginal("");
        }
        return;
      }

      const nextContent = result.content || "";
      setConnectorConfigExists(true);
      if (!connectorConfigOpen || !connectorConfigDirty) {
        setConnectorConfigContent(nextContent);
        setConnectorConfigOriginal(nextContent);
      }
    } catch {
      setConnectorConfigExists(false);
    }
  }, [
    call,
    canManageConnectorConfig,
    connectorConfigDirty,
    connectorConfigOpen,
    currentName,
    isInitialized,
  ]);

  useEffect(() => {
    refreshConnectorConfigState();
  }, [refreshConnectorConfigState]);

  const openConnectorConfigEditor = useCallback(async () => {
    if (!currentName) {
      setConnectorConfigError("Enter a connection name before editing connector.yaml.");
      return;
    }

    setConnectorConfigError(null);
    setConnectorConfigLoading(true);

    try {
      if (!connectorConfigExists) {
        const template = buildConnectorConfigTemplate({
          connectorType,
          databaseUrl,
          directory,
          baseUrl,
          apiAuthType,
          apiTokenEnv,
          apiHeaderName,
        });

        const createResult = await call<ContextCreateResult>("context/create", {
          connection: currentName,
          path: "connector.yaml",
          content: template,
        });

        if (!createResult.success) {
          setConnectorConfigError(createResult.error || "Failed to create connector.yaml");
          return;
        }
      }

      const result = await call<ContextReadResult>("context/read", {
        connection: currentName,
        path: "connector.yaml",
      });

      if (!result.success) {
        setConnectorConfigError(result.error || "Failed to open connector.yaml");
        return;
      }

      const nextContent = result.content || "";
      setConnectorConfigExists(true);
      setConnectorConfigContent(nextContent);
      setConnectorConfigOriginal(nextContent);
      setConnectorConfigOpen(true);
    } catch (err) {
      setConnectorConfigError(
        err instanceof Error ? err.message : "Failed to open connector.yaml",
      );
    } finally {
      setConnectorConfigLoading(false);
    }
  }, [
    apiAuthType,
    apiHeaderName,
    apiTokenEnv,
    baseUrl,
    call,
    connectorConfigExists,
    connectorType,
    currentName,
    databaseUrl,
    directory,
  ]);

  const saveConnectorConfig = useCallback(async () => {
    if (!currentName) {
      return false;
    }

    setConnectorConfigSaving(true);
    setConnectorConfigError(null);

    try {
      const result = await call<ContextWriteResult>("context/write", {
        connection: currentName,
        path: "connector.yaml",
        content: connectorConfigContent,
      });

      if (!result.success) {
        setConnectorConfigError(result.error || "Failed to save connector.yaml");
        return false;
      }

      setConnectorConfigOriginal(connectorConfigContent);
      setConnectorConfigExists(true);
      return true;
    } catch (err) {
      setConnectorConfigError(
        err instanceof Error ? err.message : "Failed to save connector.yaml",
      );
      return false;
    } finally {
      setConnectorConfigSaving(false);
    }
  }, [call, connectorConfigContent, currentName]);

  const navigateToStep = useCallback(
    (nextStep: WizardStep, nextName?: string) => {
      router.replace(
        buildWizardHref(nextStep, {
          name: nextName || existingName || undefined,
          type: connectorType,
        }),
      );
      setStep(nextStep);
    },
    [connectorType, existingName, router],
  );

  const resetTransientMessages = () => {
    setFormError(null);
    setSampleError(null);
  };

  const handleTest = useCallback(async () => {
    resetTransientMessages();
    setTestStatus({ testing: true, success: null, message: "Testing connection..." });

    try {
      let result: TestResult;
      if (connectorType === "file") {
        result = await call<TestResult>("connections/test", {
          connectorType: "file",
          directory,
        });
      } else if (connectorType === "api") {
        result = await call<TestResult>("connections/test", {
          connectorType: "api",
          baseUrl,
          authType: apiAuthType,
          apiKey: apiKey || undefined,
          headerName: apiAuthType === "header" ? apiHeaderName || undefined : undefined,
        });
      } else {
        if (connectorConfigExists && connectorConfigDirty) {
          const saved = await saveConnectorConfig();
          if (!saved) {
            setTestStatus({
              testing: false,
              success: false,
              message: "Save connector.yaml before testing the connection again.",
            });
            return;
          }
        }

        const effectiveDatabaseUrl = sqlConnectorOverrides.databaseUrl || databaseUrl.trim();
        if (!effectiveDatabaseUrl) {
          setTestStatus({
            testing: false,
            success: false,
            message: "No database URL configured.",
          });
          return;
        }

        result = await call<TestResult>("connections/test", {
          connectorType: "sql",
          databaseUrl: effectiveDatabaseUrl,
          connectArgs:
            sqlConnectorOverrides.connectArgs ||
            parseConnectArgsFromUrl(effectiveDatabaseUrl) ||
            undefined,
        });
      }

      setResolvedDialect(
        result.dialect || inferDialect(connectorType, { databaseUrl, detectedDialect: result.dialect }),
      );
      setTestStatus({
        testing: false,
        success: result.success,
        message:
          result.message ||
          result.error ||
          (result.success ? "Connection successful" : "Connection failed"),
        hint: result.hint,
      });
    } catch (err) {
      setTestStatus({
        testing: false,
        success: false,
        message: err instanceof Error ? err.message : "Connection test failed",
      });
    }
  }, [
    apiAuthType,
    apiHeaderName,
    apiKey,
    baseUrl,
    call,
    connectorType,
    connectorConfigDirty,
    connectorConfigExists,
    databaseUrl,
    directory,
    saveConnectorConfig,
    sqlConnectorOverrides,
  ]);

  const persistConnection = useCallback(async (): Promise<string | null> => {
    const trimmedName = connectionName.trim();
    if (!trimmedName) {
      setFormError("Connection name is required.");
      return null;
    }

    if (testStatus?.success !== true) {
      setFormError("Run a successful connection test before continuing.");
      return null;
    }

    if (connectorConfigDirty) {
      const saved = await saveConnectorConfig();
      if (!saved) {
        setFormError("Save connector.yaml before continuing.");
        return null;
      }
    }

    setSaveLoading(true);
    setFormError(null);

    try {
      const effectiveDatabaseUrl =
        connectorType === "sql"
          ? sqlConnectorOverrides.databaseUrl || databaseUrl.trim()
          : databaseUrl.trim();
      const updateTargetName = existingName || (connectorConfigExists ? trimmedName : null);

      if (updateTargetName) {
        if (trimmedName !== existingName) {
          if (existingName) {
            setFormError("Renaming is not supported in the wizard yet.");
            return null;
          }
        }

        const updateParams: Record<string, unknown> = { name: updateTargetName };
        if (connectorType === "file") {
          updateParams.directory = directory.trim();
        } else if (connectorType === "api") {
          updateParams.baseUrl = baseUrl.trim();
          updateParams.auth = {
            type: apiAuthType,
            tokenEnv: apiTokenEnv.trim(),
            headerName: apiAuthType === "header" ? apiHeaderName.trim() : undefined,
          };
          if (apiKey.trim()) {
            updateParams.apiKey = apiKey.trim();
          }
        } else {
          updateParams.databaseUrl = effectiveDatabaseUrl;
        }

        const result = await call<UpdateResult>("connections/update", updateParams);
        if (!result.success) {
          setFormError(result.error || "Failed to update connection");
          return null;
        }
      } else {
        const createParams: Record<string, unknown> = {
          name: trimmedName,
          connectorType,
          setActive: true,
        };

        if (connectorType === "file") {
          createParams.directory = directory.trim();
        } else if (connectorType === "api") {
          createParams.baseUrl = baseUrl.trim();
          createParams.authType = apiAuthType;
          createParams.tokenEnv = apiTokenEnv.trim() || undefined;
          createParams.headerName =
            apiAuthType === "header" ? apiHeaderName.trim() || undefined : undefined;
          createParams.apiKey = apiKey.trim() || undefined;
        } else {
          createParams.databaseUrl = effectiveDatabaseUrl;
        }

        const result = await call<CreateResult>("connections/create", createParams);
        if (!result.success || !result.name) {
          setFormError(result.error || "Failed to create connection");
          return null;
        }
      }

      await refreshConnections();
      await switchConnection(trimmedName);
      return trimmedName;
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to save connection");
      return null;
    } finally {
      setSaveLoading(false);
    }
  }, [
    apiAuthType,
    apiHeaderName,
    apiKey,
    apiTokenEnv,
    baseUrl,
    call,
    connectionName,
    connectorType,
    connectorConfigDirty,
    connectorConfigExists,
    databaseUrl,
    directory,
    existingName,
    refreshConnections,
    saveConnectorConfig,
    sqlConnectorOverrides.databaseUrl,
    switchConnection,
    testStatus?.success,
  ]);

  const handleConnectNext = useCallback(async () => {
    const persistedName = await persistConnection();
    if (!persistedName) {
      return;
    }
    navigateToStep("discover", persistedName);
  }, [navigateToStep, persistConnection]);

  const runDiscovery = useCallback(async () => {
    if (!currentName) {
      setFormError("Save the connection before discovery.");
      return;
    }

    setDiscoverState({
      status: "loading",
      connectorType,
      logs: connectorType === "api" ? ["Inspecting API endpoints..."] : ["Looking for catalogs..."],
      errors: [],
    });

    try {
      await switchConnection(currentName);

      if (connectorType === "api") {
        const result = await call<{
          success: boolean;
          strategy?: string;
          endpoints_found?: number;
          endpoints?: Array<{ name: string; path: string; fields: number }>;
          error?: string;
          errors?: string[];
        }>("connections/discover", {
          name: currentName,
        });

        if (!result.success) {
          setDiscoverState({
            status: "error",
            connectorType,
            logs: ["Endpoint discovery failed."],
            errors: [result.error || "Discovery failed"],
          });
          return;
        }

        setSelectedEndpoint(result.endpoints?.[0]?.name || null);
        setDiscoverState({
          status: result.errors?.length ? "partial" : "success",
          connectorType,
          endpointCount: result.endpoints_found || 0,
          endpoints: result.endpoints,
          logs: [
            `Discovery strategy: ${result.strategy || "automatic"}`,
            `Found ${result.endpoints_found || 0} endpoints`,
            ...(result.endpoints || []).slice(0, 8).map((endpoint) => endpoint.path),
          ],
          errors: result.errors || [],
        });
        return;
      }

      const catalogsResult = await call<{
        success: boolean;
        catalogs: Array<string | null>;
        error?: string;
      }>(
        "schema/catalogs",
        {},
      );

      if (!catalogsResult.success) {
        setDiscoverState({
          status: "error",
          connectorType,
          logs: ["Catalog discovery failed."],
          errors: [catalogsResult.error || "Could not inspect catalogs"],
        });
        return;
      }

      const normalizedCatalogs = catalogsResult.catalogs.length
        ? catalogsResult.catalogs.map((catalog) => normalizeDbSegment(catalog))
        : [null];
      const logs: string[] = [];
      if (normalizedCatalogs.some(Boolean)) {
        logs.push(
          `Found ${normalizedCatalogs.length} ${pluralize("catalog", normalizedCatalogs.length)}`,
        );
      }
      const sampleTargets: DiscoverySummary["sampleTargets"] = [];
      const discoveredTables: DiscoveredTablePayload[] = [];
      let schemaCount = 0;
      let tableCount = 0;
      const errors: string[] = [];

      for (const catalog of normalizedCatalogs) {
        const schemasResult = await call<{
          success: boolean;
          schemas: Array<{ name: string; catalog: string | null; tableCount: number | null }>;
          error?: string;
        }>("schema/schemas", { catalog });

        if (!schemasResult.success) {
          errors.push(schemasResult.error || `Failed to inspect ${catalog}`);
          continue;
        }

        schemaCount += schemasResult.schemas.length;
        logs.push(
          `Found ${schemasResult.schemas.length} ${pluralize("schema", schemasResult.schemas.length)} in ${catalog ? `catalog ${catalog}` : "the default catalog"}`,
        );

        for (const schema of schemasResult.schemas.slice(0, 20)) {
          const tablesResult = await call<{
            success: boolean;
            tables: Array<{ name: string; description: string | null }>;
            error?: string;
          }>("schema/tables", {
            catalog,
            schema: schema.name,
          });

          if (!tablesResult.success) {
            errors.push(tablesResult.error || `Failed to inspect ${catalog}.${schema.name}`);
            continue;
          }

          tableCount += tablesResult.tables.length;
          logs.push(
            `Found ${tablesResult.tables.length} ${pluralize("table", tablesResult.tables.length)} in ${formatDiscoveryScope(catalog, schema.name)}`,
          );

          for (const table of tablesResult.tables) {
            const fullName =
              formatTableTarget({
                catalog,
                schema: schema.name,
                table: table.name,
              }) || table.name;
            const columnsResult = await call<{
              success: boolean;
              columns: Array<{
                name: string;
                type: string | null;
              }>;
              error?: string;
            }>("schema/columns", {
              catalog,
              schema: schema.name,
              table: table.name,
            });

            if (!columnsResult.success) {
              errors.push(
                columnsResult.error || `Failed to inspect columns for ${fullName}`,
              );
            }

            discoveredTables.push({
              catalog,
              schema: schema.name,
              table: table.name,
              full_name: fullName,
              columns: (columnsResult.columns || []).map((column) => ({
                name: column.name,
                type: column.type ?? null,
              })),
            });

            if (sampleTargets.length < 16) {
              sampleTargets.push({
                catalog,
                schema: schema.name,
                table: table.name,
                label: fullName,
              });
            }
          }
        }
      }

      if (discoveredTables.length > 0) {
        const persistResult = await call<{
          success: boolean;
          error?: string;
        }>("connections/save-discovery", {
          name: currentName,
          dialect: inferDialect(connectorType, {
            databaseUrl,
            directory,
            baseUrl,
            detectedDialect: resolvedDialect,
          }),
          tables: discoveredTables,
        });

        if (!persistResult.success) {
          errors.push(persistResult.error || "Failed to persist discovery state");
        } else {
          await refreshConnections();
        }
      }

      const firstTarget = sampleTargets[0];
      if (firstTarget) {
        setSampleSelection({
          catalog: firstTarget.catalog || null,
          schema: firstTarget.schema || null,
          table: firstTarget.table || null,
        });
      }

      setDiscoverState({
        status: errors.length ? "partial" : "success",
        connectorType,
        catalogCount: normalizedCatalogs.some(Boolean) ? normalizedCatalogs.length : undefined,
        schemaCount,
        tableCount,
        sampleTargets,
        logs,
        errors,
      });
    } catch (err) {
      setDiscoverState({
        status: "error",
        connectorType,
        logs: ["Discovery failed unexpectedly."],
        errors: [err instanceof Error ? err.message : "Discovery failed"],
      });
    }
  }, [
    baseUrl,
    call,
    connectorType,
    currentName,
    databaseUrl,
    directory,
    refreshConnections,
    resolvedDialect,
    switchConnection,
  ]);

  const markOnboardingComplete = useCallback(async () => {
    if (!currentName) {
      return { success: false, error: "Save the connection before completing setup." };
    }

    const result = await call<{
      success: boolean;
      error?: string;
    }>("connections/complete-onboarding", {
      name: currentName,
    });

    if (result.success) {
      await refreshConnections();
    }

    return result;
  }, [call, currentName, refreshConnections]);

  const handleSampleData = useCallback(async () => {
    if (!currentName) {
      setSampleError("Save the connection before sampling.");
      return;
    }

    setSampleLoading(true);
    setSampleError(null);

    try {
      await switchConnection(currentName);

      if (connectorType === "api") {
        if (!selectedEndpoint) {
          setSampleError("Select an endpoint to sync a sample.");
          return;
        }

        const result = await call<{
          success: boolean;
          synced?: string[];
          rows_fetched?: Record<string, number>;
          error?: string;
        }>("connections/sync", {
          name: currentName,
          endpoint: selectedEndpoint,
        });

        if (!result.success) {
          setSampleError(result.error || "Failed to sync sample data");
          return;
        }

        const synced = result.synced || [selectedEndpoint];
        const rowCount = result.rows_fetched?.[selectedEndpoint] || 0;
        setSampleLogs([
          `Synced ${synced.join(", ")}`,
          `Fetched ${rowCount} rows from ${selectedEndpoint}`,
        ]);
        const completionResult = await markOnboardingComplete();
        if (!completionResult.success) {
          setSampleError(
            completionResult.error || "Sample synced but failed to complete onboarding",
          );
        }
        return;
      }

      if (!sampleSelection.table) {
        setSampleError("Select a table from the schema explorer first.");
        return;
      }

      const result = await call<SampleTableResult>("sample_table", {
        connection: currentName,
        table_name: sampleSelection.table,
        schema: sampleSelection.schema || undefined,
        catalog: sampleSelection.catalog || undefined,
        limit: 5,
      });

      if (result.error) {
        setSampleError(result.error);
        return;
      }

      setSampleRows(result.rows || []);
      setSampleLogs([
        `Sampled ${result.row_count} rows from ${result.full_name}`,
        `Limit ${result.limit}`,
      ]);
      const completionResult = await markOnboardingComplete();
      if (!completionResult.success) {
        setSampleError(
          completionResult.error || "Sample succeeded but failed to complete onboarding",
        );
      }
    } catch (err) {
      setSampleError(err instanceof Error ? err.message : "Failed to sample data");
    } finally {
      setSampleLoading(false);
    }
  }, [
    call,
    connectorType,
    currentName,
    markOnboardingComplete,
    sampleSelection,
    selectedEndpoint,
    switchConnection,
  ]);

  const summaryPrimaryLabel =
    connectorType === "sql" ? "DB URL" : connectorType === "file" ? "Directory" : "Base URL";
  const summaryPrimaryValue =
    connectorType === "sql"
      ? displayDatabaseUrl || "Not set"
      : connectorType === "file"
        ? directory || "Not set"
        : baseUrl || "Not set";
  const summaryDialect = inferDialect(connectorType, {
    databaseUrl,
    directory,
    baseUrl,
    detectedDialect: resolvedDialect,
  });
  const persistedStatuses = currentConnection
    ? getPersistedWizardStatuses(currentConnection)
    : {
        connect: "idle" as const,
        discover: "idle" as const,
        sample: "idle" as const,
      };
  const wizardDiscoveryStatus = summarizeDiscoveryStatus(discoverState, currentConnection);
  const wizardConnectDone = testStatus?.success === true || persistedStatuses.connect === "done";
  const wizardStatuses: Record<WizardStep, "idle" | "active" | "done"> = {
    connect:
      wizardConnectDone
        ? "done"
        : persistedStatuses.connect === "done"
          ? "done"
          : step === "connect"
            ? "active"
            : "idle",
    discover:
      wizardDiscoveryStatus === "success"
        ? "done"
        : persistedStatuses.discover === "done"
          ? "done"
          : step === "discover" || wizardDiscoveryStatus === "loading" || wizardDiscoveryStatus === "partial"
            ? "active"
            : "idle",
    sample:
      ((connectorType === "api" &&
        ((wizardDiscoveryStatus === "success" && wizardConnectDone) ||
          persistedStatuses.sample === "done")) ||
        currentConnection?.onboardingPhase?.toLowerCase() === "complete" ||
        (sampleLogs.length > 0 && !sampleError))
        ? "done"
        : step === "sample"
          ? "active"
          : "idle",
  };

  const queryPreview =
    connectorType === "api"
      ? selectedEndpoint
        ? `sync ${selectedEndpoint}`
        : "Select an endpoint above"
      : sampleSelection.table
        ? `select * from ${formatTableTarget(sampleSelection)} limit 5;`
        : "Select a table above";

  const renderSummaryCard = () => (
    <div className="max-w-4xl rounded-xl border border-gray-800 bg-gray-950/80 p-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Name</p>
          <p className="text-sm text-gray-200">{currentName || "Unsaved"}</p>
        </div>
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.2em] text-gray-500">{summaryPrimaryLabel}</p>
          <p className="break-all text-sm text-gray-200">{summaryPrimaryValue}</p>
        </div>
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Status</p>
          <ConnectionStatusSteps statuses={wizardStatuses} />
        </div>
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Dialect</p>
          <p className="text-sm text-gray-200">{summaryDialect}</p>
        </div>
      </div>
    </div>
  );

  return (
    <ConnectionWorkspaceShell selectedName={currentName || null} currentView={null}>
      <div className="space-y-6">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-white">Connection Setup Wizard</h1>
          <p className="text-sm text-gray-400">
            Create the connection, inspect what db-mcp can discover, then validate
            the first sample.
          </p>
        </div>

        <div className="space-y-8">
        <div className="space-y-4">
          <nav className="flex flex-wrap items-center gap-3 text-lg font-medium">
            {WIZARD_STEPS.map((wizardStep, index) => {
              const isActive = step === wizardStep.id;
              const isLocked = wizardStep.id !== "connect" && !existingName;
              return (
                <span key={wizardStep.id} className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      if (!isLocked) {
                        navigateToStep(wizardStep.id);
                      }
                    }}
                    disabled={isLocked}
                    className={`${
                      isActive ? "text-brand" : "text-gray-200"
                    } ${isLocked ? "cursor-not-allowed text-gray-600" : "hover:text-brand"}`}
                  >
                    {index + 1}. {wizardStep.label}
                  </button>
                  {index < WIZARD_STEPS.length - 1 && <span className="text-gray-600">•</span>}
                </span>
              );
            })}
          </nav>
        </div>
        <div className="space-y-8">
          {step === "connect" && (
            <div
              className={`items-stretch gap-6 ${connectorConfigOpen ? "xl:grid xl:grid-cols-[minmax(0,1fr)_1px_420px]" : "max-w-4xl"}`}
            >
              <div className="space-y-6">
                {renderSummaryCard()}
                <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
                  <span className="text-sm font-medium text-gray-300">Type</span>
                  <select
                    value={connectorType}
                    onChange={(event) => setConnectorType(event.target.value as ConnectorType)}
                    disabled={Boolean(existingName)}
                    className="h-10 rounded-md border border-gray-700 bg-gray-950 px-3 text-sm text-white"
                  >
                    <option value="sql">Database</option>
                    <option value="api">API</option>
                    <option value="file">Files</option>
                  </select>
                </div>
                <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
                  <span className="text-sm font-medium text-gray-300">Name</span>
                  <Input
                    value={connectionName}
                    onChange={(event) => setConnectionName(event.target.value)}
                    disabled={Boolean(existingName)}
                    placeholder="my-connection"
                    data-testid="connection-name-input"
                    className="border-gray-700 bg-gray-950 text-white"
                  />
                </div>
                {connectorType === "sql" && (
                  <>
                    <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
                      <span className="text-sm font-medium text-gray-300">DB URL</span>
                      <Input
                        value={displayDatabaseUrl}
                        onChange={(event) => {
                          setDisplayDatabaseUrl(event.target.value);
                          setDatabaseUrl(event.target.value);
                        }}
                        placeholder="trino://user:pass@host:443/catalog/schema"
                        data-testid="connection-url-input"
                        className="border-gray-700 bg-gray-950 font-mono text-white"
                      />
                    </div>
                    <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
                      <span className="text-sm font-medium text-gray-300">Config</span>
                      <div className="flex flex-wrap items-center gap-3">
                        {connectorConfigExists && (
                          <span className="text-sm text-gray-200">connector.yaml</span>
                        )}
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={openConnectorConfigEditor}
                          disabled={!canManageConnectorConfig || connectorConfigLoading}
                        >
                          {connectorConfigLoading
                            ? connectorConfigExists
                              ? "Opening..."
                              : "Creating..."
                            : connectorConfigExists
                              ? "Edit"
                              : "Create"}
                        </Button>
                        {!canManageConnectorConfig && (
                          <span className="text-xs text-gray-500">
                            Enter a connection name first.
                          </span>
                        )}
                      </div>
                    </div>
                  </>
                )}
                {connectorType === "file" && (
                  <>
                    <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
                      <span className="text-sm font-medium text-gray-300">Directory</span>
                      <Input
                        value={directory}
                        onChange={(event) => setDirectory(event.target.value)}
                        placeholder="/path/to/data"
                        data-testid="connection-directory-input"
                        className="border-gray-700 bg-gray-950 text-white"
                      />
                    </div>
                    <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
                      <span className="text-sm font-medium text-gray-300">Config</span>
                      <div className="flex flex-wrap items-center gap-3">
                        {connectorConfigExists && (
                          <span className="text-sm text-gray-200">connector.yaml</span>
                        )}
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={openConnectorConfigEditor}
                          disabled={!canManageConnectorConfig || connectorConfigLoading}
                        >
                          {connectorConfigLoading
                            ? connectorConfigExists
                              ? "Opening..."
                              : "Creating..."
                            : connectorConfigExists
                              ? "Edit"
                              : "Create"}
                        </Button>
                        {!canManageConnectorConfig && (
                          <span className="text-xs text-gray-500">
                            Enter a connection name first.
                          </span>
                        )}
                      </div>
                    </div>
                  </>
                )}
                {connectorType === "api" && (
                  <>
                    <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
                      <span className="text-sm font-medium text-gray-300">Base URL</span>
                      <Input
                        value={baseUrl}
                        onChange={(event) => setBaseUrl(event.target.value)}
                        placeholder="https://api.example.com/v1"
                        data-testid="connection-url-input"
                        className="border-gray-700 bg-gray-950 text-white"
                      />
                    </div>
                    <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-start">
                      <span className="pt-2 text-sm font-medium text-gray-300">Config</span>
                      <div className="flex flex-wrap items-center gap-3">
                        {connectorConfigExists && (
                          <span className="text-sm text-gray-200">connector.yaml</span>
                        )}
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={openConnectorConfigEditor}
                          disabled={!canManageConnectorConfig || connectorConfigLoading}
                        >
                          {connectorConfigLoading
                            ? connectorConfigExists
                              ? "Opening..."
                              : "Creating..."
                            : connectorConfigExists
                              ? "Edit"
                              : "Create"}
                        </Button>
                        {!canManageConnectorConfig && (
                          <span className="text-xs text-gray-500">
                            Enter a connection name first.
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
                      <span className="text-sm font-medium text-gray-300">Auth</span>
                      <div className="grid gap-3 md:grid-cols-3">
                        <select
                          value={apiAuthType}
                          onChange={(event) => setApiAuthType(event.target.value)}
                          className="h-10 rounded-md border border-gray-700 bg-gray-950 px-3 text-sm text-white"
                        >
                          <option value="none">None</option>
                          <option value="bearer">Bearer</option>
                          <option value="header">Header</option>
                          <option value="query_param">Query param</option>
                        </select>
                        {apiAuthType === "none" ? (
                          <div className="md:col-span-2 flex items-center text-sm text-gray-500">
                            No auth headers or tokens required.
                          </div>
                        ) : (
                          <>
                            <Input
                              value={apiTokenEnv}
                              onChange={(event) => setApiTokenEnv(event.target.value)}
                              placeholder="API_KEY"
                              className="border-gray-700 bg-gray-950 text-white"
                            />
                            <Input
                              value={apiHeaderName}
                              onChange={(event) => setApiHeaderName(event.target.value)}
                              placeholder="Authorization"
                              className="border-gray-700 bg-gray-950 text-white"
                            />
                          </>
                        )}
                      </div>
                    </div>
                  </>
                )}

                <div className="flex flex-wrap gap-3">
                  <Button onClick={handleTest} disabled={testStatus?.testing}>
                    {testStatus?.testing ? "Testing..." : "Test"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() =>
                      setFormError(
                        "Double-check credentials, network reachability, and connector-specific SSL options.",
                      )
                    }
                  >
                    Troubleshooting
                  </Button>
                </div>

                <div className="rounded-xl border border-gray-800 bg-gray-950/80 p-4 text-sm text-gray-300">
                  <p>{testStatus?.message || "Run a connection test to validate the setup."}</p>
                  {testStatus?.hint && <p className="mt-2 text-amber-300">{testStatus.hint}</p>}
                </div>

                {(formError || connectorConfigError) && (
                  <p className="text-sm text-red-300">{formError || connectorConfigError}</p>
                )}

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 text-sm text-gray-300">
                    <span>Result:</span>
                    <span>
                      {testStatus?.success === true
                        ? "Successfully connected"
                        : testStatus?.success === false
                          ? "Needs attention"
                          : "Pending"}
                    </span>
                  </div>
                  <Button onClick={handleConnectNext} disabled={saveLoading}>
                    {saveLoading ? "Saving..." : "Next >"}
                  </Button>
                </div>
              </div>

              {connectorConfigOpen && (
                <>
                  <div className="hidden xl:block w-px self-stretch bg-gray-800" />
                  <div className="flex min-h-full flex-col space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-white">connector.yaml</p>
                        <p className="text-xs text-gray-500">Connection-specific configuration</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setConnectorConfigContent(connectorConfigOriginal)}
                          disabled={!connectorConfigDirty || connectorConfigSaving}
                        >
                          Discard
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          onClick={saveConnectorConfig}
                          disabled={!connectorConfigDirty || connectorConfigSaving}
                        >
                          {connectorConfigSaving ? "Saving..." : "Save"}
                        </Button>
                      </div>
                    </div>
                    <div className="flex-1 rounded-xl border border-gray-800 bg-gray-950/80">
                      <textarea
                        value={connectorConfigContent}
                        onChange={(event) => setConnectorConfigContent(event.target.value)}
                        spellCheck={false}
                        className="h-full min-h-[44rem] w-full resize-none bg-transparent px-4 py-4 font-mono text-sm text-gray-200 outline-none"
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {step === "discover" && (
            <div className="max-w-4xl space-y-6">
              {renderSummaryCard()}
              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={runDiscovery} disabled={discoverState.status === "loading"}>
                  {discoverState.status === "loading"
                    ? hasDiscoveryData(discoverState)
                      ? "Re-discovering..."
                      : "Discovering..."
                    : hasDiscoveryData(discoverState)
                      ? "Re-discover"
                      : "Discover"}
                </Button>
              </div>

              <div className="rounded-xl border border-gray-800 bg-gray-950/80 p-4">
                <div className="space-y-2 text-sm text-gray-300">
                  {discoverState.logs.map((entry) => (
                    <p key={entry}>{entry}</p>
                  ))}
                  {discoverState.errors.map((entry) => (
                    <p key={entry} className="text-amber-300">
                      {entry}
                    </p>
                  ))}
                  {discoverState.logs.length === 0 && (
                    <p>No discovery data is available yet.</p>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap gap-6 text-sm text-gray-300">
                {discoverState.catalogCount !== undefined && (
                  <span>{discoverState.catalogCount} catalogs</span>
                )}
                {discoverState.schemaCount !== undefined && (
                  <span>{discoverState.schemaCount} schemas</span>
                )}
                {discoverState.tableCount !== undefined && (
                  <span>{discoverState.tableCount} tables</span>
                )}
                {discoverState.endpointCount !== undefined && (
                  <span>{discoverState.endpointCount} endpoints</span>
                )}
              </div>

              <div className="flex items-center justify-between">
                <Button variant="outline" onClick={() => navigateToStep("connect")}>
                  &lt; Previous
                </Button>
                <Button
                  onClick={() => navigateToStep("sample")}
                  disabled={discoverState.status === "idle" || discoverState.status === "loading"}
                >
                  Next &gt;
                </Button>
              </div>
            </div>
          )}

          {step === "sample" && (
            <div className="space-y-6">
              <div className="items-start gap-4 xl:grid xl:grid-cols-[max-content_1px_minmax(0,1fr)]">
                <div className="space-y-6">
                  {renderSummaryCard()}
                  <div className="space-y-6 max-w-4xl">
                    <div className="rounded-xl border border-gray-800 bg-gray-950/80 p-4">
                      <h2 className="text-lg font-semibold text-white">Sample data</h2>
                      <div className="mt-4 space-y-2 text-sm text-gray-300">
                        {sampleLogs.map((entry) => (
                          <p key={entry}>{entry}</p>
                        ))}
                        {sampleError && <p className="text-red-300">{sampleError}</p>}
                        {!sampleLogs.length && !sampleError && (
                          <p>Select a table or endpoint, then fetch the first sample.</p>
                        )}
                      </div>

                      {connectorType === "api" ? (
                        <div className="mt-4 space-y-3">
                          {(discoverState.endpoints || []).map((endpoint) => (
                            <label
                              key={endpoint.name}
                              className="flex items-center justify-between rounded-lg border border-gray-800 px-3 py-2 text-sm text-gray-200"
                            >
                              <span>
                                <span className="font-medium">{endpoint.name}</span>
                                <span className="ml-2 text-gray-500">{endpoint.path}</span>
                              </span>
                              <input
                                type="radio"
                                name="endpoint"
                                checked={selectedEndpoint === endpoint.name}
                                onChange={() => setSelectedEndpoint(endpoint.name)}
                              />
                            </label>
                          ))}
                        </div>
                      ) : sampleRows.length > 0 ? (
                        <div className="mt-4 overflow-x-auto rounded-lg border border-gray-800">
                          <table className="min-w-full divide-y divide-gray-800 text-sm">
                            <thead className="bg-gray-950">
                              <tr>
                                {Object.keys(sampleRows[0] || {}).map((column) => (
                                  <th
                                    key={column}
                                    className="px-3 py-2 text-left font-medium text-gray-400"
                                  >
                                    {column}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-800">
                              {sampleRows.map((row, rowIndex) => (
                                <tr key={rowIndex}>
                                  {Object.keys(sampleRows[0] || {}).map((column) => (
                                    <td
                                      key={`${rowIndex}-${column}`}
                                      className="px-3 py-2 text-gray-200"
                                    >
                                      {String(row[column] ?? "")}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : null}
                    </div>

                    <div className="flex items-start gap-6">
                      <div className="min-w-0 flex-1 rounded-xl border border-gray-800 bg-gray-950/80 p-4">
                        <p className="text-sm font-medium text-white">Selection</p>
                        <pre className="mt-3 whitespace-pre-wrap text-sm text-gray-300">
                          {queryPreview}
                        </pre>
                      </div>
                      <Button onClick={handleSampleData} disabled={sampleLoading}>
                        {sampleLoading ? "Sampling..." : "Sample Data"}
                      </Button>
                    </div>

                    <div className="flex items-center justify-between">
                      <Button variant="outline" onClick={() => navigateToStep("discover")}>
                        &lt; Previous
                      </Button>
                      <Button asChild>
                        <Link href={`/connection/${encodeURIComponent(currentName)}`}>Done</Link>
                      </Button>
                    </div>
                  </div>
                </div>

                {connectorType === "api" ? (
                  <>
                    <div className="hidden xl:block w-px self-stretch bg-gray-800" />
                    <Card className="h-full border-gray-800 bg-gray-950/80">
                      <CardHeader>
                        <CardTitle className="text-white">Discovered endpoints</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2 text-sm text-gray-300">
                        {(discoverState.endpoints || []).map((endpoint) => (
                          <div
                            key={endpoint.name}
                            className="rounded-lg border border-gray-800 px-3 py-2"
                          >
                            <p className="font-medium text-white">{endpoint.name}</p>
                            <p className="text-gray-500">{endpoint.path}</p>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  </>
                ) : (
                  <>
                    <div className="hidden xl:block w-px self-stretch bg-gray-800" />
                    <div className="min-h-[44rem] min-w-0 overflow-hidden rounded-xl border border-gray-800 bg-gray-950/80 xl:h-full">
                      <SchemaExplorer
                        isOpen
                        onClose={() => {}}
                        onInsertLink={(link) => {
                          const nextSelection = parseDbLink(link);
                          if (!nextSelection.table) {
                            return;
                          }
                          setSampleSelection({
                            catalog: normalizeDbSegment(nextSelection.catalog),
                            schema: normalizeDbSegment(nextSelection.schema),
                            table: normalizeDbSegment(nextSelection.table),
                          });
                        }}
                      />
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
        </div>
      </div>
    </ConnectionWorkspaceShell>
  );
}
