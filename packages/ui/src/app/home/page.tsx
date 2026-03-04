"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { InsightsAnalyzeResult } from "@/lib/bicp";
import { useBICP } from "@/lib/bicp-context";
import { useConnections } from "@/lib/connection-context";
import {
  type DashboardSummaryEndpointResult,
  type DashboardSummary,
  buildDashboardSummary,
  normalizeDashboardSummary,
} from "@/lib/services/dashboard";

function formatDuration(ms: number): string {
  if (!ms || ms <= 0) return "0ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${(seconds / 60).toFixed(1)}m`;
}

export default function HomePage() {
  const { isInitialized, call } = useBICP();
  const { activeConnection, connections, isLoading: connectionsLoading } =
    useConnections();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  const load = useCallback(async () => {
    if (!isInitialized || connectionsLoading) {
      return;
    }

    if (!activeConnection) {
      setSummary(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      try {
        const result = await call<DashboardSummaryEndpointResult>("dashboard/summary", {
          connection: activeConnection,
        });
        setSummary(normalizeDashboardSummary(result, activeConnection));
      } catch {
        // Back-compat fallback while endpoint rollout converges.
        const result = await call<InsightsAnalyzeResult>("insights/analyze", {
          days: 7,
        });

        if (!result.success) {
          setError(result.error || "Failed to load dashboard summary");
          setSummary(null);
        } else {
          setSummary(buildDashboardSummary(result.analysis, activeConnection));
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard summary");
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [activeConnection, call, connectionsLoading, isInitialized]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-white">Home</h1>
        <p className="text-gray-400">
          Operator dashboard for setup health, semantic quality, and next actions.
        </p>
      </div>

      {!connectionsLoading && connections.length === 0 && (
        <Card className="border-gray-800 bg-gray-900">
          <CardHeader>
            <CardTitle className="text-white">Get Started</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-gray-300">
            <p>No connections are configured yet. Start with the onboarding journey.</p>
            <Link
              href="/config?wizard=onboarding"
              className="inline-flex rounded-md border border-brand px-3 py-2 text-sm font-medium text-brand hover:bg-brand hover:text-black transition-colors"
            >
              Start onboarding
            </Link>
          </CardContent>
        </Card>
      )}

      {connections.length > 0 && !activeConnection && (
        <Card className="border-gray-800 bg-gray-900">
          <CardHeader>
            <CardTitle className="text-white">Select Active Connection</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-gray-300">
            Choose an active connection from the top-right selector to load
            connection-specific insights.
          </CardContent>
        </Card>
      )}

      {loading && activeConnection && (
        <div className="text-gray-400">Loading dashboard summary...</div>
      )}

      {error && (
        <Card className="border-red-900/50 bg-red-950/20">
          <CardContent className="pt-6 text-sm text-red-300">{error}</CardContent>
        </Card>
      )}

      {summary && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="border-gray-800 bg-gray-900">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-300">Active Connection</CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold text-white">
                {summary.setup.activeConnection}
              </CardContent>
            </Card>
            <Card className="border-gray-800 bg-gray-900">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-300">Semantic Layer</CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold text-white">
                {summary.semantic.score}/{summary.semantic.maxScore}
              </CardContent>
            </Card>
            <Card className="border-gray-800 bg-gray-900">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-300">Open Actions</CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold text-white">
                {summary.openItems}
              </CardContent>
            </Card>
            <Card className="border-gray-800 bg-gray-900">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-300">Recent Traces</CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold text-white">
                {summary.recent.traces}
              </CardContent>
            </Card>
          </div>

          <Card className="border-gray-800 bg-gray-900">
            <CardHeader>
              <CardTitle className="text-white">Action Queue</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {summary.queue.length === 0 ? (
                <p className="text-sm text-gray-400">No urgent actions right now.</p>
              ) : (
                summary.queue.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-start justify-between gap-4 rounded-md border border-gray-800 p-3"
                  >
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-white">{item.title}</p>
                      <p className="text-xs text-gray-400">{item.detail}</p>
                    </div>
                    <Link
                      href={item.ctaUrl}
                      className="shrink-0 rounded-md border border-gray-700 px-3 py-1.5 text-xs text-gray-200 hover:border-gray-600"
                    >
                      {item.ctaLabel}
                    </Link>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card className="border-gray-800 bg-gray-900">
            <CardHeader>
              <CardTitle className="text-white">Recent Activity</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm text-gray-300 sm:grid-cols-3">
              <div>
                <p className="text-gray-500">Errors</p>
                <p className="text-white text-lg">{summary.recent.errors}</p>
              </div>
              <div>
                <p className="text-gray-500">Validation Failures</p>
                <p className="text-white text-lg">{summary.recent.validationFailures}</p>
              </div>
              <div>
                <p className="text-gray-500">Total Runtime</p>
                <p className="text-white text-lg">
                  {formatDuration(summary.recent.totalDurationMs)}
                </p>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
