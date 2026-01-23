"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

export default function ConnectorsPage() {
  const { isInitialized, isLoading, error, serverInfo, initialize, call } =
    useBICP();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionsLoading, setConnectionsLoading] = useState(false);
  const [connectionsError, setConnectionsError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

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
          <CardTitle className="text-white flex items-center gap-2">
            Database Connections
            {connectionsLoading && (
              <Badge variant="secondary" className="bg-gray-800 text-gray-300">
                Loading...
              </Badge>
            )}
          </CardTitle>
          <CardDescription className="text-gray-400">
            Configure and manage your database connections. Connect to
            PostgreSQL, ClickHouse, Trino, MySQL, SQL Server, and more.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {connectionsError && (
            <div className="p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm mb-4">
              {connectionsError}
            </div>
          )}

          {!isInitialized ? (
            <p className="text-gray-500 text-sm">
              Connecting to BICP server...
            </p>
          ) : connections.length === 0 && !connectionsLoading ? (
            <div>
              <p className="text-gray-500 text-sm">
                No connections configured yet. Use the CLI to add a connection:
              </p>
              <code className="block mt-2 p-3 bg-gray-950 rounded text-gray-300 text-sm font-mono">
                db-mcp init my-database
              </code>
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
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
