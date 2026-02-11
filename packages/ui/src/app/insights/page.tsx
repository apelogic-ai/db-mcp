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
import {
  analyzeInsights,
  bicpCall,
  contextAddRule,
  dismissGap,
  saveExample,
  type InsightsAnalysis,
} from "@/lib/bicp";

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

function KnowledgeFlowBanner({
  insights,
  traceCount,
}: {
  insights: InsightsAnalysis["insights"];
  traceCount: number;
}) {
  const [dismissed, setDismissed] = useState<string | null>(null);

  const {
    knowledgeCapturesByType,
    sessionCount,
  } = insights;

  const captureTotal = Object.values(knowledgeCapturesByType).reduce(
    (a, b) => a + b,
    0,
  );

  // Get active connection ID for localStorage key
  const [connectionId, setConnectionId] = useState<string>("");
  
  useEffect(() => {
    bicpCall<{
      connections: Array<{ name: string; isActive: boolean }>;
      activeConnection: string | null;
    }>("connections/list", {}).then(result => {
      if (result.activeConnection) {
        setConnectionId(result.activeConnection);
      }
    }).catch(() => {
      // Ignore errors, just use empty string
    });
  }, []);

  // Determine banner state
  let state: "green" | "yellow" | "neutral";
  if (captureTotal > 0) {
    state = "green";
  } else if (traceCount > 5) {
    state = "yellow";
  } else {
    state = "neutral";
  }

  // Check if dismissed
  useEffect(() => {
    if (connectionId && state !== "neutral") {
      const dismissKey = `insights-banner-dismissed-${connectionId}`;
      const lastDismissed = localStorage.getItem(dismissKey);
      setDismissed(lastDismissed);
    }
  }, [connectionId, state]);

  // Reset dismiss state when state changes (e.g., was yellow, now green)
  useEffect(() => {
    if (connectionId) {
      const dismissKey = `insights-banner-dismissed-${connectionId}`;
      const lastDismissedState = localStorage.getItem(`${dismissKey}-state`);
      
      if (lastDismissedState && lastDismissedState !== state) {
        // State changed, reset dismissal
        localStorage.removeItem(dismissKey);
        localStorage.setItem(`${dismissKey}-state`, state);
        setDismissed(null);
      } else if (!lastDismissedState) {
        localStorage.setItem(`${dismissKey}-state`, state);
      }
    }
  }, [connectionId, state]);

  const handleDismiss = () => {
    if (connectionId && state !== "neutral") {
      const dismissKey = `insights-banner-dismissed-${connectionId}`;
      const timestamp = Date.now().toString();
      localStorage.setItem(dismissKey, timestamp);
      setDismissed(timestamp);
    }
  };

  // Don't show if dismissed (except neutral state which is never dismissible)
  if (dismissed && state !== "neutral") {
    return null;
  }

  const stateConfig = {
    green: {
      borderColor: "border-l-green-500 border border-green-500/30",
      bgColor: "bg-green-900/20",
      icon: "✓",
      iconColor: "text-green-500",
      text: `Knowledge capture active — ${captureTotal} examples & feedback saved${sessionCount > 0 ? ` (${sessionCount} session${sessionCount !== 1 ? 's' : ''})` : ''}`,
      dismissable: true,
    },
    yellow: {
      borderColor: "border-l-yellow-500 border border-yellow-500/30",
      bgColor: "bg-yellow-900/20",
      icon: "⚠",
      iconColor: "text-yellow-500",
      text: "No knowledge captured in this period. Approve successful queries to build your semantic layer.",
      dismissable: true,
    },
    neutral: {
      borderColor: "border-l-gray-500 border border-gray-500/30",
      bgColor: "bg-gray-900/30",
      icon: "ⓘ",
      iconColor: "text-gray-500",
      text: "Start using your agent to generate SQL — insights will appear as traces are recorded.",
      dismissable: false,
    },
  };

  const config = stateConfig[state];
  const learnHowUrl = process.env.NEXT_PUBLIC_KNOWLEDGE_HOWTO_URL;

  return (
    <div className={`w-full border-l-4 ${config.borderColor} ${config.bgColor} rounded p-3 flex items-center gap-3`}>
      <span className={`${config.iconColor} text-sm shrink-0`}>
        {config.icon}
      </span>
      <span className="text-gray-300 text-sm flex-1">
        {config.text}
        {state === "yellow" && learnHowUrl && (
          <span>
            {" "}
            <a 
              href={learnHowUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 underline"
            >
              Learn how →
            </a>
          </span>
        )}
      </span>
      {config.dismissable && (
        <button
          onClick={handleDismiss}
          className="text-gray-500 hover:text-gray-300 text-sm shrink-0 ml-2"
          title="Dismiss"
        >
          ×
        </button>
      )}
    </div>
  );
}

function VocabularyGapsCard({
  gaps,
}: {
  gaps: InsightsAnalysis["vocabularyGaps"];
}) {
  const [addingIdx, setAddingIdx] = useState<number | null>(null);
  const [addedIdxs, setAddedIdxs] = useState<Set<number>>(new Set());
  const [dismissedIdxs, setDismissedIdxs] = useState<Set<number>>(new Set());
  const [addError, setAddError] = useState<string | null>(null);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [customRule, setCustomRule] = useState("");

  if (!gaps || gaps.length === 0) return null;

  const openGaps = gaps.filter(
    (g) => g.status !== "resolved" && g.status !== "dismissed",
  );
  const resolvedGaps = gaps.filter((g) => g.status === "resolved");
  const dismissedGaps = gaps.filter((g) => g.status === "dismissed");
  const openCount = openGaps.length;
  const resolvedCount = resolvedGaps.length;
  const dismissedCount = dismissedGaps.length;

  const handleAddRule = async (
    groupIdx: number,
    rule: string,
    gapId?: string,
  ) => {
    setAddingIdx(groupIdx);
    setAddError(null);
    try {
      const connResult = await bicpCall<{
        connections: Array<{ name: string; isActive: boolean }>;
        activeConnection: string | null;
      }>("connections/list", {});
      const conn = connResult.activeConnection;
      if (!conn) {
        setAddError("No active connection");
        return;
      }

      const result = await contextAddRule(conn, rule, gapId);
      if (result.success) {
        setAddedIdxs((prev) => new Set(prev).add(groupIdx));
        setEditingIdx(null);
        setCustomRule("");
      } else {
        setAddError(result.error || "Failed to add rule");
      }
    } catch (e) {
      setAddError(e instanceof Error ? e.message : "Failed to add rule");
    } finally {
      setAddingIdx(null);
    }
  };

  const handleDismiss = async (groupIdx: number, gapId: string) => {
    setAddError(null);
    try {
      const connResult = await bicpCall<{
        connections: Array<{ name: string; isActive: boolean }>;
        activeConnection: string | null;
      }>("connections/list", {});
      const conn = connResult.activeConnection;
      if (!conn) {
        setAddError("No active connection");
        return;
      }

      const result = await dismissGap(conn, gapId, "false positive");
      if (result.success) {
        setDismissedIdxs((prev) => new Set(prev).add(groupIdx));
      } else {
        setAddError(result.error || "Failed to dismiss gap");
      }
    } catch (e) {
      setAddError(e instanceof Error ? e.message : "Failed to dismiss gap");
    }
  };

  return (
    <Card className="bg-gray-900 border-gray-800 col-span-2">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          <span className="text-yellow-400">&#x26A0;</span>
          Unmapped Terms
          <Badge
            variant="secondary"
            className="bg-yellow-900/50 text-yellow-400"
          >
            {openCount} open
          </Badge>
          {resolvedCount > 0 && (
            <Badge
              variant="secondary"
              className="bg-green-900/50 text-green-400"
            >
              {resolvedCount} resolved
            </Badge>
          )}
          {dismissedCount > 0 && (
            <Badge variant="secondary" className="bg-gray-800 text-gray-500">
              {dismissedCount} dismissed
            </Badge>
          )}
        </CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          Business terms the agent couldn&apos;t find in schema, examples, or
          rules &mdash; causing repeated searches. Add these as aliases in
          business rules.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {addError && <p className="text-red-400 text-xs">{addError}</p>}
        {/* Open gaps */}
        {openGaps.map((group, gi) => (
          <div
            key={`open-${gi}`}
            className="border border-yellow-900/30 rounded p-3 space-y-2"
          >
            {/* Terms row */}
            <div className="flex items-center gap-2 flex-wrap">
              {group.terms.map((t, ti) => (
                <span key={ti} className="flex items-center gap-1">
                  <code className="text-yellow-300 font-mono text-sm font-bold">
                    {t.term}
                  </code>
                  {t.searchCount > 0 && (
                    <span className="text-gray-600 text-[10px]">
                      {t.searchCount}x
                    </span>
                  )}
                  {ti < group.terms.length - 1 && (
                    <span className="text-gray-700 mx-0.5">/</span>
                  )}
                </span>
              ))}
              {group.source && (
                <Badge
                  variant="secondary"
                  className="bg-gray-800 text-gray-500 text-[10px]"
                >
                  {group.source === "schema_scan" ? "schema scan" : "traces"}
                </Badge>
              )}
              <span className="text-gray-600 text-xs ml-auto">
                {formatTimestamp(group.timestamp)}
              </span>
            </div>

            {/* Schema matches */}
            {group.schemaMatches.length > 0 && (
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-gray-600 text-[10px]">found in:</span>
                {group.schemaMatches.map((m, mi) => (
                  <span
                    key={mi}
                    className="text-[10px] bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded font-mono"
                  >
                    {m.type === "column" && m.table
                      ? `${m.table}.${m.name}`
                      : m.name}
                  </span>
                ))}
              </div>
            )}

            {/* Rule action */}
            {addedIdxs.has(gi) ? (
              <div className="flex items-center gap-2">
                <span className="text-green-400 text-xs whitespace-nowrap">
                  &#x2713; Added
                </span>
              </div>
            ) : dismissedIdxs.has(gi) ? (
              <div className="flex items-center gap-2">
                <span className="text-gray-500 text-xs whitespace-nowrap">
                  &#x2717; Dismissed
                </span>
              </div>
            ) : editingIdx === gi ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={customRule}
                  onChange={(e) => setCustomRule(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && customRule.trim()) {
                      handleAddRule(gi, customRule.trim(), group.id);
                    } else if (e.key === "Escape") {
                      setEditingIdx(null);
                      setCustomRule("");
                    }
                  }}
                  placeholder={`e.g. ${group.terms[0]?.term || "term"} means ...`}
                  autoFocus
                  className="flex-1 bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1 focus:outline-none focus:border-blue-500"
                />
                <button
                  onClick={() => {
                    if (customRule.trim()) {
                      handleAddRule(gi, customRule.trim(), group.id);
                    }
                  }}
                  disabled={!customRule.trim() || addingIdx !== null}
                  className="text-xs text-blue-400 hover:text-blue-300 whitespace-nowrap disabled:opacity-50 transition-colors"
                >
                  {addingIdx === gi ? "Adding..." : "Save"}
                </button>
                <button
                  onClick={() => {
                    setEditingIdx(null);
                    setCustomRule("");
                  }}
                  className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                {group.suggestedRule && (
                  <code className="text-gray-500 text-[11px] flex-1 truncate">
                    {group.suggestedRule}
                  </code>
                )}
                <div className="flex items-center gap-2 ml-auto">
                  {group.id && (
                    <button
                      onClick={() => handleDismiss(gi, group.id!)}
                      className="text-xs text-gray-600 hover:text-gray-400 whitespace-nowrap transition-colors"
                      title="Dismiss as false positive"
                    >
                      Dismiss
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setEditingIdx(gi);
                      setCustomRule(group.suggestedRule || "");
                    }}
                    className="text-xs text-blue-400 hover:text-blue-300 whitespace-nowrap transition-colors"
                  >
                    + Add Rule
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
        {/* Resolved gaps — shown dimmed */}
        {resolvedGaps.length > 0 && (
          <div className="space-y-2 pt-2 border-t border-gray-800">
            {resolvedGaps.map((group, gi) => (
              <div
                key={`resolved-${gi}`}
                className="border border-gray-800/50 rounded p-3 opacity-60"
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-green-500 text-sm">&#x2713;</span>
                  {group.terms.map((t, ti) => (
                    <span key={ti} className="flex items-center gap-1">
                      <code className="text-gray-400 font-mono text-sm line-through">
                        {t.term}
                      </code>
                      {ti < group.terms.length - 1 && (
                        <span className="text-gray-700 mx-0.5">/</span>
                      )}
                    </span>
                  ))}
                  <span className="text-gray-600 text-xs ml-auto">
                    resolved
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
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
    {
      label: "Metrics",
      ok: (status.metricCount ?? 0) > 0,
      detail: `${status.metricCount ?? 0} approved`,
    },
  ];

  const completeness = items.filter((i) => i.ok).length;
  const total = items.length;

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          Semantic Layer
          <Badge
            variant="secondary"
            className={
              completeness === total
                ? "bg-green-900/50 text-green-400"
                : completeness >= 2
                  ? "bg-yellow-900/50 text-yellow-400"
                  : "bg-red-900/50 text-red-400"
            }
          >
            {completeness}/{total}
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

/** Extract a suggested learning note from an error message. */
function suggestLearningNote(error: string): string {
  const tableMatch = error.match(/Table '([^']+)' does not exist/i);
  if (tableMatch)
    return `Table '${tableMatch[1]}' does not exist \u2014 use correct table name`;

  const schemaMatch = error.match(/Schema '([^']+)' does not exist/i);
  if (schemaMatch)
    return `Schema '${schemaMatch[1]}' does not exist \u2014 use correct schema`;

  const colMatch = error.match(/Column '([^']+)' cannot be resolved/i);
  if (colMatch)
    return `Column '${colMatch[1]}' does not exist \u2014 check column names`;

  const lineMatch = error.match(/line \d+:\d+: (.+?)(?:\[|$)/);
  if (lineMatch) return lineMatch[1].trim();

  return "";
}

/** Expandable SQL row used by both repeated queries and auto-corrected errors. */
function SqlPatternRow({
  borderColor,
  label,
  badges,
  sqlPreview,
  fullSql,
  meta,
  error,
  isSaved,
  actionLabel,
  suggestedNote,
  placeholder,
  onSave,
  saving,
}: {
  borderColor: string;
  label?: string;
  badges: Array<{ text: string; className: string }>;
  sqlPreview: string;
  fullSql: string;
  meta: string;
  error?: string;
  isSaved: boolean;
  actionLabel: string;
  suggestedNote: string;
  placeholder: string;
  onSave: (note: string) => Promise<void>;
  saving: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [noteText, setNoteText] = useState(suggestedNote);
  const [editing, setEditing] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!noteText.trim()) return;
    setLocalError(null);
    try {
      await onSave(noteText.trim());
      setEditing(false);
      setExpanded(false);
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : "Failed to save");
    }
  };

  return (
    <div className={`border border-${borderColor} rounded text-xs`}>
      {/* Clickable header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left p-2 hover:bg-gray-800/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-gray-600 text-[10px] shrink-0">
            {expanded ? "\u25BE" : "\u25B8"}
          </span>
          {label && (
            <span className="text-amber-400 font-mono shrink-0">{label}</span>
          )}
          {badges.map((b, bi) => (
            <Badge
              key={bi}
              variant="secondary"
              className={`${b.className} text-[10px] shrink-0`}
            >
              {b.text}
            </Badge>
          ))}
          <span className="text-gray-600 text-[10px] ml-auto shrink-0">
            {meta}
          </span>
          <span
            className="shrink-0 ml-2"
            onClick={(ev) => ev.stopPropagation()}
          >
            {isSaved ? (
              <span className="text-green-500">{"\u2713"} Saved</span>
            ) : !editing ? (
              <button
                onClick={(ev) => {
                  ev.stopPropagation();
                  setEditing(true);
                  setExpanded(true);
                  setNoteText(suggestedNote);
                }}
                className="text-blue-400 hover:text-blue-300 transition-colors"
              >
                {actionLabel}
              </button>
            ) : null}
          </span>
        </div>
        {!expanded && (
          <code className="text-gray-400 font-mono block truncate mt-1 pl-4">
            {sqlPreview}
          </code>
        )}
        {!expanded && error && (
          <p className="text-gray-500 mt-0.5 truncate pl-4">{error}</p>
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-2 pb-2 space-y-2">
          <pre className="bg-gray-950 border border-gray-800 rounded p-2 text-gray-300 font-mono text-[11px] overflow-x-auto max-h-48 whitespace-pre-wrap">
            {fullSql}
          </pre>
          {error && (
            <p className="text-amber-400/80 text-[11px] truncate">{error}</p>
          )}
          {editing && !isSaved && (
            <div className="flex gap-2">
              <input
                type="text"
                value={noteText}
                onChange={(ev) => setNoteText(ev.target.value)}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter") handleSave();
                  if (ev.key === "Escape") {
                    setEditing(false);
                    setNoteText(suggestedNote);
                  }
                }}
                placeholder={placeholder}
                className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500"
                autoFocus
              />
              <button
                onClick={handleSave}
                disabled={saving || !noteText.trim()}
                className="text-xs px-2 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded transition-colors"
              >
                {saving ? "..." : "Save"}
              </button>
              <button
                onClick={() => {
                  setEditing(false);
                  setNoteText(suggestedNote);
                }}
                className="text-xs px-2 py-1 text-gray-400 hover:text-gray-300 transition-colors"
              >
                Cancel
              </button>
            </div>
          )}
          {localError && <p className="text-red-400 text-xs">{localError}</p>}
        </div>
      )}
    </div>
  );
}

function SqlPatternsCard({
  repeatedQueries,
  errors,
  errorCount,
  validationFailures,
  validationFailureCount,
}: {
  repeatedQueries: InsightsAnalysis["repeatedQueries"];
  errors: InsightsAnalysis["errors"];
  errorCount: number;
  validationFailures: InsightsAnalysis["validationFailures"];
  validationFailureCount: number;
}) {
  const [savedIdxs, setSavedIdxs] = useState<Set<string>>(new Set());
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const hardErrors = errors.filter((e) => e.error_type !== "soft");
  const softErrors = errors.filter((e) => e.error_type === "soft");

  const hasContent =
    repeatedQueries.length > 0 || errorCount > 0 || validationFailureCount > 0;

  if (!hasContent) return null;

  const getActiveConnection = async () => {
    const connResult = await bicpCall<{
      connections: Array<{ name: string; isActive: boolean }>;
      activeConnection: string | null;
    }>("connections/list", {});
    return connResult.activeConnection;
  };

  const handleSaveExample = async (key: string, sql: string, note: string) => {
    setSavingKey(key);
    try {
      const conn = await getActiveConnection();
      if (!conn) throw new Error("No active connection");
      const result = await saveExample(conn, sql, note);
      if (result.success) {
        setSavedIdxs((prev) => new Set(prev).add(key));
      } else {
        throw new Error(result.error || "Failed to save");
      }
    } finally {
      setSavingKey(null);
    }
  };

  const handleSaveLearning = async (key: string, sql: string, note: string) => {
    setSavingKey(key);
    try {
      const conn = await getActiveConnection();
      if (!conn) throw new Error("No active connection");
      const result = await saveExample(conn, sql, `[ERROR PATTERN] ${note}`);
      if (result.success) {
        setSavedIdxs((prev) => new Set(prev).add(key));
      } else {
        throw new Error(result.error || "Failed to save");
      }
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <Card className="bg-gray-900 border-gray-800 col-span-2">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          SQL Patterns
          {repeatedQueries.length > 0 && (
            <Badge
              variant="secondary"
              className="bg-yellow-900/50 text-yellow-400"
            >
              {repeatedQueries.length} repeated
            </Badge>
          )}
          {softErrors.length > 0 && (
            <Badge
              variant="secondary"
              className="bg-amber-900/50 text-amber-400"
            >
              {softErrors.length} auto-corrected
            </Badge>
          )}
          {hardErrors.length > 0 && (
            <Badge variant="secondary" className="bg-red-900/50 text-red-400">
              {hardErrors.length} error{hardErrors.length !== 1 ? "s" : ""}
            </Badge>
          )}
        </CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          Repeated queries and auto-corrected errors &mdash; expand to see full
          SQL and save as knowledge
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {/* Repeated queries */}
        {repeatedQueries.length > 0 && (
          <>
            {(softErrors.length > 0 || hardErrors.length > 0) && (
              <p className="text-gray-600 text-[10px] uppercase tracking-wider pt-1">
                Repeated Queries
              </p>
            )}
            {repeatedQueries.map((q, i) => {
              const key = `rq-${i}`;
              const isSaved = q.is_example || savedIdxs.has(key);
              return (
                <SqlPatternRow
                  key={key}
                  borderColor="gray-800"
                  badges={[
                    {
                      text: `${q.count}x`,
                      className: "bg-yellow-900/50 text-yellow-400",
                    },
                  ]}
                  sqlPreview={q.sql_preview}
                  fullSql={q.full_sql || q.sql_preview}
                  meta={`First: ${formatTimestamp(q.first_seen)}  Last: ${formatTimestamp(q.last_seen)}`}
                  isSaved={isSaved}
                  actionLabel="Save as Example"
                  suggestedNote={q.suggested_intent || ""}
                  placeholder={
                    q.suggested_intent
                      ? `e.g. ${q.suggested_intent}`
                      : "Describe the intent (e.g. Show top users by session count)"
                  }
                  onSave={(note) =>
                    handleSaveExample(key, q.full_sql || q.sql_preview, note)
                  }
                  saving={savingKey === key}
                />
              );
            })}
          </>
        )}

        {/* Auto-corrected errors */}
        {softErrors.length > 0 && (
          <>
            {repeatedQueries.length > 0 && (
              <p className="text-gray-600 text-[10px] uppercase tracking-wider pt-2">
                Auto-corrected Errors
              </p>
            )}
            {softErrors.slice(0, 10).map((e, i) => {
              const key = `soft-${i}`;
              const isSaved = e.is_saved || savedIdxs.has(key);
              const hasSql = !!e.sql;
              if (!hasSql) {
                return (
                  <div
                    key={key}
                    className="border border-amber-900/30 rounded p-2 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-amber-400 font-mono">
                        {e.tool || e.span_name}
                      </span>
                      <Badge
                        variant="secondary"
                        className="bg-amber-900/30 text-amber-500 text-[10px]"
                      >
                        auto-corrected
                      </Badge>
                      <span className="text-gray-600 text-[10px] ml-auto">
                        {formatTimestamp(e.timestamp)}
                      </span>
                    </div>
                    {e.error && (
                      <p className="text-gray-500 mt-0.5 truncate">{e.error}</p>
                    )}
                  </div>
                );
              }
              return (
                <SqlPatternRow
                  key={key}
                  borderColor="amber-900/30"
                  label={e.tool || e.span_name}
                  badges={[
                    {
                      text: "auto-corrected",
                      className: "bg-amber-900/30 text-amber-500",
                    },
                  ]}
                  sqlPreview={e.sql!.split("\n")[0].slice(0, 100)}
                  fullSql={e.sql!}
                  meta={formatTimestamp(e.timestamp)}
                  error={e.error}
                  isSaved={isSaved}
                  actionLabel="Save as Learning"
                  suggestedNote={suggestLearningNote(e.error || "")}
                  placeholder="What should the agent avoid? (e.g. Don't use schema X)"
                  onSave={(note) => handleSaveLearning(key, e.sql!, note)}
                  saving={savingKey === key}
                />
              );
            })}
          </>
        )}

        {/* Hard errors (no SQL, non-expandable) */}
        {hardErrors.length > 0 && (
          <>
            {(repeatedQueries.length > 0 || softErrors.length > 0) && (
              <p className="text-gray-600 text-[10px] uppercase tracking-wider pt-2">
                Hard Errors
              </p>
            )}
            {hardErrors.slice(0, 5).map((e, i) => (
              <div
                key={`err-${i}`}
                className="border border-red-900/30 rounded p-2 text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className="text-red-400 font-mono">
                    {e.tool || e.span_name}
                  </span>
                  <span className="text-gray-600 text-[10px] ml-auto">
                    {formatTimestamp(e.timestamp)}
                  </span>
                </div>
                {e.error && (
                  <p className="text-gray-500 mt-0.5 truncate">{e.error}</p>
                )}
              </div>
            ))}
          </>
        )}

        {/* Validation failures (non-expandable) */}
        {validationFailureCount > 0 && (
          <>
            <p className="text-gray-600 text-[10px] uppercase tracking-wider pt-2">
              Validation Failures
            </p>
            {validationFailures.slice(0, 5).map((v, i) => (
              <div
                key={`val-${i}`}
                className="border border-yellow-900/30 rounded p-2 text-xs"
              >
                <code className="text-yellow-400 font-mono block truncate">
                  {v.sql_preview || "SQL validation failed"}
                </code>
                {v.error_message && (
                  <p className="text-gray-500 mt-0.5 truncate">
                    {v.error_message}
                  </p>
                )}
                {v.rejected_keyword && (
                  <span className="text-yellow-600">
                    Rejected: {v.rejected_keyword}
                  </span>
                )}
              </div>
            ))}
          </>
        )}
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

  // Classify events
  const errorPatterns = events.filter(
    (e) => e.intent && e.intent.startsWith("[ERROR PATTERN]"),
  );
  const examples = events.filter(
    (e) => !e.intent || !e.intent.startsWith("[ERROR PATTERN]"),
  );

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
          {errorPatterns.length > 0 && examples.length > 0 && (
            <p className="text-gray-600 text-[10px] uppercase tracking-wider">
              Error Patterns Learned
            </p>
          )}
          {errorPatterns.slice(0, 8).map((e, i) => (
            <div
              key={`ep-${i}`}
              className="flex items-start gap-2 text-xs px-1 py-0.5"
            >
              <span className="text-amber-500 shrink-0 mt-0.5">!</span>
              <span className="text-gray-400 truncate flex-1">
                {e.intent!.replace("[ERROR PATTERN] ", "")}
              </span>
              <span className="text-gray-600 shrink-0">
                {formatTimestamp(e.timestamp)}
              </span>
            </div>
          ))}
          {examples.length > 0 && errorPatterns.length > 0 && (
            <p className="text-gray-600 text-[10px] uppercase tracking-wider pt-1">
              Examples Saved
            </p>
          )}
          {examples.slice(0, 8).map((e, i) => (
            <div
              key={`ex-${i}`}
              className="flex items-start gap-2 text-xs px-1 py-0.5"
            >
              <span className="text-green-500 shrink-0 mt-0.5">{"\u2713"}</span>
              <span className="text-gray-400 truncate flex-1">
                {e.intent || e.tool}
              </span>
              <span className="text-gray-600 shrink-0">
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
          {/* Knowledge Flow Banner */}
          {analysis.insights && (
            <KnowledgeFlowBanner
              insights={analysis.insights}
              traceCount={analysis.traceCount}
            />
          )}

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

          {/* Semantic Layer + Tool Usage */}
          <div className="grid grid-cols-2 gap-4">
            <SemanticLayerCard status={analysis.knowledgeStatus} />
            <ToolUsageCard usage={analysis.toolUsage} />
          </div>

          {/* Vocabulary gaps — unmapped business terms */}
          {analysis.vocabularyGaps && analysis.vocabularyGaps.length > 0 && (
            <VocabularyGapsCard gaps={analysis.vocabularyGaps} />
          )}

          {/* SQL Patterns + Knowledge Capture + Tables */}
          <SqlPatternsCard
            repeatedQueries={analysis.repeatedQueries}
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
