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
import { analyzeInsights, type InsightsAnalysis } from "@/lib/bicp";

function formatDuration(ms: number): string {
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)}m`;
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms.toFixed(0)}ms`;
}

function formatTimestamp(ts: number): string {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Horizontal bar sized relative to max value. */
function Bar({
  value,
  max,
  label,
  color = "bg-blue-500",
}: {
  value: number;
  max: number;
  label: string;
  color?: string;
}) {
  const pct = max > 0 ? Math.max((value / max) * 100, 2) : 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 text-gray-400 truncate text-right font-mono">
        {label}
      </span>
      <div className="flex-1 bg-gray-800 rounded h-4 overflow-hidden">
        <div
          className={`${color} h-full rounded transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-gray-500 tabular-nums text-right">{value}</span>
    </div>
  );
}

function SemanticLayerCard({
  status,
}: {
  status: InsightsAnalysis["knowledgeStatus"];
}) {
  const items = [
    {
      label: "Schema descriptions",
      ok: status.hasSchema,
      detail: status.hasSchema ? "configured" : "missing",
    },
    {
      label: "Domain model",
      ok: status.hasDomain,
      detail: status.hasDomain ? "configured" : "missing",
    },
    {
      label: "Training examples",
      ok: status.exampleCount > 0,
      detail: `${status.exampleCount} saved`,
    },
    {
      label: "Business rules",
      ok: status.ruleCount > 0,
      detail: `${status.ruleCount} defined`,
    },
  ];

  const completeness = items.filter((i) => i.ok).length;

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          Semantic Layer
          <Badge
            variant="secondary"
            className={
              completeness === 4
                ? "bg-green-900/50 text-green-400"
                : completeness >= 2
                  ? "bg-yellow-900/50 text-yellow-400"
                  : "bg-red-900/50 text-red-400"
            }
          >
            {completeness}/4
          </Badge>
        </CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          Knowledge layer completeness for the active connection
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-2 text-xs">
            <span className={item.ok ? "text-green-500" : "text-red-500"}>
              {item.ok ? "\u2713" : "\u2717"}
            </span>
            <span className="text-gray-300">{item.label}</span>
            <span className="text-gray-600 ml-auto">{item.detail}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ToolUsageCard({ usage }: { usage: Record<string, number> }) {
  const entries = Object.entries(usage).sort((a, b) => b[1] - a[1]);
  const max = entries.length > 0 ? entries[0][1] : 0;

  if (entries.length === 0) {
    return (
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader className="pb-3">
          <CardTitle className="text-white text-sm">Tool Usage</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-500 text-xs">No tool calls recorded</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm">Tool Usage</CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          Distribution of MCP tool calls
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {entries.map(([tool, count]) => (
          <Bar
            key={tool}
            label={tool}
            value={count}
            max={max}
            color={
              tool.includes("validate")
                ? "bg-yellow-500"
                : tool.includes("run")
                  ? "bg-green-500"
                  : tool === "shell"
                    ? "bg-purple-500"
                    : "bg-blue-500"
            }
          />
        ))}
      </CardContent>
    </Card>
  );
}

function RepeatedQueriesCard({
  queries,
}: {
  queries: InsightsAnalysis["repeatedQueries"];
}) {
  if (queries.length === 0) return null;

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          Repeated Queries
          <Badge
            variant="secondary"
            className="bg-yellow-900/50 text-yellow-400"
          >
            {queries.length}
          </Badge>
        </CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          Same SQL executed multiple times — consider saving as training
          examples
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {queries.map((q, i) => (
          <div key={i} className="border border-gray-800 rounded p-2">
            <code className="text-xs text-gray-300 font-mono block truncate">
              {q.sql_preview}
            </code>
            <div className="flex gap-3 mt-1 text-xs text-gray-500">
              <span>{q.count}x executed</span>
              <span>First: {formatTimestamp(q.first_seen)}</span>
              <span>Last: {formatTimestamp(q.last_seen)}</span>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ErrorsCard({
  errors,
  errorCount,
  validationFailures,
  validationFailureCount,
}: {
  errors: InsightsAnalysis["errors"];
  errorCount: number;
  validationFailures: InsightsAnalysis["validationFailures"];
  validationFailureCount: number;
}) {
  if (errorCount === 0 && validationFailureCount === 0) return null;

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          Errors &amp; Failures
          {errorCount > 0 && (
            <Badge variant="secondary" className="bg-red-900/50 text-red-400">
              {errorCount} error{errorCount !== 1 ? "s" : ""}
            </Badge>
          )}
          {validationFailureCount > 0 && (
            <Badge
              variant="secondary"
              className="bg-yellow-900/50 text-yellow-400"
            >
              {validationFailureCount} validation failure
              {validationFailureCount !== 1 ? "s" : ""}
            </Badge>
          )}
        </CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          Failed tool calls and SQL validation issues
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {errors.slice(0, 5).map((e, i) => (
          <div
            key={`err-${i}`}
            className="border border-red-900/30 rounded p-2 text-xs"
          >
            <span className="text-red-400 font-mono">
              {e.tool || e.span_name}
            </span>
            {e.error && (
              <p className="text-gray-500 mt-0.5 truncate">{e.error}</p>
            )}
            <span className="text-gray-600 text-[10px]">
              {formatTimestamp(e.timestamp)}
            </span>
          </div>
        ))}
        {validationFailures.slice(0, 5).map((v, i) => (
          <div
            key={`val-${i}`}
            className="border border-yellow-900/30 rounded p-2 text-xs"
          >
            <code className="text-yellow-400 font-mono block truncate">
              {v.sql_preview || "SQL validation failed"}
            </code>
            {v.error_message && (
              <p className="text-gray-500 mt-0.5 truncate">{v.error_message}</p>
            )}
            {v.rejected_keyword && (
              <span className="text-yellow-600">
                Rejected: {v.rejected_keyword}
              </span>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function KnowledgeCaptureCard({
  events,
  count,
  traceCount,
}: {
  events: InsightsAnalysis["knowledgeEvents"];
  count: number;
  traceCount: number;
}) {
  const captureRate =
    traceCount > 0 ? ((count / traceCount) * 100).toFixed(0) : "0";

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          Knowledge Capture
          <Badge
            variant="secondary"
            className={
              count > 0
                ? "bg-green-900/50 text-green-400"
                : "bg-gray-800 text-gray-400"
            }
          >
            {count} event{count !== 1 ? "s" : ""}
          </Badge>
        </CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          {count > 0
            ? `${captureRate}% of tool traces led to knowledge capture (examples saved, feedback given)`
            : "No examples saved or feedback given in this period. Consider approving successful queries to improve future generation."}
        </CardDescription>
      </CardHeader>
      {events.length > 0 && (
        <CardContent className="space-y-1.5">
          {events.slice(0, 8).map((e, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className="text-green-500">+</span>
              <span className="text-gray-300 font-mono">{e.tool}</span>
              {e.feedback_type && (
                <Badge
                  variant="secondary"
                  className="bg-gray-800 text-gray-400 text-[10px]"
                >
                  {e.feedback_type}
                </Badge>
              )}
              <span className="text-gray-600 ml-auto">
                {formatTimestamp(e.timestamp)}
              </span>
            </div>
          ))}
        </CardContent>
      )}
    </Card>
  );
}

function TablesCard({ tables }: { tables: Record<string, number> }) {
  const entries = Object.entries(tables).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;

  const max = entries[0][1];

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm">Tables Referenced</CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          Most queried tables across traces
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {entries.slice(0, 10).map(([table, count]) => (
          <Bar
            key={table}
            label={table}
            value={count}
            max={max}
            color="bg-cyan-500"
          />
        ))}
      </CardContent>
    </Card>
  );
}

export default function InsightsPage() {
  const [analysis, setAnalysis] = useState<InsightsAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchInsights = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await analyzeInsights(days);
      if (result.success) {
        setAnalysis(result.analysis);
      } else {
        setError(result.error || "Failed to load insights");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [days]);

  // Initial fetch + auto-refresh every 5s
  useEffect(() => {
    fetchInsights();
    intervalRef.current = setInterval(fetchInsights, 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchInsights]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Insights</h1>
          <p className="text-gray-400 mt-1">
            Semantic layer gaps and usage patterns from trace analysis
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded px-2 py-1"
          >
            <option value={1}>Last 24h</option>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
          </select>
          <button
            onClick={fetchInsights}
            disabled={loading}
            className="p-1.5 rounded hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-50"
            title="Refresh insights"
          >
            <svg
              className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        </div>
      </div>

      {error && (
        <Card className="bg-red-950/30 border-red-900/50">
          <CardContent className="py-3">
            <p className="text-red-400 text-sm">{error}</p>
          </CardContent>
        </Card>
      )}

      {loading && !analysis && (
        <div className="text-center py-12 text-gray-500">
          <p>Analyzing traces...</p>
        </div>
      )}

      {analysis && (
        <>
          {/* Summary row */}
          <div className="grid grid-cols-4 gap-3">
            {[
              {
                label: "Tool Traces",
                value: analysis.traceCount.toString(),
                sub: `${analysis.protocolTracesFiltered} protocol filtered`,
              },
              {
                label: "Total Duration",
                value: formatDuration(analysis.totalDurationMs),
                sub: "across all traces",
              },
              {
                label: "Errors",
                value: analysis.errorCount.toString(),
                sub: `${analysis.validationFailureCount} validation failures`,
                alert: analysis.errorCount > 0,
              },
              {
                label: "Knowledge Captured",
                value: analysis.knowledgeCaptureCount.toString(),
                sub:
                  analysis.knowledgeCaptureCount > 0
                    ? "examples & feedback saved"
                    : "no capture yet",
                alert:
                  analysis.knowledgeCaptureCount === 0 &&
                  analysis.traceCount > 0,
              },
            ].map((stat) => (
              <Card key={stat.label} className="bg-gray-900 border-gray-800">
                <CardContent className="py-3 px-4">
                  <p className="text-gray-500 text-xs">{stat.label}</p>
                  <p
                    className={`text-xl font-bold ${stat.alert ? "text-yellow-400" : "text-white"}`}
                  >
                    {stat.value}
                  </p>
                  <p className="text-gray-600 text-[10px]">{stat.sub}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Main grid */}
          <div className="grid grid-cols-2 gap-4">
            <SemanticLayerCard status={analysis.knowledgeStatus} />
            <ToolUsageCard usage={analysis.toolUsage} />
            <RepeatedQueriesCard queries={analysis.repeatedQueries} />
            <ErrorsCard
              errors={analysis.errors}
              errorCount={analysis.errorCount}
              validationFailures={analysis.validationFailures}
              validationFailureCount={analysis.validationFailureCount}
            />
            <KnowledgeCaptureCard
              events={analysis.knowledgeEvents}
              count={analysis.knowledgeCaptureCount}
              traceCount={analysis.traceCount}
            />
            <TablesCard tables={analysis.tablesReferenced} />
          </div>

          {analysis.traceCount === 0 && (
            <Card className="bg-gray-900 border-gray-800">
              <CardContent className="py-8 text-center">
                <p className="text-gray-500">
                  No tool traces found for the selected period.
                </p>
                <p className="text-gray-600 text-sm mt-1">
                  Use MCP tools via Claude Desktop to generate trace data.
                </p>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
