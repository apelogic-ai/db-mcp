"use client";

import { useState } from "react";
import type { Trace } from "@/lib/bicp";
import { SpanTimeline } from "./SpanTimeline";
import { cn } from "@/lib/utils";

/** MCP protocol housekeeping patterns — not interesting for observability. */
const NOISE_PATTERNS = [
  "prompts/list",
  "tools/list",
  "resources/list",
  "initialize",
  "notifications/initialized",
  "ping",
];

function isNoiseTrace(trace: Trace): boolean {
  // Single-span traces matching protocol housekeeping
  if (trace.span_count > 1) return false;
  const name = (trace.root_span || "").toLowerCase();
  return NOISE_PATTERNS.some((p) => name.includes(p));
}

interface TraceListProps {
  traces: Trace[];
  showNoise?: boolean;
}

/** Extract a short highlight from trace spans (SQL or shell command). */
function extractHighlight(trace: Trace): string | null {
  for (const span of trace.spans) {
    // SQL preview
    const sql = (span.attributes?.["sql.preview"] ??
      span.attributes?.["sql"]) as string | undefined;
    if (sql) {
      const first = sql.replace(/\s+/g, " ").trim();
      return first.length > 60 ? first.slice(0, 57) + "..." : first;
    }
    // Shell command preview
    const command = span.attributes?.["command"] as string | undefined;
    if (command) {
      const first = command.replace(/\s+/g, " ").trim();
      return first.length > 60 ? first.slice(0, 57) + "..." : first;
    }
  }
  return null;
}

function formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms.toFixed(1)}ms`;
}

function formatTimestamp(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function TraceList({ traces, showNoise = false }: TraceListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = showNoise ? traces : traces.filter((t) => !isNoiseTrace(t));
  const hiddenCount = traces.length - filtered.length;

  if (traces.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p className="text-lg">No traces found</p>
        <p className="text-sm mt-1">
          Traces will appear here when MCP tools are called
        </p>
      </div>
    );
  }

  if (filtered.length === 0) {
    return (
      <div className="text-center text-xs text-gray-600 pt-2">
        {hiddenCount} protocol trace{hiddenCount !== 1 ? "s" : ""} hidden
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {filtered.map((trace) => {
        const isExpanded = expandedId === trace.trace_id;
        const rootName =
          (trace.spans?.[0]?.attributes?.["tool.name"] as string) ||
          trace.root_span ||
          trace.trace_id.slice(0, 8);
        const highlight = extractHighlight(trace);

        return (
          <div
            key={trace.trace_id}
            className="border border-gray-800 rounded-md overflow-hidden"
          >
            {/* Trace header row */}
            <button
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2 text-left transition-colors",
                isExpanded ? "bg-gray-800" : "bg-gray-900 hover:bg-gray-800/70",
              )}
              onClick={() => setExpandedId(isExpanded ? null : trace.trace_id)}
            >
              <svg
                className={cn(
                  "w-3 h-3 text-gray-500 transition-transform shrink-0",
                  isExpanded && "rotate-90",
                )}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 5l7 7-7 7"
                />
              </svg>

              <div className="flex-1 min-w-0">
                <span className="text-sm text-white font-mono truncate block">
                  {rootName}
                </span>
                {highlight && (
                  <span className="text-xs text-gray-500 font-mono truncate block">
                    {highlight}
                  </span>
                )}
              </div>

              <span className="text-xs text-gray-500 tabular-nums shrink-0">
                {trace.span_count} span{trace.span_count !== 1 ? "s" : ""}
              </span>

              <span className="text-xs text-gray-400 tabular-nums shrink-0 w-20 text-right">
                {formatDuration(trace.duration_ms)}
              </span>

              <span className="text-xs text-gray-500 shrink-0">
                {formatTimestamp(trace.start_time)}
              </span>
            </button>

            {/* Expanded span timeline */}
            {isExpanded && (
              <div className="px-3 py-2 border-t border-gray-800 bg-gray-950">
                <SpanTimeline
                  spans={trace.spans}
                  traceDurationMs={trace.duration_ms}
                  traceStartTime={trace.start_time}
                />
              </div>
            )}
          </div>
        );
      })}
      {hiddenCount > 0 && (
        <div className="text-center text-xs text-gray-600 pt-2">
          {hiddenCount} protocol trace{hiddenCount !== 1 ? "s" : ""} hidden
        </div>
      )}
    </div>
  );
}
