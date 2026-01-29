"use client";

import { useState } from "react";
import type { TraceSpan } from "@/lib/bicp";
import { SpanDetail } from "./SpanDetail";
import { cn } from "@/lib/utils";

interface SpanTimelineProps {
  spans: TraceSpan[];
  traceDurationMs: number;
  traceStartTime: number;
}

function getSpanColor(span: TraceSpan): string {
  if (span.status === "error") return "bg-red-500";
  const attrs = span.attributes || {};
  if ("tool.name" in attrs) return "bg-blue-500";
  const name = span.name.toLowerCase();
  if (
    name.includes("db_") ||
    name.includes("fetch") ||
    name.includes("validate") ||
    name.includes("explain")
  ) {
    return "bg-green-500";
  }
  return "bg-gray-500";
}

function getSpanColorDot(span: TraceSpan): string {
  if (span.status === "error") return "bg-red-400";
  const attrs = span.attributes || {};
  if ("tool.name" in attrs) return "bg-blue-400";
  const name = span.name.toLowerCase();
  if (
    name.includes("db_") ||
    name.includes("fetch") ||
    name.includes("validate") ||
    name.includes("explain")
  ) {
    return "bg-green-400";
  }
  return "bg-gray-400";
}

/** Build a depth map by walking parent_span_id references. */
function computeDepths(spans: TraceSpan[]): Map<string, number> {
  const parentMap = new Map<string, string>();
  for (const s of spans) {
    if (s.parent_span_id) {
      parentMap.set(s.span_id, s.parent_span_id);
    }
  }

  const depths = new Map<string, number>();
  function depth(id: string): number {
    if (depths.has(id)) return depths.get(id)!;
    const parent = parentMap.get(id);
    const d = parent ? depth(parent) + 1 : 0;
    depths.set(id, d);
    return d;
  }

  for (const s of spans) {
    depth(s.span_id);
  }
  return depths;
}

export function SpanTimeline({
  spans,
  traceDurationMs,
  traceStartTime,
}: SpanTimelineProps) {
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const depthMap = computeDepths(spans);
  const selectedSpan = spans.find((s) => s.span_id === selectedSpanId) || null;

  return (
    <div className="space-y-1">
      {spans.map((span) => {
        const depth = depthMap.get(span.span_id) || 0;
        const offsetMs = (span.start_time - traceStartTime) * 1000;
        const leftPct =
          traceDurationMs > 0
            ? Math.min((offsetMs / traceDurationMs) * 100, 100)
            : 0;
        const widthPct =
          traceDurationMs > 0
            ? Math.max(((span.duration_ms || 0) / traceDurationMs) * 100, 1)
            : 100;
        const isSelected = span.span_id === selectedSpanId;
        const displayName =
          (span.attributes?.["tool.name"] as string) || span.name;

        return (
          <div
            key={span.span_id}
            className={cn(
              "flex items-center gap-2 py-0.5 cursor-pointer rounded px-1 -mx-1 transition-colors",
              isSelected
                ? "bg-gray-800"
                : "hover:bg-gray-800/50",
            )}
            style={{ paddingLeft: `${depth * 16 + 4}px` }}
            onClick={() =>
              setSelectedSpanId(
                isSelected ? null : span.span_id,
              )
            }
          >
            {/* Span label */}
            <div className="flex items-center gap-1.5 min-w-[140px] max-w-[200px] shrink-0">
              <div
                className={cn(
                  "w-2 h-2 rounded-full shrink-0",
                  getSpanColorDot(span),
                )}
              />
              <span className="text-xs text-gray-300 truncate font-mono">
                {displayName}
              </span>
            </div>

            {/* Timeline bar */}
            <div className="flex-1 h-5 relative bg-gray-800/30 rounded-sm overflow-hidden">
              <div
                className={cn(
                  "absolute top-0.5 bottom-0.5 rounded-sm transition-opacity",
                  getSpanColor(span),
                  isSelected ? "opacity-100" : "opacity-70",
                )}
                style={{
                  left: `${leftPct}%`,
                  width: `${widthPct}%`,
                }}
              />
            </div>

            {/* Duration */}
            <span className="text-xs text-gray-500 tabular-nums w-16 text-right shrink-0">
              {span.duration_ms !== null
                ? `${span.duration_ms.toFixed(1)}ms`
                : "—"}
            </span>
          </div>
        );
      })}

      {selectedSpan && (
        <div className="mt-2">
          <SpanDetail span={selectedSpan} />
        </div>
      )}
    </div>
  );
}
