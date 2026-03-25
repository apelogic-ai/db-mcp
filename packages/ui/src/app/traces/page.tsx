"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { listTraces, clearTraces, getTraceDates } from "@/lib/bicp";
import type { Trace } from "@/lib/bicp";
import { TraceList } from "@/components/traces/TraceList";
import { ConnectionWorkspaceShell } from "@/features/connections/ConnectionWorkspaceShell";
import { cn } from "@/lib/utils";

/** Local-time YYYY-MM-DD (matches JSONL filenames written with local date). */
function localDateStr(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function formatDateLabel(dateStr: string): string {
  const today = localDateStr();
  const yesterday = localDateStr(new Date(Date.now() - 86400000));
  if (dateStr === today) return "Today";
  if (dateStr === yesterday) return "Yesterday";
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

/** Merge two trace arrays, deduplicating by trace_id, most recent first. */
function mergeTraces(a: Trace[], b: Trace[]): Trace[] {
  const seen = new Set<string>();
  const merged: Trace[] = [];
  for (const t of a) {
    if (!seen.has(t.trace_id)) {
      seen.add(t.trace_id);
      merged.push(t);
    }
  }
  for (const t of b) {
    if (!seen.has(t.trace_id)) {
      seen.add(t.trace_id);
      merged.push(t);
    }
  }
  merged.sort((a, b) => b.start_time - a.start_time);
  return merged;
}

export default function TracesPage() {
  const [liveTraces, setLiveTraces] = useState<Trace[]>([]);
  const [historicalByDate, setHistoricalByDate] = useState<
    Record<string, Trace[]>
  >({});
  const [expandedDays, setExpandedDays] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dates, setDates] = useState<string[]>([]);
  const [loadedDates, setLoadedDates] = useState<Set<string>>(new Set());

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLive = useCallback(async () => {
    try {
      const result = await listTraces("live");
      if (result.success) setLiveTraces(result.traces);
    } catch {
      /* silent */
    }
  }, []);

  const fetchDates = useCallback(async () => {
    try {
      const result = await getTraceDates();
      if (result.success && result.enabled) setDates(result.dates);
    } catch {
      /* silent */
    }
  }, []);

  const fetchHistorical = useCallback(async (date: string) => {
    try {
      const result = await listTraces("historical", date, 500);
      if (result.success) {
        setHistoricalByDate((prev) => ({
          ...prev,
          [date]: result.traces,
        }));
        setLoadedDates((prev) => new Set([...prev, date]));
      }
    } catch {
      /* silent */
    }
  }, []);

  // Initial load: fetch live + dates + today's historical
  useEffect(() => {
    setLoading(true);
    const today = localDateStr();
    Promise.all([fetchLive(), fetchDates(), fetchHistorical(today)]).finally(
      () => setLoading(false),
    );
    setExpandedDays(new Set([today]));

    pollRef.current = setInterval(fetchLive, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchLive, fetchDates, fetchHistorical]);

  const toggleDay = useCallback(
    (key: string) => {
      setExpandedDays((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
          if (!loadedDates.has(key)) fetchHistorical(key);
        }
        return next;
      });
    },
    [loadedDates, fetchHistorical],
  );

  const handleClear = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await clearTraces();
      setLiveTraces([]);
    } catch {
      /* ignore */
    }
  };

  const handleRefresh = async () => {
    setLoading(true);
    const today = localDateStr();
    await Promise.all([fetchLive(), fetchDates(), fetchHistorical(today)]);
    const reloadPromises = [...expandedDays]
      .filter((d) => d !== today)
      .map((d) => fetchHistorical(d));
    await Promise.all(reloadPromises);
    setLoading(false);
  };

  // Build day list from server dates
  const today = localDateStr();
  const hasLive = liveTraces.length > 0;

  // Ensure today is always in the list even if server didn't return it
  const allDates = dates.includes(today) ? dates : [today, ...dates];

  // For each date, compute the traces to show
  const dayEntries = allDates.map((date) => {
    const historical = historicalByDate[date] ?? [];
    const isToday = date === today;
    // Merge live traces into today
    const traces = isToday ? mergeTraces(liveTraces, historical) : historical;
    const isLoaded = loadedDates.has(date) || isToday;

    return {
      key: date,
      label: formatDateLabel(date),
      traces,
      traceCount: isLoaded ? traces.length : -1,
      isToday,
    };
  });

  return (
    <ConnectionWorkspaceShell currentView={null} currentAdvancedView="traces">
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Traces</h1>
            <p className="mt-1 text-gray-400">
              OpenTelemetry trace viewer for MCP server operations
            </p>
          </div>
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="rounded p-1.5 text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200 disabled:opacity-50"
            title="Refresh traces"
          >
            <svg
              className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
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

        {error && (
          <div className="py-4 text-center text-sm text-red-400">{error}</div>
        )}

        {loading && dayEntries.every((d) => d.traceCount <= 0) && (
          <div className="py-8 text-center text-gray-500">Loading traces...</div>
        )}

        <div className="space-y-2">
          {dayEntries.map(({ key, label, traces, traceCount, isToday }) => {
            const isExpanded = expandedDays.has(key);
            const notLoaded = traceCount === -1;

            return (
              <div
                key={key}
                className="overflow-hidden rounded-lg border border-gray-800"
              >
                <button
                  className={cn(
                    "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors",
                    isExpanded
                      ? "bg-gray-800/50"
                      : "bg-gray-900 hover:bg-gray-800/30",
                  )}
                  onClick={() => toggleDay(key)}
                >
                  <svg
                    className={cn(
                      "h-3 w-3 shrink-0 text-gray-500 transition-transform",
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

                  <span className="flex-1 text-sm font-medium text-white">
                    {label}
                  </span>

                  {isToday && hasLive && (
                    <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                  )}

                  <span className="tabular-nums text-xs text-gray-500">
                    {notLoaded
                      ? "click to load"
                      : `${traceCount} trace${traceCount !== 1 ? "s" : ""}`}
                  </span>

                  {isToday && hasLive && (
                    <button
                      onClick={handleClear}
                      className="ml-1 rounded p-1 text-gray-500 transition-colors hover:bg-gray-700 hover:text-gray-300"
                      title="Clear live traces"
                    >
                      <svg
                        className="h-3.5 w-3.5"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
                        />
                      </svg>
                    </button>
                  )}
                </button>

                {isExpanded && (
                  <div className="border-t border-gray-800 bg-gray-950 px-4 py-3">
                    {notLoaded && traces.length === 0 ? (
                      <div className="py-4 text-center text-sm text-gray-500">
                        Loading...
                      </div>
                    ) : (
                      <TraceList traces={traces} />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="text-center text-xs text-gray-600">
          Live traces auto-refresh every 3 seconds
        </div>
      </div>
    </ConnectionWorkspaceShell>
  );
}
