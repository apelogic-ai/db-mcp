import type { ConnectArgs, ConnectorType, WizardStep } from "./types";
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
