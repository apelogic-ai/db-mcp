"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConnectionKnowledgeWorkspace } from "@/features/context/ConnectionKnowledgeWorkspace";
import InsightsPageClient from "@/features/insights/InsightsPageClient";
import { useBICP } from "@/lib/bicp-context";
import { useConnections } from "@/lib/connection-context";
import { type InsightsAnalyzeResult } from "@/lib/bicp";
import { buildDashboardSummary } from "@/lib/services/dashboard";
import { ConnectionStatusSteps, type ConnectionStepStatus } from "./ConnectionStatusSteps";
import type { ConnectionGetResult, CreateResult, DeleteResult } from "./types";
import { ConnectionWorkspaceShell } from "./ConnectionWorkspaceShell";
import {
  buildConnectionRoute,
  buildConnectionAppHref,
  buildWizardHref,
  getConnectionOnboardingTone,
  getPersistedWizardStatuses,
  getWizardResumeStep,
  inferDialect,
  maskDatabaseUrl,
} from "./utils";

type DetailView = "overview" | "insights" | "knowledge";

function buildDuplicateConnectionName(name: string, existingNames: string[]): string {
  const baseCandidate = `${name}-copy`;
  if (!existingNames.includes(baseCandidate)) {
    return baseCandidate;
  }

  let suffix = 2;
  while (existingNames.includes(`${baseCandidate}-${suffix}`)) {
    suffix += 1;
  }
  return `${baseCandidate}-${suffix}`;
}

export function ConnectionDetailPageClient({
  name,
  view,
}: {
  name: string;
  view: DetailView;
}) {
  const { isInitialized, call } = useBICP();
  const router = useRouter();
  const { connections, refreshConnections, switchConnection } = useConnections();

  const [connectorType, setConnectorType] = useState<"sql" | "file" | "api">("sql");
  const [databaseUrl, setDatabaseUrl] = useState("");
  const [displayDatabaseUrl, setDisplayDatabaseUrl] = useState("");
  const [directory, setDirectory] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<ReturnType<typeof buildDashboardSummary> | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState<"duplicate" | "delete" | null>(null);

  const loadPageData = useCallback(async () => {
    if (!isInitialized) {
      return;
    }

    setError(null);

    try {
      await switchConnection(name);
      const connectionResult = await call<ConnectionGetResult>("connections/get", { name });

      if (!connectionResult.success) {
        setError(connectionResult.error || "Failed to load connection");
        return;
      }

      const type = connectionResult.connectorType || "sql";
      setConnectorType(type);
      setDatabaseUrl(connectionResult.databaseUrl || "");
      setDisplayDatabaseUrl(maskDatabaseUrl(connectionResult.databaseUrl || ""));
      setDirectory(connectionResult.directory || "");
      setBaseUrl(connectionResult.baseUrl || "");

      if (view === "overview") {
        const insightsResult = await call<InsightsAnalyzeResult>("insights/analyze", { days: 7 });
        if (insightsResult.success) {
          const connectionSummary =
            connections.find((connection) => connection.name === name) ?? null;
          setSummary(buildDashboardSummary(insightsResult.analysis, name, connectionSummary));
        } else {
          setSummary(null);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load connection");
    }
  }, [call, connections, isInitialized, name, switchConnection, view]);

  useEffect(() => {
    loadPageData();
  }, [loadPageData]);

  useEffect(() => {
    const nextUrl = buildConnectionRoute(name, view).href;
    const currentUrl = `${window.location.pathname}${window.location.search}`;
    if (currentUrl !== nextUrl) {
      window.history.replaceState(window.history.state, "", nextUrl);
    }
  }, [name, view]);

  const sectionLinks: Array<{ id: DetailView; label: string; href: string }> = [
    {
      id: "overview",
      label: "Overview",
      href: buildConnectionRoute(name).appHref,
    },
    {
      id: "insights",
      label: "Insights",
      href: buildConnectionRoute(name, "insights").appHref,
    },
    {
      id: "knowledge",
      label: "Knowledge",
      href: buildConnectionRoute(name, "knowledge").appHref,
    },
  ];

  const currentConnection = useMemo(
    () => connections.find((connection) => connection.name === name) ?? null,
    [connections, name],
  );

  const configureLabel =
    currentConnection && getConnectionOnboardingTone(currentConnection) === "complete"
      ? "Re-configure"
      : "Configure";
  const configureStep = currentConnection ? getWizardResumeStep(currentConnection) : "connect";

  const persistedStatuses: Record<"connect" | "discover" | "sample", ConnectionStepStatus> = currentConnection
    ? getPersistedWizardStatuses(currentConnection)
    : { connect: "active", discover: "idle", sample: "idle" };
  const semanticPercent = summary
    ? Math.round((summary.semantic.score / summary.semantic.maxScore) * 100)
    : 0;
  const semanticCircleOffset = summary
    ? 100 - (100 * summary.semantic.score) / summary.semantic.maxScore
    : 100;
  const currentAppHref = buildConnectionAppHref(name, view);

  const navigateToSection = useCallback((targetHref: string) => {
    const currentVisibleUrl =
      typeof window === "undefined"
        ? currentAppHref
        : `${window.location.pathname}${window.location.search}`;

    if (currentVisibleUrl !== currentAppHref) {
      window.history.replaceState(window.history.state, "", currentAppHref);
    }
    router.push(targetHref, { scroll: false });
  }, [currentAppHref, router]);

  const setupRows = useMemo(() => {
    return [
      {
        label: "Name",
        value: name,
      },
      {
        label: connectorType === "sql" ? "DB URL" : connectorType === "file" ? "Directory" : "Base URL",
        value:
          connectorType === "sql"
            ? displayDatabaseUrl || "Not set"
            : connectorType === "file"
              ? directory || "Not set"
              : baseUrl || "Not set",
      },
      {
        label: "Dialect",
        value: inferDialect(connectorType, { databaseUrl, directory, baseUrl }),
      },
    ];
  }, [baseUrl, connectorType, databaseUrl, directory, displayDatabaseUrl, name]);

  const handleDuplicate = useCallback(async () => {
    setMenuOpen(false);
    setActionLoading("duplicate");
    setError(null);

    try {
      const connectionResult = await call<ConnectionGetResult>("connections/get", { name });
      if (!connectionResult.success) {
        setError(connectionResult.error || "Failed to load connection for duplication");
        return;
      }

      const duplicateName = buildDuplicateConnectionName(
        name,
        connections.map((connection) => connection.name),
      );

      const createParams: Record<string, unknown> = {
        name: duplicateName,
        connectorType: connectionResult.connectorType || "sql",
        setActive: false,
      };

      if (connectionResult.connectorType === "file") {
        createParams.directory = connectionResult.directory || "";
      } else if (connectionResult.connectorType === "api") {
        createParams.baseUrl = connectionResult.baseUrl || "";
        createParams.authType = connectionResult.auth?.type || "bearer";
        createParams.tokenEnv = connectionResult.auth?.tokenEnv || undefined;
        createParams.headerName =
          connectionResult.auth?.type === "header"
            ? connectionResult.auth?.headerName || undefined
            : undefined;
      } else {
        createParams.databaseUrl = connectionResult.databaseUrl || "";
      }

      const createResult = await call<CreateResult>("connections/create", createParams);
      if (!createResult.success || !createResult.name) {
        setError(createResult.error || "Failed to duplicate connection");
        return;
      }

      await refreshConnections();
      await switchConnection(createResult.name);
      router.push(buildConnectionAppHref(createResult.name, view), { scroll: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to duplicate connection");
    } finally {
      setActionLoading(null);
    }
  }, [call, connections, name, refreshConnections, router, switchConnection, view]);

  const handleDelete = useCallback(async () => {
    setActionLoading("delete");
    setError(null);

    try {
      const result = await call<DeleteResult>("connections/delete", { name });
      if (!result.success) {
        setError(result.error || "Failed to delete connection");
        return;
      }

      setDeleteDialogOpen(false);
      const remainingConnections = connections.filter((connection) => connection.name !== name);
      await refreshConnections();

      if (remainingConnections.length > 0) {
        router.push(buildConnectionAppHref(remainingConnections[0].name), { scroll: false });
      } else {
        router.push("/connection/new#connect", { scroll: false });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete connection");
    } finally {
      setActionLoading(null);
    }
  }, [call, connections, name, refreshConnections, router]);

  return (
    <ConnectionWorkspaceShell selectedName={name} currentView={view}>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div className="inline-flex h-9 items-center justify-center gap-1 text-gray-400">
            {sectionLinks.map((section) => (
              <Link
                key={section.id}
                href={section.href}
                onClick={(event) => {
                  event.preventDefault();
                  navigateToSection(section.href);
                }}
                className={`inline-flex items-center justify-center whitespace-nowrap border-b-2 px-3 py-1 text-sm font-medium transition-all ${
                  view === section.id
                    ? "border-brand text-brand"
                    : "border-transparent text-gray-400 hover:text-gray-200"
                }`}
              >
                {section.label}
              </Link>
            ))}
          </div>

          <div className="relative">
            <button
              type="button"
              aria-label="Connection actions"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-gray-800 text-gray-400 transition-colors hover:border-gray-700 hover:text-white"
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
              >
                <circle cx="12" cy="12" r="1" />
                <circle cx="19" cy="12" r="1" />
                <circle cx="5" cy="12" r="1" />
              </svg>
            </button>

            {menuOpen && (
              <>
                <button
                  type="button"
                  aria-label="Close connection actions"
                  onClick={() => setMenuOpen(false)}
                  className="fixed inset-0 z-10 cursor-default"
                />
                <div className="absolute right-0 top-11 z-20 min-w-48 rounded-xl border border-gray-800 bg-gray-950 p-1.5 shadow-2xl">
                  <Link
                    href={buildWizardHref(configureStep, { name })}
                    onClick={() => setMenuOpen(false)}
                    className="flex w-full items-center rounded-lg px-3 py-2 text-left text-sm text-gray-200 transition-colors hover:bg-gray-900"
                  >
                    {configureLabel}
                  </Link>
                  <button
                    type="button"
                    onClick={handleDuplicate}
                    disabled={actionLoading !== null}
                    className="flex w-full items-center rounded-lg px-3 py-2 text-left text-sm text-gray-200 transition-colors hover:bg-gray-900 disabled:opacity-50"
                  >
                    {actionLoading === "duplicate" ? "Duplicating..." : "Duplicate"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      setDeleteDialogOpen(true);
                    }}
                    className="flex w-full items-center rounded-lg px-3 py-2 text-left text-sm text-red-300 transition-colors hover:bg-red-950/40"
                  >
                    Delete
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        {error && <p className="text-sm text-red-300">{error}</p>}

        {view === "overview" && (
          <div className="space-y-4">
            <div className="grid gap-6 rounded-lg border border-gray-800 bg-gray-950/80 p-4 md:grid-cols-2">
              <div className="space-y-2">
                <p className="text-[11px] uppercase tracking-[0.24em] text-gray-500">Name</p>
                <p className="text-sm text-gray-200">{name}</p>
              </div>
              <div className="space-y-2">
                <p className="text-[11px] uppercase tracking-[0.24em] text-gray-500">
                  {connectorType === "sql" ? "DB URL" : connectorType === "file" ? "Directory" : "Base URL"}
                </p>
                <p className="break-all font-mono text-sm text-white">
                  {connectorType === "sql"
                    ? displayDatabaseUrl || "Not set"
                    : connectorType === "file"
                      ? directory || "Not set"
                      : baseUrl || "Not set"}
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-[11px] uppercase tracking-[0.24em] text-gray-500">Status</p>
                <ConnectionStatusSteps statuses={persistedStatuses} />
              </div>
              <div className="space-y-2">
                <p className="text-[11px] uppercase tracking-[0.24em] text-gray-500">Dialect</p>
                <p className="text-sm text-gray-200">
                  {inferDialect(connectorType, { databaseUrl, directory, baseUrl })}
                </p>
              </div>
            </div>

            {summary ? (
              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <Card className="border-gray-800 bg-gray-950/80">
                    <CardHeader className="pb-1">
                      <CardTitle className="text-sm text-gray-300">Semantic Layer</CardTitle>
                    </CardHeader>
                    <CardContent className="flex items-center gap-4">
                      <div className="relative h-20 w-20 shrink-0">
                        <svg viewBox="0 0 36 36" className="h-20 w-20 -rotate-90">
                          <path
                            d="M18 2.5a15.5 15.5 0 1 1 0 31a15.5 15.5 0 1 1 0-31"
                            fill="none"
                            stroke="rgba(75, 85, 99, 0.4)"
                            strokeWidth="3"
                            strokeLinecap="round"
                            pathLength="100"
                          />
                          <path
                            d="M18 2.5a15.5 15.5 0 1 1 0 31a15.5 15.5 0 1 1 0-31"
                            fill="none"
                            stroke="rgb(251 146 60)"
                            strokeWidth="3"
                            strokeLinecap="round"
                            pathLength="100"
                            strokeDasharray="100"
                            strokeDashoffset={semanticCircleOffset}
                          />
                        </svg>
                        <div className="absolute inset-0 flex items-center justify-center text-lg font-semibold text-white">
                          {semanticPercent}%
                        </div>
                      </div>
                      <div className="space-y-1">
                        <p className="text-2xl font-semibold text-white">
                          {summary.semantic.score}/{summary.semantic.maxScore}
                        </p>
                        <p className="text-xs text-gray-400">Semantic layer completeness</p>
                      </div>
                    </CardContent>
                  </Card>
                  <Card className="border-gray-800 bg-gray-950/80">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm text-gray-300">Open Actions</CardTitle>
                    </CardHeader>
                    <CardContent className="text-4xl font-semibold text-white">
                      {summary.queue.length}
                    </CardContent>
                  </Card>
                  <Card className="border-gray-800 bg-gray-950/80">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm text-gray-300">Recent Traces</CardTitle>
                    </CardHeader>
                    <CardContent className="text-4xl font-semibold text-white">
                      {summary.recent.traces}
                    </CardContent>
                  </Card>
                </div>

                <Card className="border-gray-800 bg-gray-950/80">
                  <CardHeader>
                    <CardTitle className="text-white">Recommended Actions</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {summary.queue.map((item) => (
                      <div
                        key={item.id}
                        className="flex items-start justify-between gap-4 rounded-lg border border-gray-800 p-3"
                      >
                        <div className="space-y-1">
                          <p className="text-sm font-medium text-white">{item.title}</p>
                          <p className="text-xs text-gray-400">{item.detail}</p>
                        </div>
                        <Button asChild variant="outline" size="sm">
                          <Link href={item.ctaUrl}>{item.ctaLabel}</Link>
                        </Button>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>
            ) : (
              <Card className="border-gray-800 bg-gray-950/80">
                <CardContent className="pt-6 text-sm text-gray-400">
                  Dashboard data is unavailable for this connection yet.
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {view === "insights" && (
          <InsightsPageClient connectionName={name} showHeader={false} />
        )}

        {view === "knowledge" && (
          <ConnectionKnowledgeWorkspace connectionName={name} />
        )}
      </div>

      {deleteDialogOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-md rounded-2xl border border-red-900/60 bg-gray-950 p-6 shadow-2xl">
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-white">Delete connection?</h2>
              <p className="text-sm text-gray-400">
                This will remove <span className="font-medium text-white">{name}</span> from db-mcp.
                This action cannot be undone.
              </p>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={() => setDeleteDialogOpen(false)}
                disabled={actionLoading === "delete"}
              >
                Cancel
              </Button>
              <Button
                onClick={handleDelete}
                disabled={actionLoading === "delete"}
                className="bg-red-600 text-white hover:bg-red-700"
              >
                {actionLoading === "delete" ? "Deleting..." : "Delete connection"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </ConnectionWorkspaceShell>
  );
}
