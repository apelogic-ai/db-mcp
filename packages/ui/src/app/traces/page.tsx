"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { listTraces, clearTraces, getTraceDates } from "@/lib/bicp";
import type { Trace } from "@/lib/bicp";
import { TraceList } from "@/components/traces/TraceList";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface DayGroup {
  date: string;
  label: string;
  traces: Trace[];
  isLive: boolean;
}

function formatDateLabel(dateStr: string): string {
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  if (dateStr === today) return "Today";
  if (dateStr === yesterday) return "Yesterday";
  // Format as "Mon, Jan 28"
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export default function TracesPage() {
  const [liveTraces, setLiveTraces] = useState<Trace[]>([]);
  const [historicalGroups, setHistoricalGroups] = useState<DayGroup[]>([]);
  const [expandedDays, setExpandedDays] = useState<Set<string>>(
    new Set(["live"]),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dates, setDates] = useState<string[]>([]);
  const [loadedDates, setLoadedDates] = useState<Set<string>>(new Set());

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch live traces
  const fetchLive = useCallback(async () => {
    try {
      const result = await listTraces("live");
      if (result.success) {
        setLiveTraces(result.traces);
      }
    } catch {
      // Silent - live polling shouldn't show errors
    }
  }, []);

  // Fetch available dates
  const fetchDates = useCallback(async () => {
    try {
      const result = await getTraceDates();
      if (result.success && result.enabled) {
        setDates(result.dates);
      }
    } catch {
      // Silent
    }
  }, []);

  // Fetch historical traces for a specific date
  const fetchHistorical = useCallback(async (date: string) => {
    try {
      const result = await listTraces("historical", date);
      if (result.success) {
        setHistoricalGroups((prev) => {
          const filtered = prev.filter((g) => g.date !== date);
          if (result.traces.length === 0) return filtered;
          const group: DayGroup = {
            date,
            label: formatDateLabel(date),
            traces: result.traces,
            isLive: false,
          };
          const updated = [...filtered, group];
          updated.sort((a, b) => b.date.localeCompare(a.date));
          return updated;
        });
        setLoadedDates((prev) => new Set([...prev, date]));
      }
    } catch {
      // Silent
    }
  }, []);

  // Initial load: fetch live + dates
  useEffect(() => {
    setLoading(true);
    Promise.all([fetchLive(), fetchDates()]).finally(() => setLoading(false));

    // Poll live traces
    pollRef.current = setInterval(fetchLive, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchLive, fetchDates]);

  // When a day accordion is expanded, load its historical data
  const toggleDay = useCallback(
    (key: string) => {
      setExpandedDays((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
          // Load historical data for this date if not yet loaded
          if (key !== "live" && !loadedDates.has(key)) {
            fetchHistorical(key);
          }
        }
        return next;
      });
    },
    [loadedDates, fetchHistorical],
  );

  const handleClear = async () => {
    try {
      await clearTraces();
      setLiveTraces([]);
    } catch {
      // ignore
    }
  };

  const handleRefresh = async () => {
    setLoading(true);
    // Reload live and dates
    await Promise.all([fetchLive(), fetchDates()]);
    // Reload any expanded historical days
    const reloadPromises = [...expandedDays]
      .filter((d) => d !== "live")
      .map((d) => fetchHistorical(d));
    await Promise.all(reloadPromises);
    setLoading(false);
  };

  // Build day groups for display
  const today = new Date().toISOString().slice(0, 10);
  const allDays: { key: string; label: string; traceCount: number }[] = [];

  // Live / Today always first
  allDays.push({
    key: "live",
    label: "Today (Live)",
    traceCount: liveTraces.length,
  });

  // Historical dates (skip today since it's covered by live)
  for (const date of dates) {
    if (date === today) continue;
    const loaded = historicalGroups.find((g) => g.date === date);
    allDays.push({
      key: date,
      label: formatDateLabel(date),
      traceCount: loaded?.traces.length ?? -1, // -1 = not loaded yet
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Traces</h1>
          <p className="text-gray-400 mt-1">
            OpenTelemetry trace viewer for MCP server operations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="border-gray-700 text-gray-300 hover:bg-gray-800"
            onClick={handleRefresh}
          >
            Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="border-gray-700 text-gray-300 hover:bg-gray-800"
            onClick={handleClear}
          >
            Clear Live
          </Button>
        </div>
      </div>

      {error && (
        <div className="text-center py-4 text-red-400 text-sm">{error}</div>
      )}

      {loading && liveTraces.length === 0 && dates.length === 0 && (
        <div className="text-center py-8 text-gray-500">Loading traces...</div>
      )}

      {/* Day-grouped accordion */}
      <div className="space-y-2">
        {allDays.map(({ key, label, traceCount }) => {
          const isExpanded = expandedDays.has(key);
          const isLive = key === "live";
          const traces = isLive
            ? liveTraces
            : (historicalGroups.find((g) => g.date === key)?.traces ?? []);
          const notLoaded = !isLive && traceCount === -1;

          return (
            <div
              key={key}
              className="border border-gray-800 rounded-lg overflow-hidden"
            >
              <button
                className={cn(
                  "w-full flex items-center gap-3 px-4 py-3 text-left transition-colors",
                  isExpanded
                    ? "bg-gray-800/50"
                    : "bg-gray-900 hover:bg-gray-800/30",
                )}
                onClick={() => toggleDay(key)}
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

                <span className="text-sm font-medium text-white flex-1">
                  {label}
                </span>

                {isLive && (
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                )}

                <span className="text-xs text-gray-500 tabular-nums">
                  {notLoaded
                    ? "click to load"
                    : `${traceCount} trace${traceCount !== 1 ? "s" : ""}`}
                </span>
              </button>

              {isExpanded && (
                <div className="px-4 py-3 border-t border-gray-800 bg-gray-950">
                  {notLoaded && traces.length === 0 ? (
                    <div className="text-center py-4 text-gray-500 text-sm">
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

      {/* Live polling indicator */}
      <div className="text-center text-xs text-gray-600">
        Live traces auto-refresh every 3 seconds
      </div>
    </div>
  );
}
