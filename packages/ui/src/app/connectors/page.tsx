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

export default function ConnectorsPage() {
  const { isInitialized, isLoading, error, serverInfo, initialize, call } =
    useBICP();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionsLoading, setConnectionsLoading] = useState(false);
  const [connectionsError, setConnectionsError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  // Create form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDatabaseUrl, setNewDatabaseUrl] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<{
    tested: boolean;
    success: boolean;
    message: string;
  } | null>(null);

  // Delete state
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  // Auto-test debounce
  const testTimeoutRef = useRef<NodeJS.Timeout | null>(null);

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
      const urlToTest = url ?? newDatabaseUrl;
      if (!urlToTest.trim()) {
        return;
      }

      setTestStatus({ tested: false, success: false, message: "Testing..." });
      setCreateLoading(true);
      try {
        const result = await call<TestResult>("connections/test", {
          databaseUrl: urlToTest,
        });
        setTestStatus({
          tested: true,
          success: result.success,
          message: result.success
            ? `Connected successfully (${result.dialect || "unknown dialect"})`
            : result.error || "Connection failed",
        });
      } catch (err) {
        setTestStatus({
          tested: true,
          success: false,
          message: err instanceof Error ? err.message : "Test failed",
        });
      } finally {
        setCreateLoading(false);
      }
    },
    [call, newDatabaseUrl],
  );

  // Auto-test when URL changes (debounced)
  const handleDatabaseUrlChange = (value: string) => {
    setNewDatabaseUrl(value);
    setTestStatus(null);

    // Clear previous timeout
    if (testTimeoutRef.current) {
      clearTimeout(testTimeoutRef.current);
    }

    // Auto-test after 800ms of no typing (only if URL looks complete)
    if (value.includes("://") && value.length > 15) {
      testTimeoutRef.current = setTimeout(() => {
        handleTestConnection(value);
      }, 800);
    }
  };

  const handleCreateConnection = async () => {
    if (!newName.trim() || !newDatabaseUrl.trim()) {
      setCreateError("Name and Database URL are required");
      return;
    }

    setCreateLoading(true);
    setCreateError(null);
    try {
      const result = await call<CreateResult>("connections/create", {
        name: newName.trim(),
        databaseUrl: newDatabaseUrl.trim(),
        setActive: true,
      });

      if (result.success) {
        // Reset form and refresh list
        setShowCreateForm(false);
        setNewName("");
        setNewDatabaseUrl("");
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
    try {
      const result = await call<DeleteResult>("connections/delete", { name });
      if (result.success) {
        setDeleteConfirm(null);
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

      {/* BICP Connection Status */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            BICP Connection
            {isInitialized ? (
              <Badge className="bg-green-900 text-green-300">Connected</Badge>
            ) : (
              <Badge variant="secondary" className="bg-gray-800 text-gray-300">
                {isLoading ? "Connecting..." : "Not Connected"}
              </Badge>
            )}
          </CardTitle>
          <CardDescription className="text-gray-400">
            Connect to the db-mcp sidecar via BICP protocol
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
              Error: {error.message}
            </div>
          )}

          {serverInfo && (
            <div className="p-3 bg-gray-950 rounded text-sm space-y-1">
              <p className="text-gray-300">
                <span className="text-gray-500">Server:</span> {serverInfo.name}{" "}
                v{serverInfo.version}
              </p>
              <p className="text-gray-300">
                <span className="text-gray-500">Protocol:</span>{" "}
                {serverInfo.protocolVersion}
              </p>
            </div>
          )}

          <Button
            onClick={initialize}
            disabled={isLoading}
            className="bg-blue-600 hover:bg-blue-700 text-white"
          >
            {isLoading
              ? "Connecting..."
              : isInitialized
                ? "Reconnect"
                : "Connect to Sidecar"}
          </Button>
        </CardContent>
      </Card>

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
              <Button
                onClick={() => setShowCreateForm(true)}
                className="bg-green-600 hover:bg-green-700 text-white"
              >
                + Add Connection
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {connectionsError && (
            <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm mb-4">
              {connectionsError}
            </div>
          )}

          {/* Create Connection Form */}
          {showCreateForm && (
            <div className="p-4 bg-gray-950 border border-gray-800 rounded-lg mb-4 space-y-4">
              <h3 className="text-white font-medium">New Connection</h3>

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
                <Input
                  placeholder="postgresql://user:pass@host:5432/database"
                  value={newDatabaseUrl}
                  onChange={(e) => handleDatabaseUrlChange(e.target.value)}
                  className="bg-gray-900 border-gray-700 text-white font-mono text-sm"
                />
                <p className="text-xs text-gray-500">
                  Supports: PostgreSQL, ClickHouse, Trino, MySQL, SQL Server
                </p>
              </div>

              {testStatus && (
                <div
                  className={`p-3 rounded text-sm ${
                    testStatus.success
                      ? "bg-green-950 border border-green-800 text-green-300"
                      : "bg-red-950 border border-red-800 text-red-300"
                  }`}
                >
                  {testStatus.message}
                </div>
              )}

              {createError && (
                <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
                  {createError}
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => handleTestConnection()}
                  disabled={createLoading || !newDatabaseUrl.trim()}
                  className="border-gray-700 hover:bg-gray-800"
                >
                  {createLoading ? "Testing..." : "Test Connection"}
                </Button>
                <Button
                  onClick={handleCreateConnection}
                  disabled={
                    createLoading || !newName.trim() || !newDatabaseUrl.trim()
                  }
                  className="bg-green-600 hover:bg-green-700 text-white"
                >
                  {createLoading ? "Creating..." : "Create"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowCreateForm(false);
                    setNewName("");
                    setNewDatabaseUrl("");
                    setTestStatus(null);
                    setCreateError(null);
                  }}
                  className="border-gray-700 hover:bg-gray-800"
                >
                  Cancel
                </Button>
              </div>
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
                      ? "bg-gray-800 border-green-700"
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
                          className="text-xs border-gray-700 hover:bg-gray-800"
                        >
                          Switch
                        </Button>
                      )}
                      {deleteConfirm === conn.name ? (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleDeleteConnection(conn.name)}
                            className="text-xs border-red-700 text-red-400 hover:bg-red-950"
                          >
                            Confirm
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setDeleteConfirm(null)}
                            className="text-xs border-gray-700 hover:bg-gray-800"
                          >
                            Cancel
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDeleteConfirm(conn.name)}
                          className="text-xs border-gray-700 hover:bg-gray-800 text-gray-400"
                        >
                          Delete
                        </Button>
                      )}
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
              {connections.length > 0 && !showCreateForm && (
                <div className="pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={fetchConnections}
                    disabled={connectionsLoading}
                    className="text-xs border-gray-700 hover:bg-gray-800"
                  >
                    Refresh
                  </Button>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
