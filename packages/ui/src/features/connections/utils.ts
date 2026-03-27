import type {
  ApiEnvVarEntry,
  ApiTemplateDescriptor,
  ConnectArgs,
  ConnectorType,
  WizardStep,
} from "./types";
import type { ConnectionSummary } from "@/lib/connection-context";

export const WIZARD_STEPS: Array<{ id: WizardStep; label: string }> = [
  { id: "connect", label: "Connect and Test" },
  { id: "discover", label: "Discover" },
  { id: "sample", label: "Sample Data" },
];

export function parseConnectArgsFromUrl(
  url: string,
): ConnectArgs | undefined {
  try {
    const parsed = new URL(url);
    const params = parsed.searchParams;
    const httpScheme = params.get("http_scheme") ?? params.get("httpScheme");
    const verifyRaw = params.get("verify");
    const connectArgs: ConnectArgs = {};

    if (httpScheme) connectArgs.http_scheme = httpScheme;
    if (verifyRaw !== null) {
      const normalized = verifyRaw.trim().toLowerCase();
      connectArgs.verify = !["false", "0", "no", "off"].includes(normalized);
    }

    return Object.keys(connectArgs).length ? connectArgs : undefined;
  } catch {
    return undefined;
  }
}

function parseYamlPrimitive(rawValue: string): string | boolean | number | null {
  const withoutComment = rawValue.replace(/\s+#.*$/, "").trim();
  if (!withoutComment) {
    return null;
  }

  const trimmed = withoutComment.replace(/^['"]|['"]$/g, "");
  const normalized = trimmed.toLowerCase();
  if (["true", "yes", "on"].includes(normalized)) {
    return true;
  }
  if (["false", "no", "off"].includes(normalized)) {
    return false;
  }
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) {
    return Number(trimmed);
  }
  return trimmed;
}

export function parseSqlConnectorOverrides(content: string): {
  databaseUrl?: string;
  connectArgs?: ConnectArgs;
} {
  const stack: Array<{ indent: number; key: string }> = [];
  const connectArgs: ConnectArgs = {};
  let databaseUrl: string | undefined;

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.replace(/\t/g, "  ");
    if (!line.trim() || line.trim().startsWith("#")) {
      continue;
    }

    const match = line.match(/^(\s*)([A-Za-z0-9_-]+):(?:\s*(.*))?$/);
    if (!match) {
      continue;
    }

    const indent = match[1].length;
    const key = match[2];
    const rawValue = match[3] ?? "";

    while (stack.length && stack[stack.length - 1].indent >= indent) {
      stack.pop();
    }

    const parentPath = stack.map((entry) => entry.key);
    const value = parseYamlPrimitive(rawValue);
    const path = [...parentPath, key].join(".");

    if (path === "database_url" && typeof value === "string" && value) {
      databaseUrl = value;
    }

    if (
      (path.startsWith("connect_args.") || path.startsWith("capabilities.connect_args.")) &&
      value !== null
    ) {
      connectArgs[key] = value;
    }

    if (rawValue.trim() === "") {
      stack.push({ indent, key });
    }
  }

  return {
    databaseUrl,
    connectArgs: Object.keys(connectArgs).length ? connectArgs : undefined,
  };
}

export function maskDatabaseUrl(url: string): string {
  try {
    const match = url.match(/^(\w+):\/\/([^:]+):([^@]+)@(.+)$/);
    if (!match) {
      return url;
    }
    const [, protocol, user, , rest] = match;
    return `${protocol}://${user}:****@${rest}`;
  } catch {
    return url;
  }
}

export function wizardStepFromHash(hash: string): WizardStep {
  const normalized = hash.replace(/^#/, "");
  if (normalized === "discover" || normalized === "sample") {
    return normalized;
  }
  return "connect";
}

export function isWizardStepLocked(step: WizardStep, connectionName?: string | null): boolean {
  return step !== "connect" && !connectionName?.trim();
}

export function normalizeApiEnvEntry(entry: ApiEnvVarEntry): ApiEnvVarEntry {
  const value = entry.value || "";
  const hasSavedValue = entry.hasSavedValue || false;
  const removed = entry.removed || false;
  const masked = removed ? false : entry.masked ?? hasSavedValue;

  return {
    ...entry,
    value,
    hasSavedValue,
    masked,
    removed,
  };
}

export function applyApiEnvValueChange(entry: ApiEnvVarEntry, nextValue: string): ApiEnvVarEntry {
  const normalized = normalizeApiEnvEntry(entry);
  const trimmed = nextValue.trim();

  if (!trimmed && normalized.hasSavedValue && !normalized.removed) {
    return {
      ...normalized,
      value: "",
      masked: true,
    };
  }

  return {
    ...normalized,
    value: nextValue,
    masked: false,
    removed: false,
  };
}

export function saveApiEnvEntry(entry: ApiEnvVarEntry): ApiEnvVarEntry {
  const normalized = normalizeApiEnvEntry(entry);
  if (!normalized.value?.trim()) {
    return normalized;
  }

  return {
    ...normalized,
    hasSavedValue: true,
    masked: true,
    removed: false,
  };
}

export function clearApiEnvEntry(entry: ApiEnvVarEntry): ApiEnvVarEntry {
  const normalized = normalizeApiEnvEntry(entry);
  return {
    ...normalized,
    value: "",
    hasSavedValue: false,
    masked: false,
    removed: true,
  };
}

export function getApiEnvRowState(entry: ApiEnvVarEntry): {
  displayValue: string;
  placeholder: string;
  primaryActionLabel: "Add" | "Save" | null;
  isSaved: boolean;
  showTrash: boolean;
} {
  const normalized = normalizeApiEnvEntry(entry);
  const trimmedValue = normalized.value?.trim() || "";
  const isSaved = Boolean(normalized.hasSavedValue && normalized.masked && !trimmedValue);
  const hasDraftValue = !normalized.masked && Boolean(trimmedValue);
  const primaryActionLabel =
    normalized.hasSavedValue && !hasDraftValue
      ? null
      : hasDraftValue
        ? normalized.hasSavedValue
          ? "Save"
          : "Add"
        : "Add";

  return {
    displayValue: normalized.masked ? "" : normalized.value || "",
    placeholder: isSaved ? "*** saved ***" : normalized.prompt || "Value",
    primaryActionLabel,
    isSaved,
    showTrash: normalized.hasSavedValue || Boolean(trimmedValue) || !normalized.slot,
  };
}

export function buildApiEnvEntriesForAuth(
  authType: string,
  previousEntries: ApiEnvVarEntry[],
  options: {
    tokenEnv?: string;
    usernameEnv?: string;
    passwordEnv?: string;
  } = {},
): ApiEnvVarEntry[] {
  const previousBySlot = new Map(
    previousEntries.map((entry) => {
      const normalized = normalizeApiEnvEntry(entry);
      return [normalized.slot || normalized.name, normalized];
    }),
  );

  if (authType === "none") {
    return [];
  }

  if (authType === "basic") {
    const usernameSlot = options.usernameEnv?.trim() || "API_USERNAME";
    const passwordSlot = options.passwordEnv?.trim() || "API_PASSWORD";
    const usernamePrevious = previousBySlot.get(usernameSlot);
    const passwordPrevious = previousBySlot.get(passwordSlot);
    return [
      {
        slot: usernameSlot,
        name: usernamePrevious?.name || usernameSlot,
        value: usernamePrevious?.value || "",
        prompt: usernamePrevious?.prompt || "Username/email",
        secret: false,
        hasSavedValue: usernamePrevious?.hasSavedValue || false,
        masked: usernamePrevious?.masked ?? (usernamePrevious?.hasSavedValue || false),
        removed: usernamePrevious?.removed || false,
      },
      {
        slot: passwordSlot,
        name: passwordPrevious?.name || passwordSlot,
        value: passwordPrevious?.value || "",
        prompt: passwordPrevious?.prompt || "Password/token",
        secret: true,
        hasSavedValue: passwordPrevious?.hasSavedValue || false,
        masked: passwordPrevious?.masked ?? (passwordPrevious?.hasSavedValue || false),
        removed: passwordPrevious?.removed || false,
      },
    ];
  }

  const tokenSlot = options.tokenEnv?.trim() || "API_KEY";
  const previous = previousBySlot.get(tokenSlot) || previousEntries[0];
  return [
    {
      slot: tokenSlot,
      name: previous?.name || tokenSlot,
      value: previous?.value || "",
      prompt: previous?.prompt || "API token",
      secret: true,
      hasSavedValue: previous?.hasSavedValue || false,
      masked: previous?.masked ?? (previous?.hasSavedValue || false),
      removed: previous?.removed || false,
    },
  ];
}

export function buildApiStateFromTemplate(template: ApiTemplateDescriptor): {
  authType: string;
  tokenEnv: string;
  headerName: string;
  paramName: string;
  envVars: ApiEnvVarEntry[];
} {
  return {
    authType: template.auth.type || "bearer",
    tokenEnv: template.auth.tokenEnv || template.env[0]?.name || "",
    headerName: template.auth.headerName || "",
    paramName: template.auth.paramName || "",
    envVars: template.env.map((entry) => ({
      slot: entry.slot || entry.name,
      name: entry.name,
      value: "",
      prompt: entry.prompt,
      secret: entry.secret,
      hasSavedValue: entry.hasSavedValue || false,
      masked: entry.masked ?? (entry.hasSavedValue || false),
      removed: entry.removed || false,
    })),
  };
}

export function buildApiTestParams(options: {
  name?: string | null;
  templateId?: string;
  baseUrl: string;
  authType: string;
  tokenEnv: string;
  apiKey: string;
  headerName: string;
  paramName: string;
  envVars: ApiEnvVarEntry[];
}): Record<string, unknown> {
  const params: Record<string, unknown> = {
    connectorType: "api",
    baseUrl: options.baseUrl,
    authType: options.authType,
  };

  if (options.name?.trim()) {
    params.name = options.name.trim();
  }
  if (options.templateId?.trim()) {
    params.templateId = options.templateId.trim();
  }
  if (options.tokenEnv.trim()) {
    params.tokenEnv = options.tokenEnv.trim();
  }
  if (options.apiKey.trim()) {
    params.apiKey = options.apiKey.trim();
  }
  if (options.authType === "header" && options.headerName.trim()) {
    params.headerName = options.headerName.trim();
  }
  if (options.authType === "query_param" && options.paramName.trim()) {
    params.paramName = options.paramName.trim();
  }
  if (options.envVars.length > 0) {
    params.envVars = options.envVars
      .filter((entry) => entry.name.trim())
      .map((entry) => {
        const payload: Record<string, unknown> = {
          name: entry.name.trim(),
          secret: entry.secret,
        };
        if (entry.slot?.trim()) {
          payload.slot = entry.slot.trim();
        }
        if (entry.value?.trim()) {
          payload.value = entry.value.trim();
        }
        if (entry.removed) {
          payload.removed = true;
        }
        if (entry.prompt?.trim()) {
          payload.prompt = entry.prompt.trim();
        }
        return payload;
      });
  }

  return params;
}

export function buildWizardHref(
  step: WizardStep,
  options: { name?: string; type?: ConnectorType } = {},
): string {
  const params = new URLSearchParams();
  if (options.name) {
    params.set("name", options.name);
  }
  if (options.type) {
    params.set("type", options.type);
  }
  const search = params.toString();
  return `/connection/new${search ? `?${search}` : ""}#${step}`;
}

type WizardCheckpointStatus = "idle" | "active" | "done";

export function getWizardResumeStep(connection: Pick<
  ConnectionSummary,
  "onboardingPhase" | "hasSchema" | "hasDiscovery" | "hasDomain" | "hasCredentials" | "connectorType"
>): WizardStep {
  const statuses = getPersistedWizardStatuses(connection);

  if (statuses.connect !== "done") {
    return "connect";
  }

  if (statuses.discover !== "done") {
    return "discover";
  }

  if (statuses.sample !== "done") {
    return "sample";
  }

  return connection.connectorType === "api" ? "discover" : "sample";
}

export function getPersistedWizardStatuses(connection: Pick<
  ConnectionSummary,
  "onboardingPhase" | "hasSchema" | "hasDiscovery" | "hasDomain" | "hasCredentials" | "connectorType"
>): Record<WizardStep, WizardCheckpointStatus> {
  const complete = (connection.onboardingPhase || "").toLowerCase() === "complete";
  const phase = (connection.onboardingPhase || "").toLowerCase();
  const connectDone = Boolean(connection.hasCredentials);
  const discoverDone = Boolean(connection.hasDiscovery) ||
    ["discover", "sample", "review", "complete"].includes(phase);
  const sampleDone = connection.connectorType === "api" ? discoverDone : complete;
  const resumeStep = complete
    ? connection.connectorType === "api"
      ? "discover"
      : "sample"
    : !connectDone
      ? "connect"
      : !discoverDone
        ? "discover"
        : "sample";

  return {
    connect: connectDone ? "done" : resumeStep === "connect" ? "active" : "idle",
    discover: discoverDone ? "done" : resumeStep === "discover" ? "active" : "idle",
    sample: sampleDone ? "done" : resumeStep === "sample" ? "active" : "idle",
  };
}

export function buildConnectionHref(
  name: string,
  section: "overview" | "insights" | "knowledge" = "overview",
): string {
  return buildConnectionRoute(name, section).href;
}

export function buildConnectionAppHref(
  name: string,
  section: "overview" | "insights" | "knowledge" = "overview",
): string {
  return buildConnectionRoute(name, section).appHref;
}

export function buildConnectionRoute(
  name: string,
  section: "overview" | "insights" | "knowledge" = "overview",
): { href: string; appHref: string } {
  const encodedName = encodeURIComponent(name);
  if (section === "insights") {
    return {
      href: `/connection/${encodedName}/insights`,
      appHref: `/connection/insights?name=${encodedName}`,
    };
  }
  if (section === "knowledge") {
    return {
      href: `/connection/${encodedName}/knowledge`,
      appHref: `/connection/knowledge?name=${encodedName}`,
    };
  }
  return {
    href: `/connection/${encodedName}`,
    appHref: `/connection?name=${encodedName}`,
  };
}

export function resolveConnectionName(
  pathname: string,
  searchParams: URLSearchParams | ReadonlyURLSearchParamsLike,
): string | null {
  const queryName = searchParams.get("name");
  if (queryName) {
    return queryName;
  }

  const pathSegments = pathname.split("/").filter(Boolean);
  const candidate = pathSegments[0] === "connection" ? pathSegments[1] : null;

  if (!candidate || candidate === "new" || candidate === "insights" || candidate === "knowledge") {
    return null;
  }

  return decodeURIComponent(candidate);
}

type ReadonlyURLSearchParamsLike = {
  get(name: string): string | null;
};

export function inferDialect(
  connectorType: ConnectorType,
  values: {
    databaseUrl?: string;
    directory?: string;
    baseUrl?: string;
    detectedDialect?: string | null;
  },
): string {
  if (values.detectedDialect) {
    return values.detectedDialect;
  }

  if (connectorType === "file") {
    return "duckdb";
  }

  if (connectorType === "api") {
    return "API connector";
  }

  const candidate = (values.databaseUrl || "").toLowerCase();
  if (candidate.startsWith("postgresql://") || candidate.startsWith("postgres://")) {
    return "PostgreSQL";
  }
  if (candidate.startsWith("clickhouse")) {
    return "ClickHouse";
  }
  if (candidate.startsWith("trino://")) {
    return "Trino";
  }
  if (candidate.startsWith("mysql://")) {
    return "MySQL";
  }
  if (candidate.startsWith("mssql://") || candidate.startsWith("sqlserver://")) {
    return "SQL Server";
  }
  if (candidate.startsWith("sqlite://")) {
    return "SQLite";
  }
  return "Pending test";
}

export function summarizeConnectionState(
  hasSchema: boolean,
  hasDomain: boolean,
): string {
  if (hasSchema && hasDomain) {
    return "Ready";
  }
  if (hasSchema || hasDomain) {
    return "In progress";
  }
  return "Needs setup";
}

export type ConnectionOnboardingTone = "complete" | "partial" | "missing";

export function getConnectionOnboardingTone(connection: {
  onboardingPhase?: string | null;
  hasSchema?: boolean;
  hasDiscovery?: boolean;
  hasDomain?: boolean;
  hasCredentials?: boolean;
  connectorType?: ConnectorType;
}): ConnectionOnboardingTone {
  const statuses = getPersistedWizardStatuses({
    onboardingPhase: connection.onboardingPhase ?? null,
    hasSchema: connection.hasSchema ?? false,
    hasDiscovery: connection.hasDiscovery ?? false,
    hasDomain: connection.hasDomain ?? false,
    hasCredentials: connection.hasCredentials ?? false,
    connectorType: connection.connectorType,
  });

  if (statuses.connect === "done" && statuses.discover === "done" && statuses.sample === "done") {
    return "complete";
  }

  if (statuses.connect !== "idle" || statuses.discover !== "idle" || statuses.sample !== "idle") {
    return "partial";
  }

  return "missing";
}

export function getConnectionOnboardingDotClass(
  connection: Pick<
    ConnectionSummary,
    "onboardingPhase" | "hasSchema" | "hasDiscovery" | "hasDomain" | "hasCredentials" | "connectorType"
  >,
): string {
  const tone = getConnectionOnboardingTone(connection);
  if (tone === "complete") {
    return "bg-emerald-400";
  }
  if (tone === "partial") {
    return "bg-amber-400";
  }
  return "bg-gray-500";
}

export function parseDbLink(link: string): {
  catalog: string | null;
  schema: string | null;
  table: string | null;
  column: string | null;
} {
  const stripped = link.replace(/^db:\/\//, "");
  const parts = stripped.split("/").filter(Boolean);
  return {
    catalog: normalizeDbSegment(parts[0]),
    schema: normalizeDbSegment(parts[1]),
    table: normalizeDbSegment(parts[2]),
    column: normalizeDbSegment(parts[3]),
  };
}

export function formatTableTarget(target: {
  catalog?: string | null;
  schema?: string | null;
  table?: string | null;
}): string {
  return [target.catalog, target.schema, target.table]
    .map(normalizeDbSegment)
    .filter(Boolean)
    .join(".");
}

export function normalizeDbSegment(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const normalized = value.trim();
  if (
    !normalized ||
    normalized === "__default__" ||
    normalized.toLowerCase() === "null" ||
    normalized.toLowerCase() === "undefined"
  ) {
    return null;
  }

  return normalized;
}
