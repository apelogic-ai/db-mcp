"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useBICP } from "@/lib/bicp-context";
import AgentConfig from "@/components/AgentConfig";
import { DialectIcon } from "@/components/DialectIcon";

interface Connection {
  name: string;
  isActive: boolean;
  hasSchema: boolean;
  hasDomain: boolean;
  hasCredentials: boolean;
  dialect: string | null;
  onboardingPhase: string | null;
  connectorType: "sql" | "file" | "api";
}

interface ConnectionsListResult {
  connections: Connection[];
  activeConnection: string | null;
}

interface CreateResult {
  success: boolean;
  name?: string;
  dialect?: string;
  error?: string;
}

interface TestResult {
  success: boolean;
  message?: string;
  dialect?: string;
  error?: string;
  hint?: string;
  sources?: Record<string, string>;
}

interface DeleteResult {
  success: boolean;
  error?: string;
}

interface GetResult {
  success: boolean;
  name?: string;
  databaseUrl?: string;
  connectorType?: "sql" | "file" | "api";
  directory?: string;
  baseUrl?: string;
  auth?: {
    type: string;
    tokenEnv: string;
    headerName: string;
    paramName: string;
  };
  endpoints?: Array<{ name: string; path: string; method: string }>;
  pagination?: {
    type: string;
    cursorParam: string;
    cursorField: string;
    pageSizeParam: string;
    pageSize: number;
    dataField: string;
  };
  rateLimitRps?: number;
  error?: string;
}

interface UpdateResult {
  success: boolean;
  error?: string;
}

// Inline status indicator (spinner / check / X)
function StatusIndicator({
  testStatus,
}: {
  testStatus: {
    testing: boolean;
    success: boolean | null;
    message: string;
    hint?: string;
  } | null;
}) {
  if (!testStatus) return null;
  if (testStatus.testing) {
    return (
      <svg
        className="animate-spin h-4 w-4 text-gray-400"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
    );
  }
  if (testStatus.success === true) {
    return (
      <span title={testStatus.message}>
        <svg
          className="h-4 w-4 text-green-500"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
      </span>
    );
  }
  if (testStatus.success === false) {
    return (
      <span title={testStatus.message}>
        <svg
          className="h-4 w-4 text-red-500"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
            clipRule="evenodd"
          />
        </svg>
      </span>
    );
  }
  return null;
}

export default function ConfigPage() {
  const { isInitialized, isLoading, error, serverInfo, initialize, call } =
    useBICP();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionsLoading, setConnectionsLoading] = useState(false);
  const [connectionsError, setConnectionsError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  // Create/Edit form state
  const [showCreateSqlForm, setShowCreateSqlForm] = useState(false);
  const [showCreateFileForm, setShowCreateFileForm] = useState(false);
  const [showCreateApiForm, setShowCreateApiForm] = useState(false);
  const [editingConnection, setEditingConnection] = useState<string | null>(
    null,
  );
  const [editingType, setEditingType] = useState<"sql" | "file" | "api">("sql");
  const [fullDatabaseUrl, setFullDatabaseUrl] = useState("");
  const [displayDatabaseUrl, setDisplayDatabaseUrl] = useState("");
  const [urlModified, setUrlModified] = useState(false);
  const [directoryPath, setDirectoryPath] = useState("");
  const [newName, setNewName] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<{
    testing: boolean;
    success: boolean | null;
    message: string;
    hint?: string;
  } | null>(null);

  // API form state
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [apiAuthType, setApiAuthType] = useState("bearer");
  const [apiTokenEnv, setApiTokenEnv] = useState("");
  const [apiHeaderName, setApiHeaderName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [syncLoading, setSyncLoading] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [discoverLoading, setDiscoverLoading] = useState<string | null>(null);
  const [discoverResult, setDiscoverResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);

  // Auto-test debounce
  const testTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Filtered connection lists
  const sqlConnections = connections.filter(
    (c) => c.connectorType !== "file" && c.connectorType !== "api",
  );
  const fileConnections = connections.filter((c) => c.connectorType === "file");
  const apiConnections = connections.filter((c) => c.connectorType === "api");

  const maskDatabaseUrl = (url: string): string => {
    try {
      const match = url.match(/^(\w+):\/\/([^:]+):([^@]+)@(.+)$/);
      if (match) {
        const [, protocol, user, , rest] = match;
        return `${protocol}://${user}:****@${rest}`;
      }
      return url;
    } catch {
      return url;
    }
  };

  const resetFormState = () => {
    setShowCreateSqlForm(false);
    setShowCreateFileForm(false);
    setShowCreateApiForm(false);
    setEditingConnection(null);
    setFullDatabaseUrl("");
    setDisplayDatabaseUrl("");
    setDirectoryPath("");
    setUrlModified(false);
    setNewName("");
    setTestStatus(null);
    setCreateError(null);
    setApiBaseUrl("");
    setApiAuthType("bearer");
    setApiTokenEnv("");
    setApiHeaderName("");
    setApiKey("");
    setSyncResult(null);
  };

  const fetchConnections = useCallback(async () => {
    setConnectionsLoading(true);
    setConnectionsError(null);
    try {
      const result = await call<ConnectionsListResult>("connections/list", {});
      setConnections(result.connections);
    } catch (err) {
      setConnectionsError(
        err instanceof Error ? err.message : "Failed to fetch connections",
      );
    } finally {
      setConnectionsLoading(false);
    }
  }, [call]);

  useEffect(() => {
    if (isInitialized && !hasFetched) {
      setHasFetched(true);
      fetchConnections();
    }
  }, [isInitialized, hasFetched, fetchConnections]);

  const handleSwitchConnection = async (name: string) => {
    try {
      await call("connections/switch", { name });
      await fetchConnections();
    } catch (err) {
      setConnectionsError(
        err instanceof Error ? err.message : "Failed to switch connection",
      );
    }
  };

  const handleTestConnection = useCallback(
    async (url?: string, dir?: string, type?: "sql" | "file" | "api") => {
      const effectiveType = type ?? editingType;

      if (effectiveType === "api") {
        const baseUrlToTest = url ?? apiBaseUrl;
        if (!baseUrlToTest.trim()) return;

        setTestStatus({ testing: true, success: null, message: "" });
        try {
          const result = await call<TestResult>("connections/test", {
            connectorType: "api",
            baseUrl: baseUrlToTest,
            apiKey: apiKey || undefined,
            authType: apiAuthType,
            headerName:
              apiAuthType === "header" ? apiHeaderName || undefined : undefined,
          });
          setTestStatus({
            testing: false,
            success: result.success,
            message: result.success
              ? result.message || "API reachable"
              : result.error || "Connection failed",
          });
        } catch (err) {
          setTestStatus({
            testing: false,
            success: false,
            message: err instanceof Error ? err.message : "Test failed",
          });
        }
        return;
      }

      if (effectiveType === "file") {
        const dirToTest = dir ?? directoryPath;
        if (!dirToTest.trim()) return;

        setTestStatus({ testing: true, success: null, message: "" });
        try {
          const result = await call<TestResult>("connections/test", {
            connectorType: "file",
            directory: dirToTest,
          });
          const sourceCount = result.sources
            ? Object.keys(result.sources).length
            : 0;
          setTestStatus({
            testing: false,
            success: result.success,
            message: result.success
              ? `Found ${sourceCount} table${sourceCount !== 1 ? "s" : ""}`
              : result.error || "Connection failed",
            hint: result.hint || undefined,
          });
        } catch (err) {
          setTestStatus({
            testing: false,
            success: false,
            message: err instanceof Error ? err.message : "Test failed",
          });
        }
        return;
      }

      const urlToTest = url ?? fullDatabaseUrl;
      if (!urlToTest.trim()) return;

      if (urlToTest.includes("****")) {
        setTestStatus({
          testing: false,
          success: false,
          message: "Enter the full URL including password to test",
        });
        return;
      }

      setTestStatus({ testing: true, success: null, message: "" });
      try {
        const result = await call<TestResult>("connections/test", {
          connectorType: "sql",
          databaseUrl: urlToTest,
        });
        setTestStatus({
          testing: false,
          success: result.success,
          message: result.success
            ? result.dialect || "Connected"
            : result.error || "Connection failed",
          hint: result.hint || undefined,
        });
      } catch (err) {
        setTestStatus({
          testing: false,
          success: false,
          message: err instanceof Error ? err.message : "Test failed",
        });
      }
    },
    [
      call,
      fullDatabaseUrl,
      directoryPath,
      editingType,
      apiBaseUrl,
      apiKey,
      apiAuthType,
    ],
  );

  const handleDatabaseUrlChange = (value: string) => {
    setDisplayDatabaseUrl(value);
    setFullDatabaseUrl(value);
    setUrlModified(true);
    setTestStatus(null);

    if (testTimeoutRef.current) clearTimeout(testTimeoutRef.current);

    if (value.includes("://") && value.length > 15 && !value.includes("****")) {
      testTimeoutRef.current = setTimeout(() => {
        handleTestConnection(value, undefined, "sql");
      }, 800);
    }
  };

  const handleDirectoryPathChange = (value: string) => {
    setDirectoryPath(value);
    setUrlModified(true);
    setTestStatus(null);

    if (testTimeoutRef.current) clearTimeout(testTimeoutRef.current);

    if (value.startsWith("/") && value.length > 1) {
      testTimeoutRef.current = setTimeout(() => {
        handleTestConnection(undefined, value, "file");
      }, 800);
    }
  };

  const handleCreateConnection = async (type: "sql" | "file" | "api") => {
    if (type === "api") {
      if (!newName.trim() || !apiBaseUrl.trim()) {
        setCreateError("Name and Base URL are required");
        return;
      }
    } else if (type === "file") {
      if (!newName.trim() || !directoryPath.trim()) {
        setCreateError("Name and Directory Path are required");
        return;
      }
    } else {
      if (!newName.trim() || !fullDatabaseUrl.trim()) {
        setCreateError("Name and Database URL are required");
        return;
      }
    }

    setCreateLoading(true);
    setCreateError(null);
    try {
      const params: Record<string, unknown> = {
        name: newName.trim(),
        connectorType: type,
        setActive: true,
      };
      if (type === "api") {
        params.baseUrl = apiBaseUrl.trim();
        params.authType = apiAuthType;
        params.tokenEnv = apiTokenEnv.trim() || undefined;
        params.headerName =
          apiAuthType === "header"
            ? apiHeaderName.trim() || undefined
            : undefined;
        params.apiKey = apiKey.trim() || undefined;
      } else if (type === "file") {
        params.directory = directoryPath.trim();
      } else {
        params.databaseUrl = fullDatabaseUrl.trim();
      }

      const result = await call<CreateResult>("connections/create", params);

      if (result.success) {
        resetFormState();
        await fetchConnections();
      } else {
        setCreateError(result.error || "Failed to create connection");
      }
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : "Failed to create connection",
      );
    } finally {
      setCreateLoading(false);
    }
  };

  const handleDeleteConnection = async (name: string) => {
    if (!confirm(`Delete connection "${name}"? This cannot be undone.`)) return;

    try {
      const result = await call<DeleteResult>("connections/delete", { name });
      if (result.success) {
        if (editingConnection === name) resetFormState();
        await fetchConnections();
      } else {
        setConnectionsError(result.error || "Failed to delete connection");
      }
    } catch (err) {
      setConnectionsError(
        err instanceof Error ? err.message : "Failed to delete connection",
      );
    }
  };

  const handleEditConnection = async (name: string) => {
    try {
      const result = await call<GetResult>("connections/get", { name });
      if (result.success) {
        const type = result.connectorType || "sql";
        resetFormState();
        setEditingConnection(name);
        setEditingType(type);
        setNewName(name);

        if (type === "api") {
          setApiBaseUrl(result.baseUrl || "");
          setApiAuthType(result.auth?.type || "bearer");
          setApiTokenEnv(result.auth?.tokenEnv || "");
          setApiHeaderName(result.auth?.headerName || "");
        } else if (type === "file") {
          setDirectoryPath(result.directory || "");
        } else {
          const url = result.databaseUrl || "";
          setFullDatabaseUrl(url);
          setDisplayDatabaseUrl(maskDatabaseUrl(url));
        }
      } else {
        setConnectionsError(result.error || "Failed to get connection details");
      }
    } catch (err) {
      setConnectionsError(
        err instanceof Error ? err.message : "Failed to get connection details",
      );
    }
  };

  const handleUpdateConnection = async () => {
    if (!editingConnection) return;

    if (editingType === "api") {
      if (!apiBaseUrl.trim()) {
        setCreateError("Base URL is required");
        return;
      }
    } else if (editingType === "file") {
      if (!directoryPath.trim()) {
        setCreateError("Directory Path is required");
        return;
      }
    } else {
      if (!fullDatabaseUrl.trim()) {
        setCreateError("Database URL is required");
        return;
      }
      if (fullDatabaseUrl.includes("****")) {
        setCreateError(
          "Please enter the full database URL including the password",
        );
        return;
      }
    }

    setCreateLoading(true);
    setCreateError(null);
    try {
      const params: Record<string, unknown> = { name: editingConnection };
      if (editingType === "api") {
        params.baseUrl = apiBaseUrl.trim();
        params.auth = {
          type: apiAuthType,
          tokenEnv: apiTokenEnv.trim(),
          headerName:
            apiAuthType === "header" ? apiHeaderName.trim() : undefined,
        };
        if (apiKey.trim()) {
          params.apiKey = apiKey.trim();
        }
      } else if (editingType === "file") {
        params.directory = directoryPath.trim();
      } else {
        params.databaseUrl = fullDatabaseUrl.trim();
      }

      const result = await call<UpdateResult>("connections/update", params);

      if (result.success) {
        resetFormState();
        await fetchConnections();
      } else {
        setCreateError(result.error || "Failed to update connection");
      }
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : "Failed to update connection",
      );
    } finally {
      setCreateLoading(false);
    }
  };

  const handleSyncConnection = async (name: string) => {
    setSyncLoading(name);
    setSyncResult(null);
    try {
      const result = await call<{
        success: boolean;
        synced?: string[];
        rows_fetched?: Record<string, number>;
        errors?: string[];
        error?: string;
      }>("connections/sync", { name });

      if (result.success) {
        const synced = result.synced || [];
        const totalRows = Object.values(result.rows_fetched || {}).reduce(
          (a, b) => a + b,
          0,
        );
        setSyncResult({
          success: true,
          message: `Synced ${synced.length} endpoint${synced.length !== 1 ? "s" : ""} (${totalRows} rows)`,
        });
      } else {
        setSyncResult({
          success: false,
          message: result.error || "Sync failed",
        });
      }
    } catch (err) {
      setSyncResult({
        success: false,
        message: err instanceof Error ? err.message : "Sync failed",
      });
    } finally {
      setSyncLoading(null);
    }
  };

  const handleDiscoverEndpoints = async (name: string) => {
    setDiscoverLoading(name);
    setDiscoverResult(null);
    try {
      const result = await call<{
        success: boolean;
        strategy?: string;
        endpoints_found?: number;
        api_title?: string;
        endpoints?: Array<{ name: string; path: string; fields: number }>;
        errors?: string[];
        error?: string;
      }>("connections/discover", { name });

      if (result.success && (result.endpoints_found || 0) > 0) {
        const title = result.api_title ? ` (${result.api_title})` : "";
        setDiscoverResult({
          success: true,
          message: `Found ${result.endpoints_found} endpoint${result.endpoints_found !== 1 ? "s" : ""} via ${result.strategy}${title}`,
        });
        // Refresh connections list to show updated endpoint count
        await fetchConnections();
      } else if (result.success) {
        setDiscoverResult({
          success: false,
          message: "No endpoints discovered. Configure endpoints manually.",
        });
      } else {
        setDiscoverResult({
          success: false,
          message: result.error || "Discovery failed",
        });
      }
    } catch (err) {
      setDiscoverResult({
        success: false,
        message: err instanceof Error ? err.message : "Discovery failed",
      });
    } finally {
      setDiscoverLoading(null);
    }
  };

  const getDialectBadge = (dialect: string | null) => {
    if (!dialect) return null;
    const colors: Record<string, string> = {
      postgresql: "bg-blue-900 text-blue-300",
      clickhouse: "bg-yellow-900 text-yellow-300",
      trino: "bg-purple-900 text-purple-300",
      mysql: "bg-brand/20 text-brand-light",
      mssql: "bg-red-900 text-red-300",
      sqlite: "bg-gray-700 text-gray-300",
      duckdb: "bg-amber-900 text-amber-300",
    };
    return (
      <Badge className={colors[dialect] || "bg-gray-700 text-gray-300"}>
        {dialect}
      </Badge>
    );
  };

  const getOnboardingBadge = (phase: string | null) => {
    if (!phase) return null;
    const phaseLabels: Record<string, { label: string; color: string }> = {
      discovery: { label: "Discovery", color: "bg-blue-900 text-blue-300" },
      review: { label: "Review", color: "bg-yellow-900 text-yellow-300" },
      "domain-building": {
        label: "Building",
        color: "bg-purple-900 text-purple-300",
      },
      complete: { label: "Complete", color: "bg-brand/20 text-brand-light" },
    };
    const info = phaseLabels[phase] || {
      label: phase,
      color: "bg-gray-700 text-gray-300",
    };
    return <Badge className={info.color}>{info.label}</Badge>;
  };

  // Shared connection list item renderer
  const renderConnectionItem = (conn: Connection) => (
    <div key={conn.name}>
      <div
        className={`p-4 rounded-lg border ${
          conn.isActive
            ? "bg-brand/10 border-brand/30"
            : "bg-gray-900 border-gray-800 hover:border-gray-700"
        } ${editingConnection === conn.name ? "rounded-b-none border-b-0" : ""}`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <DialectIcon dialect={conn.dialect} size={20} className={conn.isActive ? "text-brand" : ""} />
            <span className="text-white font-medium">{conn.name}</span>
            {conn.isActive && (
              <Badge className="bg-brand/20 text-brand-light text-xs">
                Active
              </Badge>
            )}
            {getDialectBadge(conn.dialect)}
            {getOnboardingBadge(conn.onboardingPhase)}
          </div>
          <div className="flex items-center gap-2">
            {!conn.isActive && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleSwitchConnection(conn.name)}
                className="text-xs border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300"
              >
                Switch
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                editingConnection === conn.name
                  ? resetFormState()
                  : handleEditConnection(conn.name)
              }
              className={`text-xs border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 ${editingConnection === conn.name ? "bg-gray-800" : ""}`}
            >
              {editingConnection === conn.name ? "Cancel" : "Edit"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleDeleteConnection(conn.name)}
              className="text-xs border-red-800 bg-gray-900 text-red-400 hover:bg-red-950 hover:text-red-300"
            >
              Delete
            </Button>
          </div>
        </div>
        <div className="mt-2 flex gap-4 text-xs text-gray-500">
          <span
            className={
              conn.connectorType === "file" || conn.hasCredentials
                ? "text-green-500"
                : "text-gray-600"
            }
          >
            {conn.connectorType === "api"
              ? "API"
              : conn.connectorType === "file"
                ? "Directory"
                : conn.hasCredentials
                  ? "Credentials"
                  : "No credentials"}
          </span>
          <span className={conn.hasSchema ? "text-green-500" : "text-gray-600"}>
            {conn.hasSchema ? "Schema" : "No schema"}
          </span>
          <span className={conn.hasDomain ? "text-green-500" : "text-gray-600"}>
            {conn.hasDomain ? "Domain" : "No domain"}
          </span>
        </div>
      </div>

      {/* Inline Edit Form */}
      {editingConnection === conn.name && (
        <div className="p-4 bg-gray-950 border border-gray-800 border-t-0 rounded-b-lg space-y-4">
          {editingType === "api" ? (
            <>
              <div className="space-y-2">
                <label className="text-sm text-gray-400">Base URL</label>
                <div className="relative">
                  <Input
                    placeholder="https://api.example.com/v1"
                    value={apiBaseUrl}
                    onChange={(e) => {
                      setApiBaseUrl(e.target.value);
                      setUrlModified(true);
                    }}
                    className="bg-gray-900 border-gray-700 text-white font-mono text-sm pr-10"
                  />
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    <StatusIndicator testStatus={testStatus} />
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm text-gray-400">Auth Type</label>
                  <select
                    value={apiAuthType}
                    onChange={(e) => {
                      setApiAuthType(e.target.value);
                      setUrlModified(true);
                    }}
                    className="w-full bg-gray-900 border border-gray-700 text-white rounded-md px-3 py-2 text-sm"
                  >
                    <option value="bearer">Bearer Token</option>
                    <option value="header">Custom Header</option>
                    <option value="query_param">Query Parameter</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-gray-400">
                    {apiAuthType === "query_param"
                      ? "Query Param Name"
                      : "Env Var Name"}
                  </label>
                  <Input
                    placeholder={
                      apiAuthType === "query_param" ? "api_key" : "API_KEY"
                    }
                    value={apiTokenEnv}
                    onChange={(e) => {
                      setApiTokenEnv(e.target.value);
                      setUrlModified(true);
                    }}
                    className="bg-gray-900 border-gray-700 text-white font-mono text-sm"
                  />
                </div>
              </div>
              {apiAuthType === "header" && (
                <div className="space-y-2">
                  <label className="text-sm text-gray-400">Header Name</label>
                  <Input
                    placeholder="X-Api-Key"
                    value={apiHeaderName}
                    onChange={(e) => {
                      setApiHeaderName(e.target.value);
                      setUrlModified(true);
                    }}
                    className="bg-gray-900 border-gray-700 text-white font-mono text-sm"
                  />
                </div>
              )}
              <div className="space-y-2">
                <label className="text-sm text-gray-400">
                  API Key (optional, updates .env)
                </label>
                <Input
                  placeholder="sk-..."
                  type="password"
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    setUrlModified(true);
                  }}
                  className="bg-gray-900 border-gray-700 text-white font-mono text-sm"
                />
              </div>
              {testStatus &&
                !testStatus.testing &&
                testStatus.success === false && (
                  <p className="text-xs text-red-400">{testStatus.message}</p>
                )}
              {testStatus &&
                !testStatus.testing &&
                testStatus.success === true && (
                  <p className="text-xs text-green-400">{testStatus.message}</p>
                )}
            </>
          ) : editingType === "file" ? (
            <div className="space-y-2">
              <label className="text-sm text-gray-400">Directory Path</label>
              <div className="relative">
                <Input
                  placeholder="/path/to/your/data"
                  value={directoryPath}
                  onChange={(e) => handleDirectoryPathChange(e.target.value)}
                  className="bg-gray-900 border-gray-700 text-white font-mono text-sm pr-10"
                />
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <StatusIndicator testStatus={testStatus} />
                </div>
              </div>
              <p className="text-xs text-gray-500">
                Point to a directory containing CSV, Parquet, or JSON files.
                {testStatus &&
                  !testStatus.testing &&
                  testStatus.success === true && (
                    <span className="text-green-400 ml-2">
                      {testStatus.message}
                    </span>
                  )}
                {testStatus &&
                  !testStatus.testing &&
                  testStatus.success === false && (
                    <span className="text-red-400 ml-2">
                      {testStatus.message}
                    </span>
                  )}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <label className="text-sm text-gray-400">Database URL</label>
              <div className="relative">
                <Input
                  placeholder="postgresql://user:pass@host:5432/database"
                  value={displayDatabaseUrl}
                  onChange={(e) => handleDatabaseUrlChange(e.target.value)}
                  className="bg-gray-900 border-gray-700 text-white font-mono text-sm pr-10"
                />
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <StatusIndicator testStatus={testStatus} />
                </div>
              </div>
              <p className="text-xs text-gray-500">
                Supports: PostgreSQL, ClickHouse, Trino, MySQL, SQL Server
                {testStatus &&
                  !testStatus.testing &&
                  testStatus.success === false && (
                    <>
                      <span className="text-red-400 ml-2">
                        {testStatus.message}
                      </span>
                      {testStatus.hint && (
                        <span className="text-yellow-400 ml-1">
                          {testStatus.hint}
                        </span>
                      )}
                    </>
                  )}
              </p>
            </div>
          )}

          {createError && (
            <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
              {createError}
            </div>
          )}

          <div className="flex items-center gap-2 justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                handleTestConnection(undefined, undefined, editingType)
              }
              disabled={
                testStatus?.testing ||
                (editingType === "api"
                  ? !apiBaseUrl.trim()
                  : editingType === "file"
                    ? !directoryPath.trim()
                    : !fullDatabaseUrl.trim())
              }
              className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
            >
              {testStatus?.testing ? "Testing..." : "Test"}
            </Button>
            <Button
              onClick={handleUpdateConnection}
              size="sm"
              disabled={createLoading || !urlModified}
              className="bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 text-xs"
            >
              {createLoading ? "Updating..." : "Update"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Configuration</h1>
        <p className="text-gray-400 mt-1">
          Manage connections and agent settings
        </p>
      </div>

      {/* Connection error banner */}
      {error && (
        <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
          Connection error: {error.message}
        </div>
      )}

      {connectionsError && (
        <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
          {connectionsError}
        </div>
      )}

      {/* Section 1: Database Connections */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-white flex items-center gap-2">
                Database Connections
                {connectionsLoading && (
                  <Badge
                    variant="secondary"
                    className="bg-gray-800 text-gray-300"
                  >
                    Loading...
                  </Badge>
                )}
              </CardTitle>
              <CardDescription className="text-gray-400">
                Connect to PostgreSQL, ClickHouse, Trino, MySQL, or SQL Server.
              </CardDescription>
            </div>
            {isInitialized && !showCreateSqlForm && (
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={fetchConnections}
                  disabled={connectionsLoading}
                  className="text-gray-400 hover:text-white hover:bg-gray-800"
                  title="Refresh"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={connectionsLoading ? "animate-spin" : ""}
                  >
                    <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
                    <path d="M21 3v5h-5" />
                  </svg>
                </Button>
                <Button
                  onClick={() => {
                    resetFormState();
                    setShowCreateSqlForm(true);
                  }}
                  className="bg-brand hover:bg-brand-dark text-white"
                >
                  + Add Database
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {/* Create SQL Connection Form */}
          {showCreateSqlForm && (
            <div className="p-4 bg-gray-950 border border-gray-800 rounded-lg mb-4 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-white font-medium">
                  New Database Connection
                </h3>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      handleTestConnection(undefined, undefined, "sql")
                    }
                    disabled={testStatus?.testing || !fullDatabaseUrl.trim()}
                    className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                  >
                    {testStatus?.testing ? "Testing..." : "Test"}
                  </Button>
                  <Button
                    onClick={() => handleCreateConnection("sql")}
                    size="sm"
                    disabled={
                      createLoading ||
                      !newName.trim() ||
                      !fullDatabaseUrl.trim()
                    }
                    className="bg-brand hover:bg-brand-dark text-white disabled:opacity-50 text-xs"
                  >
                    {createLoading ? "Creating..." : "Create"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={resetFormState}
                    className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                  >
                    Cancel
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm text-gray-400">Connection Name</label>
                <Input
                  placeholder="my-database"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="bg-gray-900 border-gray-700 text-white"
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm text-gray-400">Database URL</label>
                <div className="relative">
                  <Input
                    placeholder="postgresql://user:pass@host:5432/database"
                    value={displayDatabaseUrl}
                    onChange={(e) => handleDatabaseUrlChange(e.target.value)}
                    className="bg-gray-900 border-gray-700 text-white font-mono text-sm pr-10"
                  />
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    <StatusIndicator testStatus={testStatus} />
                  </div>
                </div>
                <p className="text-xs text-gray-500">
                  Supports: PostgreSQL, ClickHouse, Trino, MySQL, SQL Server
                  {testStatus &&
                    !testStatus.testing &&
                    testStatus.success === false && (
                      <>
                        <span className="text-red-400 ml-2">
                          {testStatus.message}
                        </span>
                        {testStatus.hint && (
                          <span className="text-yellow-400 ml-1">
                            {testStatus.hint}
                          </span>
                        )}
                      </>
                    )}
                </p>
              </div>

              {createError && (
                <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
                  {createError}
                </div>
              )}
            </div>
          )}

          {!isInitialized ? (
            <p className="text-gray-500 text-sm">
              Connecting to BICP server...
            </p>
          ) : sqlConnections.length === 0 &&
            !connectionsLoading &&
            !showCreateSqlForm ? (
            <div className="text-center py-8">
              <p className="text-gray-500 text-sm mb-4">
                No database connections configured yet.
              </p>
              <Button
                onClick={() => {
                  resetFormState();
                  setShowCreateSqlForm(true);
                }}
                className="bg-brand hover:bg-brand-dark text-white"
              >
                + Add Your First Database
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {sqlConnections.map(renderConnectionItem)}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Section 2: File Connections */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-white flex items-center gap-2">
                File Connections
                {connectionsLoading && (
                  <Badge
                    variant="secondary"
                    className="bg-gray-800 text-gray-300"
                  >
                    Loading...
                  </Badge>
                )}
              </CardTitle>
              <CardDescription className="text-gray-400">
                Query local CSV, Parquet, and JSON files using DuckDB.
              </CardDescription>
            </div>
            {isInitialized && !showCreateFileForm && (
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={fetchConnections}
                  disabled={connectionsLoading}
                  className="text-gray-400 hover:text-white hover:bg-gray-800"
                  title="Refresh"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={connectionsLoading ? "animate-spin" : ""}
                  >
                    <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
                    <path d="M21 3v5h-5" />
                  </svg>
                </Button>
                <Button
                  onClick={() => {
                    resetFormState();
                    setShowCreateFileForm(true);
                  }}
                  className="bg-brand hover:bg-brand-dark text-white"
                >
                  + Add File Connection
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {/* Create File Connection Form */}
          {showCreateFileForm && (
            <div className="p-4 bg-gray-950 border border-gray-800 rounded-lg mb-4 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-white font-medium">New File Connection</h3>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      handleTestConnection(undefined, undefined, "file")
                    }
                    disabled={testStatus?.testing || !directoryPath.trim()}
                    className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                  >
                    {testStatus?.testing ? "Testing..." : "Test"}
                  </Button>
                  <Button
                    onClick={() => handleCreateConnection("file")}
                    size="sm"
                    disabled={
                      createLoading || !newName.trim() || !directoryPath.trim()
                    }
                    className="bg-brand hover:bg-brand-dark text-white disabled:opacity-50 text-xs"
                  >
                    {createLoading ? "Creating..." : "Create"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={resetFormState}
                    className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                  >
                    Cancel
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm text-gray-400">Connection Name</label>
                <Input
                  placeholder="my-data-files"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="bg-gray-900 border-gray-700 text-white"
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm text-gray-400">Directory Path</label>
                <div className="relative">
                  <Input
                    placeholder="/path/to/your/data"
                    value={directoryPath}
                    onChange={(e) => handleDirectoryPathChange(e.target.value)}
                    className="bg-gray-900 border-gray-700 text-white font-mono text-sm pr-10"
                  />
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    <StatusIndicator testStatus={testStatus} />
                  </div>
                </div>
                <p className="text-xs text-gray-500">
                  Point to a directory containing CSV, Parquet, or JSON files.
                  Each file becomes a queryable table.
                  {testStatus &&
                    !testStatus.testing &&
                    testStatus.success === true && (
                      <span className="text-green-400 ml-2">
                        {testStatus.message}
                      </span>
                    )}
                  {testStatus &&
                    !testStatus.testing &&
                    testStatus.success === false && (
                      <>
                        <span className="text-red-400 ml-2">
                          {testStatus.message}
                        </span>
                        {testStatus.hint && (
                          <span className="text-yellow-400 ml-1">
                            {testStatus.hint}
                          </span>
                        )}
                      </>
                    )}
                </p>
              </div>

              {createError && (
                <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
                  {createError}
                </div>
              )}
            </div>
          )}

          {!isInitialized ? (
            <p className="text-gray-500 text-sm">
              Connecting to BICP server...
            </p>
          ) : fileConnections.length === 0 &&
            !connectionsLoading &&
            !showCreateFileForm ? (
            <div className="text-center py-8">
              <p className="text-gray-500 text-sm mb-4">
                No file connections configured yet.
              </p>
              <Button
                onClick={() => {
                  resetFormState();
                  setShowCreateFileForm(true);
                }}
                className="bg-brand hover:bg-brand-dark text-white"
              >
                + Add Your First File Connection
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {fileConnections.map(renderConnectionItem)}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Section 3: API Connections */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-white flex items-center gap-2">
                API Connections
                {connectionsLoading && (
                  <Badge
                    variant="secondary"
                    className="bg-gray-800 text-gray-300"
                  >
                    Loading...
                  </Badge>
                )}
              </CardTitle>
              <CardDescription className="text-gray-400">
                Connect to REST APIs. Data is synced as JSONL and queried via
                DuckDB.
              </CardDescription>
            </div>
            {isInitialized && !showCreateApiForm && (
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={fetchConnections}
                  disabled={connectionsLoading}
                  className="text-gray-400 hover:text-white hover:bg-gray-800"
                  title="Refresh"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={connectionsLoading ? "animate-spin" : ""}
                  >
                    <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
                    <path d="M21 3v5h-5" />
                  </svg>
                </Button>
                <Button
                  onClick={() => {
                    resetFormState();
                    setShowCreateApiForm(true);
                  }}
                  className="bg-brand hover:bg-brand-dark text-white"
                >
                  + Add API Connection
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {/* Create API Connection Form */}
          {showCreateApiForm && (
            <div className="p-4 bg-gray-950 border border-gray-800 rounded-lg mb-4 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-white font-medium">New API Connection</h3>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      handleTestConnection(apiBaseUrl, undefined, "api")
                    }
                    disabled={testStatus?.testing || !apiBaseUrl.trim()}
                    className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                  >
                    {testStatus?.testing ? "Testing..." : "Test"}
                  </Button>
                  <Button
                    onClick={() => handleCreateConnection("api")}
                    size="sm"
                    disabled={
                      createLoading || !newName.trim() || !apiBaseUrl.trim()
                    }
                    className="bg-brand hover:bg-brand-dark text-white disabled:opacity-50 text-xs"
                  >
                    {createLoading ? "Creating..." : "Create"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={resetFormState}
                    className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                  >
                    Cancel
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm text-gray-400">Connection Name</label>
                <Input
                  placeholder="my-api"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="bg-gray-900 border-gray-700 text-white"
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm text-gray-400">Base URL</label>
                <div className="relative">
                  <Input
                    placeholder="https://api.example.com/v1"
                    value={apiBaseUrl}
                    onChange={(e) => setApiBaseUrl(e.target.value)}
                    className="bg-gray-900 border-gray-700 text-white font-mono text-sm pr-10"
                  />
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    <StatusIndicator testStatus={testStatus} />
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm text-gray-400">Auth Type</label>
                  <select
                    value={apiAuthType}
                    onChange={(e) => setApiAuthType(e.target.value)}
                    className="w-full bg-gray-900 border border-gray-700 text-white rounded-md px-3 py-2 text-sm"
                  >
                    <option value="bearer">Bearer Token</option>
                    <option value="header">Custom Header</option>
                    <option value="query_param">Query Parameter</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-gray-400">
                    {apiAuthType === "query_param"
                      ? "Query Param Name"
                      : "Env Var Name"}
                  </label>
                  <Input
                    placeholder={
                      apiAuthType === "query_param" ? "api_key" : "API_KEY"
                    }
                    value={apiTokenEnv}
                    onChange={(e) => setApiTokenEnv(e.target.value)}
                    className="bg-gray-900 border-gray-700 text-white font-mono text-sm"
                  />
                </div>
              </div>

              {apiAuthType === "header" && (
                <div className="space-y-2">
                  <label className="text-sm text-gray-400">Header Name</label>
                  <Input
                    placeholder="X-Api-Key"
                    value={apiHeaderName}
                    onChange={(e) => setApiHeaderName(e.target.value)}
                    className="bg-gray-900 border-gray-700 text-white font-mono text-sm"
                  />
                </div>
              )}

              <div className="space-y-2">
                <label className="text-sm text-gray-400">
                  API Key (stored in .env)
                </label>
                <Input
                  placeholder="sk-..."
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  className="bg-gray-900 border-gray-700 text-white font-mono text-sm"
                />
                <p className="text-xs text-gray-500">
                  Stored securely in .env file, never committed to git.
                </p>
              </div>

              {testStatus &&
                !testStatus.testing &&
                testStatus.success === false && (
                  <p className="text-xs text-red-400">{testStatus.message}</p>
                )}
              {testStatus &&
                !testStatus.testing &&
                testStatus.success === true && (
                  <p className="text-xs text-green-400">{testStatus.message}</p>
                )}

              {createError && (
                <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
                  {createError}
                </div>
              )}
            </div>
          )}

          {!isInitialized ? (
            <p className="text-gray-500 text-sm">
              Connecting to BICP server...
            </p>
          ) : apiConnections.length === 0 &&
            !connectionsLoading &&
            !showCreateApiForm ? (
            <div className="text-center py-8">
              <p className="text-gray-500 text-sm mb-4">
                No API connections configured yet.
              </p>
              <Button
                onClick={() => {
                  resetFormState();
                  setShowCreateApiForm(true);
                }}
                className="bg-brand hover:bg-brand-dark text-white"
              >
                + Add Your First API Connection
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {apiConnections.map((conn) => (
                <div key={conn.name}>
                  {renderConnectionItem(conn)}
                  {/* Discover & Sync buttons for API connections */}
                  {editingConnection !== conn.name && (
                    <div className="flex flex-col gap-1.5 mt-2">
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDiscoverEndpoints(conn.name)}
                          disabled={discoverLoading === conn.name}
                          className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                        >
                          {discoverLoading === conn.name
                            ? "Discovering..."
                            : "Discover Endpoints"}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleSyncConnection(conn.name)}
                          disabled={syncLoading === conn.name}
                          className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                        >
                          {syncLoading === conn.name
                            ? "Syncing..."
                            : "Sync Data"}
                        </Button>
                      </div>
                      {discoverResult && discoverLoading === null && (
                        <span
                          className={`text-xs ${discoverResult.success ? "text-green-400" : "text-yellow-400"}`}
                        >
                          {discoverResult.message}
                        </span>
                      )}
                      {syncResult && syncLoading === null && (
                        <span
                          className={`text-xs ${syncResult.success ? "text-green-400" : "text-red-400"}`}
                        >
                          {syncResult.message}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Section 4: Agent Configuration */}
      <AgentConfig />
    </div>
  );
}
