"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useBICP } from "@/lib/bicp-context";
import { useConnections } from "@/lib/connection-context";
import type {
  ApiEnvVarEntry,
  ApiTemplateDescriptor,
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
import {
  applyApiEnvValueChange,
  buildApiEnvEntriesForAuth,
  buildApiStateFromTemplate,
  buildApiTestParams,
  buildWizardHref,
  clearApiEnvEntry,
  formatTableTarget,
  getPersistedWizardStatuses,
  inferDialect,
  isWizardStepLocked,
  maskDatabaseUrl,
  normalizeApiEnvEntry,
  normalizeDbSegment,
  parseConnectArgsFromUrl,
  parseDbLink,
  parseSqlConnectorOverrides,
  saveApiEnvEntry,
  wizardStepFromHash,
} from "./utils";

// ─── Local types (private to wizard logic) ──────────────────────────────────

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

type ApiTemplatesResult = {
  success: boolean;
  templates?: ApiTemplateDescriptor[];
  error?: string;
};

type RenderTemplateResult = {
  success: boolean;
  content?: string;
  error?: string;
};

// ─── Pure helpers ────────────────────────────────────────────────────────────

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

export function parseExistingSchemaSnapshot(
  content: string,
  connectorType: ConnectorType,
): DiscoverySummary | null {
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
    tables
      .map((table) => normalizeDbSegment(table.catalog))
      .filter((value): value is string => Boolean(value)),
  );
  const schemas = new Set(
    tables
      .map((table) => normalizeDbSegment(table.schema))
      .filter((value): value is string => Boolean(value)),
  );

  const logs: string[] = [];
  logs.push(
    generatedAt
      ? `Loaded existing schema snapshot from ${generatedAt}.`
      : "Loaded existing schema snapshot.",
  );
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

export function hasDiscoveryData(state: DiscoverySummary): boolean {
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
  apiParamName: string;
  apiEnvVars: ApiEnvVarEntry[];
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
    ];

    if (options.apiAuthType === "basic") {
      lines.push(`  username_env: ${options.apiEnvVars[0]?.name || "API_USERNAME"}`);
      lines.push(`  password_env: ${options.apiEnvVars[1]?.name || "API_PASSWORD"}`);
    } else if (options.apiAuthType !== "none") {
      lines.push(`  token_env: ${options.apiTokenEnv || "API_KEY"}`);
    }

    if (options.apiAuthType === "header" && options.apiHeaderName) {
      lines.push(`  header_name: ${options.apiHeaderName}`);
    }
    if (options.apiAuthType === "query_param" && options.apiParamName) {
      lines.push(`  param_name: ${options.apiParamName}`);
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

export function summarizeDiscoveryStatus(
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

// ─── Hook ────────────────────────────────────────────────────────────────────

export function useWizardState() {
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
  const [apiTemplateId, setApiTemplateId] = useState("");
  const [apiTemplates, setApiTemplates] = useState<ApiTemplateDescriptor[]>([]);
  const [apiAuthType, setApiAuthType] = useState("bearer");
  const [apiTokenEnv, setApiTokenEnv] = useState("");
  const [apiHeaderName, setApiHeaderName] = useState("");
  const [apiParamName, setApiParamName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiEnvVars, setApiEnvVars] = useState<ApiEnvVarEntry[]>([]);
  const [apiEnvFeedback, setApiEnvFeedback] = useState<string | null>(null);
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

  // ─── Derived / computed ────────────────────────────────────────────────────

  const currentName = existingName || connectionName.trim();
  const currentConnection = useMemo(
    () => connections.find((connection) => connection.name === currentName) || null,
    [connections, currentName],
  );
  const selectedApiTemplate = useMemo(
    () => apiTemplates.find((template) => template.id === apiTemplateId) || null,
    [apiTemplateId, apiTemplates],
  );
  const effectiveApiBaseUrl = useMemo(
    () => baseUrl.trim() || selectedApiTemplate?.baseUrl || "https://api.example.com/v1",
    [baseUrl, selectedApiTemplate],
  );
  const effectiveApiTokenEnv = useMemo(() => {
    if (apiAuthType === "basic" || apiAuthType === "none") {
      return apiTokenEnv;
    }
    return apiEnvVars[0]?.name?.trim() || apiTokenEnv;
  }, [apiAuthType, apiEnvVars, apiTokenEnv]);
  const canManageConnectorConfig = Boolean(currentName);
  const connectorConfigDirty = connectorConfigContent !== connectorConfigOriginal;
  const sqlConnectorOverrides = useMemo(
    () =>
      connectorType === "sql" && connectorConfigExists
        ? parseSqlConnectorOverrides(connectorConfigContent || connectorConfigOriginal)
        : {},
    [connectorConfigContent, connectorConfigExists, connectorConfigOriginal, connectorType],
  );

  // ─── Effects ──────────────────────────────────────────────────────────────

  useEffect(() => {
    const syncStep = () => {
      const nextStep = wizardStepFromHash(window.location.hash);
      if (isWizardStepLocked(nextStep, currentName)) {
        setStep("connect");
        window.history.replaceState(
          null,
          "",
          buildWizardHref("connect", {
            name: currentName || undefined,
            type: connectorType,
          }),
        );
        return;
      }
      setStep(nextStep);
    };

    syncStep();
    window.addEventListener("hashchange", syncStep);
    return () => window.removeEventListener("hashchange", syncStep);
  }, [connectorType, currentName]);

  useEffect(() => {
    setConnectorType(initialType);
    setDiscoverState((prev) => ({ ...prev, connectorType: initialType }));
  }, [initialType]);

  // ─── API Templates ────────────────────────────────────────────────────────

  const loadApiTemplates = useCallback(async () => {
    if (!isInitialized) {
      return;
    }

    try {
      const result = await call<ApiTemplatesResult>("connections/templates", {
        connectorType: "api",
      });
      if (result.success && result.templates) {
        setApiTemplates(result.templates);
      }
    } catch {
      // Best-effort hydration only.
    }
  }, [call, isInitialized]);

  useEffect(() => {
    loadApiTemplates();
  }, [loadApiTemplates]);

  const handleApiTemplateSelect = useCallback(
    (nextTemplateId: string) => {
      setApiEnvFeedback(null);
      setApiTemplateId(nextTemplateId);
      if (!nextTemplateId) {
        const nextEnvVars = buildApiEnvEntriesForAuth(apiAuthType, apiEnvVars, {
          tokenEnv: apiTokenEnv,
        });
        setApiEnvVars(nextEnvVars);
        if (nextEnvVars[0]?.name) {
          setApiTokenEnv(nextEnvVars[0].name);
        }
        return;
      }

      const template = apiTemplates.find((entry) => entry.id === nextTemplateId);
      if (!template) {
        return;
      }

      const nextState = buildApiStateFromTemplate(template);
      setApiAuthType(nextState.authType);
      setApiTokenEnv(nextState.tokenEnv);
      setApiHeaderName(nextState.headerName);
      setApiParamName(nextState.paramName);
      setApiEnvVars(nextState.envVars);
      setApiKey("");
    },
    [apiAuthType, apiEnvVars, apiTemplates, apiTokenEnv],
  );

  const handleApiAuthTypeChange = useCallback(
    (nextAuthType: string) => {
      setApiEnvFeedback(null);
      setApiAuthType(nextAuthType);
      if (apiTemplateId) {
        return;
      }
      const nextEnvVars = buildApiEnvEntriesForAuth(nextAuthType, apiEnvVars, {
        tokenEnv: apiTokenEnv,
      });
      setApiEnvVars(nextEnvVars);
      if (nextAuthType === "none") {
        setApiTokenEnv("");
      } else if (nextAuthType !== "basic" && nextEnvVars[0]?.name) {
        setApiTokenEnv(nextEnvVars[0].name);
      }
    },
    [apiEnvVars, apiTemplateId, apiTokenEnv],
  );

  const updateApiEnvVar = useCallback((index: number, patch: Partial<ApiEnvVarEntry>) => {
    setApiEnvFeedback(null);
    setApiEnvVars((previous) =>
      previous.map((entry, entryIndex) => {
        if (entryIndex !== index) {
          return entry;
        }
        return normalizeApiEnvEntry({
          ...entry,
          ...patch,
        });
      }),
    );
  }, []);

  const handleApiEnvValueChange = useCallback((index: number, nextValue: string) => {
    setApiEnvFeedback(null);
    setApiEnvVars((previous) =>
      previous.map((entry, entryIndex) =>
        entryIndex === index ? applyApiEnvValueChange(entry, nextValue) : entry,
      ),
    );
  }, []);

  const addApiEnvVar = useCallback(() => {
    setApiEnvFeedback(null);
    setApiEnvVars((previous) => [
      ...previous,
      {
        slot: "",
        name: "",
        value: "",
        prompt: "Additional env var",
        secret: true,
        hasSavedValue: false,
        masked: false,
        removed: false,
      },
    ]);
  }, []);

  useEffect(() => {
    if (connectorType !== "api" || apiTemplateId) {
      return;
    }

    setApiEnvVars((previous) => {
      const next = buildApiEnvEntriesForAuth(apiAuthType, previous, {
        tokenEnv: apiTokenEnv,
      });
      return JSON.stringify(previous) === JSON.stringify(next) ? previous : next;
    });
  }, [apiAuthType, apiTemplateId, apiTokenEnv, connectorType]);

  // ─── Hydration ────────────────────────────────────────────────────────────

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
        const result = await call<{ success: boolean; content?: string; error?: string }>(
          "context/read",
          {
            connection: name,
            path: "schema/descriptions.yaml",
          },
        );

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

  const hydrateConnectionForm = useCallback(
    async (name: string) => {
      if (!isInitialized || !name) {
        return;
      }

      try {
        const result = await call<ConnectionGetResult>("connections/get", {
          name,
        });
        if (!result.success) {
          setFormError(result.error || "Failed to load connection");
          return;
        }

        const type = result.connectorType || "sql";
        setConnectorType(type);
        setConnectionName(name);
        setDatabaseUrl(result.databaseUrl || "");
        setDisplayDatabaseUrl(maskDatabaseUrl(result.databaseUrl || ""));
        setDirectory(result.directory || "");
        setBaseUrl(result.baseUrl || "");
        setApiTemplateId(result.presetId || "");
        setApiAuthType(result.auth?.type || "bearer");
        setApiTokenEnv(result.auth?.tokenEnv || "");
        setApiHeaderName(result.auth?.headerName || "");
        setApiParamName(result.auth?.paramName || "");
        setApiKey("");
        setApiEnvVars(
          (
            result.envVars ||
            buildApiEnvEntriesForAuth(result.auth?.type || "bearer", [], {
              tokenEnv: result.auth?.tokenEnv || "",
              usernameEnv: result.auth?.usernameEnv || "",
              passwordEnv: result.auth?.passwordEnv || "",
            })
          ).map((entry) => normalizeApiEnvEntry(entry)),
        );
        setResolvedDialect(inferDialect(type, { databaseUrl: result.databaseUrl }));

        await switchConnection(name);
        await hydrateExistingDiscoveryState(name, type, result.endpoints);
      } catch (err) {
        setFormError(err instanceof Error ? err.message : "Failed to load connection");
      }
    },
    [call, hydrateExistingDiscoveryState, isInitialized, switchConnection],
  );

  useEffect(() => {
    if (existingName) {
      hydrateConnectionForm(existingName);
    }
  }, [existingName, hydrateConnectionForm]);

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

  // ─── Connector config ─────────────────────────────────────────────────────

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

  // ─── API env var persistence ──────────────────────────────────────────────

  const persistApiEnvVars = useCallback(
    async (nextEnvVars: ApiEnvVarEntry[], feedback: string) => {
      const trimmedName = connectionName.trim();
      if (!trimmedName) {
        setFormError("Enter a connection name before saving env vars.");
        return false;
      }

      const updateTargetName =
        existingName || connectorConfigExists || currentConnection ? trimmedName : null;

      try {
        let success = false;

        if (updateTargetName) {
          const result = await call<UpdateResult>("connections/update", {
            name: updateTargetName,
            baseUrl: effectiveApiBaseUrl,
            templateId: apiTemplateId || undefined,
            auth: {
              type: apiAuthType,
              tokenEnv: effectiveApiTokenEnv.trim(),
              headerName: apiAuthType === "header" ? apiHeaderName.trim() : undefined,
              paramName: apiAuthType === "query_param" ? apiParamName.trim() : undefined,
              usernameEnv: apiAuthType === "basic" ? nextEnvVars[0]?.name.trim() : undefined,
              passwordEnv: apiAuthType === "basic" ? nextEnvVars[1]?.name.trim() : undefined,
            },
            envVars: nextEnvVars,
          });
          success = result.success;
          if (!result.success) {
            setFormError(result.error || "Failed to save env vars");
            return false;
          }
        } else {
          const result = await call<CreateResult>("connections/create", {
            name: trimmedName,
            connectorType: "api",
            setActive: false,
            baseUrl: effectiveApiBaseUrl,
            templateId: apiTemplateId || undefined,
            authType: apiAuthType,
            tokenEnv: effectiveApiTokenEnv.trim() || undefined,
            headerName: apiAuthType === "header" ? apiHeaderName.trim() || undefined : undefined,
            paramName:
              apiAuthType === "query_param" ? apiParamName.trim() || undefined : undefined,
            envVars: nextEnvVars,
          });
          success = result.success;
          if (!result.success) {
            setFormError(result.error || "Failed to save env vars");
            return false;
          }
        }

        if (success) {
          setApiEnvVars(nextEnvVars);
          setApiEnvFeedback(feedback);
          setFormError(null);
          await refreshConnections();
          await refreshConnectorConfigState();
        }

        return success;
      } catch (err) {
        setFormError(err instanceof Error ? err.message : "Failed to save env vars");
        return false;
      }
    },
    [
      apiAuthType,
      apiHeaderName,
      apiParamName,
      apiTemplateId,
      call,
      connectionName,
      connectorConfigExists,
      currentConnection,
      effectiveApiBaseUrl,
      effectiveApiTokenEnv,
      existingName,
      refreshConnections,
      refreshConnectorConfigState,
    ],
  );

  const handleSaveApiEnvVar = useCallback(
    async (index: number) => {
      const entry = apiEnvVars[index];
      if (!entry?.value?.trim()) {
        return;
      }

      const nextEnvVars = apiEnvVars.map((candidate, entryIndex) =>
        entryIndex === index ? saveApiEnvEntry(candidate) : candidate,
      );
      const savedEntry = nextEnvVars[index];
      await persistApiEnvVars(
        nextEnvVars,
        `Saved ${savedEntry?.name || savedEntry?.slot || "credential"} to .env`,
      );
    },
    [apiEnvVars, persistApiEnvVars],
  );

  const handleRemoveApiEnvVar = useCallback(
    async (index: number) => {
      const entry = apiEnvVars[index];
      if (!entry) {
        return;
      }

      const normalized = normalizeApiEnvEntry(entry);
      const shouldKeepRow = Boolean(normalized.slot) || normalized.hasSavedValue;
      if (!shouldKeepRow) {
        setApiEnvVars((previous) => previous.filter((_, entryIndex) => entryIndex !== index));
        setApiEnvFeedback(null);
        return;
      }

      const nextEnvVars = apiEnvVars.map((candidate, entryIndex) =>
        entryIndex === index ? clearApiEnvEntry(candidate) : candidate,
      );
      await persistApiEnvVars(
        nextEnvVars,
        `Removed ${normalized.name || normalized.slot || "credential"} from .env`,
      );
    },
    [apiEnvVars, persistApiEnvVars],
  );

  // ─── Connector config editor ──────────────────────────────────────────────

  const openConnectorConfigEditor = useCallback(async () => {
    if (!currentName) {
      setConnectorConfigError("Enter a connection name before editing connector.yaml.");
      return;
    }

    setConnectorConfigError(null);
    setConnectorConfigLoading(true);

    try {
      if (!connectorConfigExists) {
        let template = buildConnectorConfigTemplate({
          connectorType,
          databaseUrl,
          directory,
          baseUrl,
          apiAuthType,
          apiTokenEnv: effectiveApiTokenEnv,
          apiHeaderName,
          apiParamName,
          apiEnvVars,
        });

        if (connectorType === "api" && apiTemplateId) {
          const renderResult = await call<RenderTemplateResult>("connections/render-template", {
            templateId: apiTemplateId,
            baseUrl,
            authType: apiAuthType,
            headerName: apiHeaderName,
            paramName: apiParamName,
            envVars: apiEnvVars,
          });
          if (!renderResult.success || !renderResult.content) {
            setConnectorConfigError(renderResult.error || "Failed to render template");
            return;
          }
          template = renderResult.content;
        }

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
    apiTemplateId,
    apiEnvVars,
    apiParamName,
    effectiveApiTokenEnv,
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
      if (existingName) {
        await hydrateConnectionForm(currentName);
      }
      return true;
    } catch (err) {
      setConnectorConfigError(
        err instanceof Error ? err.message : "Failed to save connector.yaml",
      );
      return false;
    } finally {
      setConnectorConfigSaving(false);
    }
  }, [call, connectorConfigContent, currentName, existingName, hydrateConnectionForm]);

  // ─── Navigation ───────────────────────────────────────────────────────────

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

  // ─── Connection test ──────────────────────────────────────────────────────

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
        result = await call<TestResult>(
          "connections/test",
          buildApiTestParams({
            name: currentName,
            templateId: apiTemplateId,
            baseUrl,
            authType: apiAuthType,
            tokenEnv: effectiveApiTokenEnv,
            apiKey,
            headerName: apiHeaderName,
            paramName: apiParamName,
            envVars: apiEnvVars,
          }),
        );
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
        result.dialect ||
          inferDialect(connectorType, { databaseUrl, detectedDialect: result.dialect }),
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
    apiTemplateId,
    apiEnvVars,
    apiParamName,
    effectiveApiTokenEnv,
    baseUrl,
    call,
    connectorType,
    connectorConfigDirty,
    connectorConfigExists,
    currentName,
    databaseUrl,
    directory,
    saveConnectorConfig,
    sqlConnectorOverrides,
  ]);

  // ─── Connection save ──────────────────────────────────────────────────────

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
          updateParams.templateId = apiTemplateId || undefined;
          updateParams.auth = {
            type: apiAuthType,
            tokenEnv: effectiveApiTokenEnv.trim(),
            headerName: apiAuthType === "header" ? apiHeaderName.trim() : undefined,
            paramName: apiAuthType === "query_param" ? apiParamName.trim() : undefined,
            usernameEnv: apiAuthType === "basic" ? apiEnvVars[0]?.name.trim() : undefined,
            passwordEnv: apiAuthType === "basic" ? apiEnvVars[1]?.name.trim() : undefined,
          };
          updateParams.envVars = apiEnvVars;
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
          createParams.templateId = apiTemplateId || undefined;
          createParams.authType = apiAuthType;
          createParams.tokenEnv = effectiveApiTokenEnv.trim() || undefined;
          createParams.headerName =
            apiAuthType === "header" ? apiHeaderName.trim() || undefined : undefined;
          createParams.paramName =
            apiAuthType === "query_param" ? apiParamName.trim() || undefined : undefined;
          createParams.envVars = apiEnvVars;
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
    apiTemplateId,
    apiEnvVars,
    apiParamName,
    effectiveApiTokenEnv,
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

  // ─── Discovery ────────────────────────────────────────────────────────────

  const runDiscovery = useCallback(async () => {
    if (!currentName) {
      setFormError("Save the connection before discovery.");
      return;
    }

    setDiscoverState({
      status: "loading",
      connectorType,
      logs:
        connectorType === "api" ? ["Inspecting API endpoints..."] : ["Looking for catalogs..."],
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
      }>("schema/catalogs", {});

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

  // ─── Onboarding completion + sampling ────────────────────────────────────

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

  // ─── Derived wizard status ────────────────────────────────────────────────

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
          : step === "discover" ||
              wizardDiscoveryStatus === "loading" ||
              wizardDiscoveryStatus === "partial"
            ? "active"
            : "idle",
    sample:
      (connectorType === "api" &&
        ((wizardDiscoveryStatus === "success" && wizardConnectDone) ||
          persistedStatuses.sample === "done")) ||
      currentConnection?.onboardingPhase?.toLowerCase() === "complete" ||
      (sampleLogs.length > 0 && !sampleError)
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

  // ─── Return value ─────────────────────────────────────────────────────────

  return {
    // navigation
    step,
    navigateToStep,
    existingName,
    currentName,
    currentConnection,
    // connector type
    connectorType,
    setConnectorType,
    // connection name
    connectionName,
    setConnectionName,
    // sql
    databaseUrl,
    setDatabaseUrl,
    displayDatabaseUrl,
    setDisplayDatabaseUrl,
    // file
    directory,
    setDirectory,
    // api
    baseUrl,
    setBaseUrl,
    apiTemplateId,
    apiTemplates,
    selectedApiTemplate,
    handleApiTemplateSelect,
    apiAuthType,
    handleApiAuthTypeChange,
    apiTokenEnv,
    apiHeaderName,
    setApiHeaderName,
    apiParamName,
    setApiParamName,
    apiKey,
    setApiKey,
    apiEnvVars,
    apiEnvFeedback,
    updateApiEnvVar,
    handleApiEnvValueChange,
    addApiEnvVar,
    handleSaveApiEnvVar,
    handleRemoveApiEnvVar,
    // connector config
    connectorConfigExists,
    connectorConfigOpen,
    setConnectorConfigOpen,
    connectorConfigLoading,
    connectorConfigSaving,
    connectorConfigError,
    setConnectorConfigError,
    connectorConfigContent,
    setConnectorConfigContent,
    connectorConfigOriginal,
    connectorConfigDirty,
    canManageConnectorConfig,
    openConnectorConfigEditor,
    saveConnectorConfig,
    // test
    testStatus,
    handleTest,
    // connect step
    saveLoading,
    formError,
    setFormError,
    handleConnectNext,
    // discover step
    discoverState,
    runDiscovery,
    // sample step
    sampleSelection,
    setSampleSelection,
    sampleLoading,
    sampleError,
    setSampleError,
    sampleRows,
    sampleLogs,
    selectedEndpoint,
    setSelectedEndpoint,
    handleSampleData,
    queryPreview,
    // summary
    summaryPrimaryLabel,
    summaryPrimaryValue,
    summaryDialect,
    wizardStatuses,
  };
}

export type WizardState = ReturnType<typeof useWizardState>;
