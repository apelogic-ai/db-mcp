"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBICP } from "@/lib/bicp-context";
import { useConnections } from "@/lib/connection-context";
import type {
  ConnectionRecord,
  ConnectionsListResult,
  DeleteResult,
} from "./types";
import { summarizeConnectionState } from "./utils";

const SECTION_ORDER: Array<{
  key: ConnectionRecord["connectorType"];
  title: string;
  description: string;
}> = [
  {
    key: "sql",
    title: "DB connections",
    description: "PostgreSQL, ClickHouse, Trino, MySQL, SQL Server, and SQLite.",
  },
  {
    key: "api",
    title: "API connections",
    description: "REST APIs that can be discovered and synced into db-mcp.",
  },
  {
    key: "file",
    title: "File connections",
    description: "CSV, JSON, and Parquet folders surfaced through DuckDB.",
  },
];

export function ConnectionsPageClient() {
  const { isInitialized, call } = useBICP();
  const { refreshConnections } = useConnections();
  const [connections, setConnections] = useState<ConnectionRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingName, setDeletingName] = useState<string | null>(null);

  const loadConnections = useCallback(async () => {
    if (!isInitialized) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await call<ConnectionsListResult>("connections/list", {});
      setConnections(result.connections);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load connections");
    } finally {
      setLoading(false);
    }
  }, [call, isInitialized]);

  useEffect(() => {
    loadConnections();
  }, [loadConnections]);

  const groupedConnections = useMemo(() => {
    return SECTION_ORDER.map((section) => ({
      ...section,
      items: connections.filter((connection) => {
        if (section.key === "sql") {
          return !connection.connectorType || connection.connectorType === "sql";
        }
        return connection.connectorType === section.key;
      }),
    }));
  }, [connections]);

  const handleDelete = useCallback(
    async (name: string) => {
      if (!confirm(`Delete connection "${name}"? This cannot be undone.`)) {
        return;
      }

      setDeletingName(name);
      setError(null);

      try {
        const result = await call<DeleteResult>("connections/delete", { name });
        if (!result.success) {
          setError(result.error || "Failed to delete connection");
          return;
        }
        await loadConnections();
        await refreshConnections();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete connection");
      } finally {
        setDeletingName(null);
      }
    },
    [call, loadConnections, refreshConnections],
  );

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-white">Connections</h1>
        <p className="text-sm text-gray-400">
          Choose a connection, inspect its setup state, or start a new onboarding
          wizard.
        </p>
      </div>

      {error && (
        <Card className="border-red-900/60 bg-red-950/30">
          <CardContent className="pt-6 text-sm text-red-200">{error}</CardContent>
        </Card>
      )}

      {groupedConnections.map((section) => (
        <Card key={section.key} className="border-gray-800 bg-gray-900">
          <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
            <div className="space-y-1">
              <CardTitle className="text-white">{section.title}</CardTitle>
              <p className="text-sm text-gray-400">{section.description}</p>
            </div>
            <Button
              asChild
              size="sm"
              className="bg-brand hover:bg-brand/90 text-white"
            >
              <Link href={`/connection/new?type=${section.key}#connect`}>+ New</Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading && section.items.length === 0 ? (
              <p className="text-sm text-gray-500">Loading connections...</p>
            ) : section.items.length === 0 ? (
              <div className="rounded-xl border border-dashed border-gray-800 bg-gray-950/60 px-4 py-6 text-sm text-gray-500">
                No {section.title.toLowerCase()} yet.
              </div>
            ) : (
              section.items.map((connection) => (
                <div
                  key={connection.name}
                  className="rounded-xl border border-gray-800 bg-gray-950/80 px-4 py-4"
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-center gap-3">
                        <span
                          className={`h-2.5 w-2.5 rounded-full ${
                            connection.isActive ? "bg-emerald-400" : "bg-amber-400"
                          }`}
                        />
                        <Link
                          href={`/connection/${encodeURIComponent(connection.name)}`}
                          className="text-lg font-semibold text-white hover:text-brand"
                        >
                          {connection.name}
                        </Link>
                        {connection.dialect && (
                          <Badge className="border border-gray-700 bg-gray-900 text-gray-200">
                            {connection.dialect}
                          </Badge>
                        )}
                        {connection.isActive && (
                          <Badge className="bg-brand/15 text-brand border border-brand/30">
                            Active
                          </Badge>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-4 text-sm text-gray-400">
                        <span>{summarizeConnectionState(connection.hasSchema, connection.hasDomain)}</span>
                        <span>
                          Schema {connection.hasSchema ? "configured" : "missing"}
                        </span>
                        <span>
                          Domain {connection.hasDomain ? "configured" : "missing"}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button asChild variant="outline" size="sm">
                        <Link href={`/connection/${encodeURIComponent(connection.name)}`}>
                          Edit
                        </Link>
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDelete(connection.name)}
                        disabled={deletingName === connection.name}
                        className="border-red-900/70 text-red-300 hover:bg-red-950/60"
                      >
                        {deletingName === connection.name ? "Deleting..." : "Delete"}
                      </Button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
