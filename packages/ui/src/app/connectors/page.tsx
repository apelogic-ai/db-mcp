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

interface Connection {
  name: string;
  isActive: boolean;
  hasSchema: boolean;
  hasDomain: boolean;
  hasCredentials: boolean;
  dialect: string | null;
  onboardingPhase: string | null;
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
}

interface DeleteResult {
  success: boolean;
  error?: string;
}

interface GetResult {
  success: boolean;
  name?: string;
  databaseUrl?: string;
  error?: string;
}

interface UpdateResult {
  success: boolean;
  error?: string;
}

export default function ConnectorsPage() {
  const { isInitialized, isLoading, error, serverInfo, initialize, call } =
    useBICP();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionsLoading, setConnectionsLoading] = useState(false);
  const [connectionsError, setConnectionsError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  // Create/Edit form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingConnection, setEditingConnection] = useState<string | null>(
    null,
  );
  const [fullDatabaseUrl, setFullDatabaseUrl] = useState(""); // Full URL for testing/saving
  const [displayDatabaseUrl, setDisplayDatabaseUrl] = useState(""); // Masked URL for display
  const [urlModified, setUrlModified] = useState(false); // Track if user modified the URL
  const [newName, setNewName] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<{
    testing: boolean;
    success: boolean | null;
    message: string;
  } | null>(null);

  // Auto-test debounce
  const testTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Helper to mask database URL (show only host and db name)
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

  // Fetch connections once when initialized
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
    async (url?: string) => {
      const urlToTest = url ?? fullDatabaseUrl;
      if (!urlToTest.trim()) {
        return;
      }

      setTestStatus({ testing: true, success: null, message: "" });
      try {
        const result = await call<TestResult>("connections/test", {
          databaseUrl: urlToTest,
        });
        setTestStatus({
          testing: false,
          success: result.success,
          message: result.success
            ? result.dialect || "Connected"
            : result.error || "Connection failed",
        });
      } catch (err) {
        setTestStatus({
          testing: false,
          success: false,
          message: err instanceof Error ? err.message : "Test failed",
        });
      }
    },
    [call, fullDatabaseUrl],
  );

  // Auto-test when URL changes (debounced)
  const handleDatabaseUrlChange = (value: string) => {
    setDisplayDatabaseUrl(value);
    setFullDatabaseUrl(value); // User entered a new URL, use it as full URL
    setUrlModified(true);
    setTestStatus(null);

    // Clear previous timeout
    if (testTimeoutRef.current) {
      clearTimeout(testTimeoutRef.current);
    }

    // Auto-test after 800ms of no typing (only if URL looks complete)
    if (value.includes("://") && value.length > 15 && !value.includes("****")) {
      testTimeoutRef.current = setTimeout(() => {
        handleTestConnection(value);
      }, 800);
    }
  };

  const handleCreateConnection = async () => {
    if (!newName.trim() || !fullDatabaseUrl.trim()) {
      setCreateError("Name and Database URL are required");
      return;
    }

    setCreateLoading(true);
    setCreateError(null);
    try {
      const result = await call<CreateResult>("connections/create", {
        name: newName.trim(),
        databaseUrl: fullDatabaseUrl.trim(),
        setActive: true,
      });

      if (result.success) {
        // Reset form and refresh list
        setShowCreateForm(false);
        setNewName("");
        setFullDatabaseUrl("");
        setDisplayDatabaseUrl("");
        setUrlModified(false);
        setTestStatus(null);
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
    if (!confirm(`Delete connection "${name}"? This cannot be undone.`)) {
      return;
    }

    try {
      const result = await call<DeleteResult>("connections/delete", { name });
      if (result.success) {
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
        const url = result.databaseUrl || "";
        const maskedUrl = maskDatabaseUrl(url);
        setEditingConnection(name);
        setNewName(name);
        setFullDatabaseUrl(url); // Store full URL for testing
        setDisplayDatabaseUrl(maskedUrl); // Show masked URL
        setUrlModified(false);
        setShowCreateForm(true);
        setTestStatus(null);
        setCreateError(null);
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
    if (!editingConnection || !fullDatabaseUrl.trim()) {
      setCreateError("Database URL is required");
      return;
    }

    setCreateLoading(true);
    setCreateError(null);
    try {
      const result = await call<UpdateResult>("connections/update", {
        name: editingConnection,
        databaseUrl: fullDatabaseUrl.trim(),
      });

      if (result.success) {
        // Reset form and refresh list
        setShowCreateForm(false);
        setEditingConnection(null);
        setFullDatabaseUrl("");
        setDisplayDatabaseUrl("");
        setUrlModified(false);
        setNewName("");
        setTestStatus(null);
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

  const getDialectBadge = (dialect: string | null) => {
    if (!dialect) return null;
    const colors: Record<string, string> = {
      postgresql: "bg-blue-900 text-blue-300",
      clickhouse: "bg-yellow-900 text-yellow-300",
      trino: "bg-purple-900 text-purple-300",
      mysql: "bg-orange-900 text-orange-300",
      mssql: "bg-red-900 text-red-300",
      sqlite: "bg-gray-700 text-gray-300",
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
      complete: { label: "Complete", color: "bg-green-900 text-green-300" },
    };
    const info = phaseLabels[phase] || {
      label: phase,
      color: "bg-gray-700 text-gray-300",
    };
    return <Badge className={info.color}>{info.label}</Badge>;
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Data Connectors</h1>
        <p className="text-gray-400 mt-1">
          Manage database and API connections
        </p>
      </div>

      {/* Connection error banner */}
      {error && (
        <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
          Connection error: {error.message}
        </div>
      )}

      {/* Connections List */}
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
                Configure and manage your database connections.
              </CardDescription>
            </div>
            {isInitialized && !showCreateForm && (
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
                  onClick={() => setShowCreateForm(true)}
                  className="bg-green-600 hover:bg-green-700 text-white"
                >
                  + Add Connection
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {connectionsError && (
            <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm mb-4">
              {connectionsError}
            </div>
          )}

          {/* Create/Edit Connection Form */}
          {showCreateForm && (
            <div className="p-4 bg-gray-950 border border-gray-800 rounded-lg mb-4 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-white font-medium">
                  {editingConnection
                    ? `Edit Connection: ${editingConnection}`
                    : "New Connection"}
                </h3>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleTestConnection()}
                    disabled={testStatus?.testing || !fullDatabaseUrl.trim()}
                    className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                  >
                    {testStatus?.testing ? "Testing..." : "Test"}
                  </Button>
                  {editingConnection ? (
                    <Button
                      onClick={handleUpdateConnection}
                      size="sm"
                      disabled={createLoading || !urlModified}
                      className="bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 text-xs"
                    >
                      {createLoading ? "Updating..." : "Update"}
                    </Button>
                  ) : (
                    <Button
                      onClick={handleCreateConnection}
                      size="sm"
                      disabled={
                        createLoading ||
                        !newName.trim() ||
                        !fullDatabaseUrl.trim()
                      }
                      className="bg-green-600 hover:bg-green-700 text-white disabled:opacity-50 text-xs"
                    >
                      {createLoading ? "Creating..." : "Create"}
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setShowCreateForm(false);
                      setEditingConnection(null);
                      setFullDatabaseUrl("");
                      setDisplayDatabaseUrl("");
                      setUrlModified(false);
                      setNewName("");
                      setTestStatus(null);
                      setCreateError(null);
                    }}
                    className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                  >
                    Cancel
                  </Button>
                </div>
              </div>

              {!editingConnection && (
                <div className="space-y-2">
                  <label className="text-sm text-gray-400">
                    Connection Name
                  </label>
                  <Input
                    placeholder="my-database"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    className="bg-gray-900 border-gray-700 text-white"
                  />
                </div>
              )}

              <div className="space-y-2">
                <label className="text-sm text-gray-400">Database URL</label>
                <div className="relative">
                  <Input
                    placeholder="postgresql://user:pass@host:5432/database"
                    value={displayDatabaseUrl}
                    onChange={(e) => handleDatabaseUrlChange(e.target.value)}
                    className="bg-gray-900 border-gray-700 text-white font-mono text-sm pr-10"
                  />
                  {/* Inline status indicator */}
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    {testStatus?.testing && (
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
                    )}
                    {testStatus &&
                      !testStatus.testing &&
                      testStatus.success === true && (
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
                      )}
                    {testStatus &&
                      !testStatus.testing &&
                      testStatus.success === false && (
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
                      )}
                  </div>
                </div>
                <p className="text-xs text-gray-500">
                  Supports: PostgreSQL, ClickHouse, Trino, MySQL, SQL Server
                  {testStatus &&
                    !testStatus.testing &&
                    testStatus.success === false && (
                      <span className="text-red-400 ml-2">
                        {testStatus.message}
                      </span>
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
          ) : connections.length === 0 &&
            !connectionsLoading &&
            !showCreateForm ? (
            <div className="text-center py-8">
              <p className="text-gray-500 text-sm mb-4">
                No connections configured yet.
              </p>
              <Button
                onClick={() => setShowCreateForm(true)}
                className="bg-green-600 hover:bg-green-700 text-white"
              >
                + Add Your First Connection
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {connections.map((conn) => (
                <div
                  key={conn.name}
                  className={`p-4 rounded-lg border ${
                    conn.isActive
                      ? "bg-green-950/30 border-green-800"
                      : "bg-gray-950 border-gray-800 hover:border-gray-700"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-2 h-2 rounded-full ${conn.isActive ? "bg-green-500" : "bg-gray-600"}`}
                      />
                      <span className="text-white font-medium">
                        {conn.name}
                      </span>
                      {conn.isActive && (
                        <Badge className="bg-green-900 text-green-300 text-xs">
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
                        onClick={() => handleEditConnection(conn.name)}
                        className="text-xs border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300"
                      >
                        Edit
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
                        conn.hasCredentials ? "text-green-500" : "text-gray-600"
                      }
                    >
                      {conn.hasCredentials ? "Credentials" : "No credentials"}
                    </span>
                    <span
                      className={
                        conn.hasSchema ? "text-green-500" : "text-gray-600"
                      }
                    >
                      {conn.hasSchema ? "Schema" : "No schema"}
                    </span>
                    <span
                      className={
                        conn.hasDomain ? "text-green-500" : "text-gray-600"
                      }
                    >
                      {conn.hasDomain ? "Domain" : "No domain"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
