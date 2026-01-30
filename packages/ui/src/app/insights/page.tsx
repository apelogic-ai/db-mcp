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

function KnowledgeFlowCard({
  insights,
  traceCount,
}: {
  insights: InsightsAnalysis["insights"];
  traceCount: number;
}) {
  const {
    generationCalls,
    callsWithExamples,
    callsWithoutExamples,
    callsWithRules,
    exampleHitRate,
    validateCalls,
    validateFailRate,
    knowledgeCapturesByType,
    sessionCount,
  } = insights;

  const captureTotal = Object.values(knowledgeCapturesByType).reduce(
    (a, b) => a + b,
    0,
  );

  // Build insight items — each is a question + answer + severity
  type Insight = {
    question: string;
    answer: string;
    severity: "good" | "warn" | "bad" | "neutral";
  };

  const items: Insight[] = [];

  // 1. Is the agent finding what it needs?
  if (generationCalls > 0) {
    if (exampleHitRate !== null && exampleHitRate >= 80) {
      items.push({
        question: "Is the agent finding what it needs?",
        answer: `Yes \u2014 ${exampleHitRate}% of generation calls had examples in context (${callsWithExamples}/${generationCalls})`,
        severity: "good",
      });
    } else if (exampleHitRate !== null && exampleHitRate > 0) {
      items.push({
        question: "Is the agent finding what it needs?",
        answer: `Partially \u2014 only ${exampleHitRate}% of generation calls had examples (${callsWithExamples}/${generationCalls}). ${callsWithoutExamples} calls had no examples.`,
        severity: "warn",
      });
    } else {
      items.push({
        question: "Is the agent finding what it needs?",
        answer: `No examples were available for any of the ${generationCalls} generation calls. Add training examples to improve accuracy.`,
        severity: "bad",
      });
    }
  }

  // 2. Is it using prior knowledge?
  if (generationCalls > 0) {
    if (callsWithRules > 0 && callsWithExamples > 0) {
      items.push({
        question: "Is it reusing prior knowledge?",
        answer: `Yes \u2014 ${callsWithRules}/${generationCalls} calls used business rules, ${callsWithExamples}/${generationCalls} used examples`,
        severity: "good",
      });
    } else if (callsWithRules > 0 || callsWithExamples > 0) {
      const missing = callsWithRules === 0 ? "business rules" : "examples";
      items.push({
        question: "Is it reusing prior knowledge?",
        answer: `Partially \u2014 no ${missing} available. Add them to improve generation.`,
        severity: "warn",
      });
    } else {
      items.push({
        question: "Is it reusing prior knowledge?",
        answer:
          "No prior knowledge used. The agent is generating SQL without examples or rules.",
        severity: "bad",
      });
    }
  }

  // 3. Are there SQL generation mistakes?
  if (validateCalls > 0) {
    if (validateFailRate !== null && validateFailRate === 0) {
      items.push({
        question: "Are there SQL mistakes?",
        answer: `No \u2014 all ${validateCalls} validations passed`,
        severity: "good",
      });
    } else if (validateFailRate !== null) {
      items.push({
        question: "Are there SQL mistakes?",
        answer: `${validateFailRate}% of validations failed (${validateCalls} total). Check errors below for patterns.`,
        severity: validateFailRate > 20 ? "bad" : "warn",
      });
    }
  }

  // 4. Are we capturing new knowledge?
  if (traceCount > 5) {
    if (captureTotal > 0) {
      const parts = Object.entries(knowledgeCapturesByType)
        .map(([type, count]) => `${count} ${type.replace("_", " ")}`)
        .join(", ");
      items.push({
        question: "Are we capturing new knowledge?",
        answer: `Yes \u2014 ${parts}`,
        severity: "good",
      });
    } else {
      items.push({
        question: "Are we capturing new knowledge?",
        answer:
          "No knowledge captured in this period. Use query_approve after successful queries to save examples.",
        severity: "warn",
      });
    }
  }

  if (items.length === 0) {
    // Not enough data yet
    items.push({
      question: "Not enough data yet",
      answer:
        generationCalls === 0
          ? "Use get_data or query_generate to start generating SQL. Insights will appear once generation traces are recorded."
          : "Keep using tools to build up trace data for analysis.",
      severity: "neutral",
    });
  }

  const severityColor = {
    good: "text-green-400",
    warn: "text-yellow-400",
    bad: "text-red-400",
    neutral: "text-gray-400",
  };

  const severityIcon = {
    good: "\u2713",
    warn: "\u26A0",
    bad: "\u2717",
    neutral: "\u2022",
  };

  return (
    <Card className="bg-gray-900 border-gray-800 col-span-2">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm">
          Knowledge Flow Insights
        </CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          Is the semantic layer helping the agent generate better SQL?
          {sessionCount > 0 && (
            <span className="ml-2 text-gray-600">
              ({sessionCount} session{sessionCount !== 1 ? "s" : ""})
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map((item, i) => (
          <div key={i} className="border border-gray-800 rounded p-3">
            <div className="flex items-start gap-2">
              <span
                className={`${severityColor[item.severity]} text-sm shrink-0 mt-0.5`}
              >
                {severityIcon[item.severity]}
              </span>
              <div>
                <p className="text-gray-300 text-sm font-medium">
                  {item.question}
                </p>
                <p className="text-gray-500 text-xs mt-0.5">{item.answer}</p>
              </div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
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
  const [savingIdx, setSavingIdx] = useState<number | null>(null);
  const [intentIdx, setIntentIdx] = useState<number | null>(null);
  const [intentText, setIntentText] = useState("");
  const [savedIdxs, setSavedIdxs] = useState<Set<number>>(new Set());
  const [saveError, setSaveError] = useState<string | null>(null);

  if (queries.length === 0) return null;

  const handleSave = async (idx: number) => {
    const q = queries[idx];
    const sql = q.full_sql || q.sql_preview;
    if (!intentText.trim()) return;

    setSavingIdx(idx);
    setSaveError(null);
    try {
      const connResult = await bicpCall<{
        connections: Array<{ name: string; isActive: boolean }>;
        activeConnection: string | null;
      }>("connections/list", {});
      const conn = connResult.activeConnection;
      if (!conn) {
        setSaveError("No active connection");
        return;
      }
      const result = await saveExample(conn, sql, intentText.trim());
      if (result.success) {
        setSavedIdxs((prev) => new Set(prev).add(idx));
        setIntentIdx(null);
        setIntentText("");
      } else {
        setSaveError(result.error || "Failed to save");
      }
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSavingIdx(null);
    }
  };

  const exampleCount = queries.filter(
    (q, i) => q.is_example || savedIdxs.has(i),
  ).length;

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
          {exampleCount > 0 && (
            <Badge
              variant="secondary"
              className="bg-green-900/50 text-green-400 text-[10px]"
            >
              {exampleCount} saved
            </Badge>
          )}
        </CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          Same SQL executed multiple times — consider saving as training
          examples
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {queries.map((q, i) => {
          const isSaved = q.is_example || savedIdxs.has(i);
          return (
            <div key={i} className="border border-gray-800 rounded p-2">
              <code className="text-xs text-gray-300 font-mono block truncate">
                {q.sql_preview}
              </code>
              <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                <span>{q.count}x executed</span>
                <span>First: {formatTimestamp(q.first_seen)}</span>
                <span>Last: {formatTimestamp(q.last_seen)}</span>
                <span className="ml-auto">
                  {isSaved ? (
                    <span className="text-green-500">✓ Saved</span>
                  ) : intentIdx === i ? null : (
                    <button
                      onClick={() => {
                        setIntentIdx(i);
                        setIntentText("");
                        setSaveError(null);
                      }}
                      className="text-blue-400 hover:text-blue-300 transition-colors"
                    >
                      Save as Example
                    </button>
                  )}
                </span>
              </div>
              {intentIdx === i && !isSaved && (
                <div className="mt-2 flex gap-2">
                  <input
                    type="text"
                    value={intentText}
                    onChange={(e) => setIntentText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSave(i);
                      if (e.key === "Escape") {
                        setIntentIdx(null);
                        setIntentText("");
                      }
                    }}
                    placeholder={
                      q.suggested_intent
                        ? `e.g. ${q.suggested_intent}`
                        : "Describe the intent (e.g. Show top users by session count)"
                    }
                    className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500"
                    autoFocus
                  />
                  <button
                    onClick={() => handleSave(i)}
                    disabled={savingIdx === i || !intentText.trim()}
                    className="text-xs px-2 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded transition-colors"
                  >
                    {savingIdx === i ? "..." : "Save"}
                  </button>
                  <button
                    onClick={() => {
                      setIntentIdx(null);
                      setIntentText("");
                    }}
                    className="text-xs px-2 py-1 text-gray-400 hover:text-gray-300 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              )}
              {saveError && intentIdx === i && (
                <p className="text-red-400 text-xs mt-1">{saveError}</p>
              )}
            </div>
          );
        })}
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

  const hardErrors = errors.filter((e) => e.error_type !== "soft");
  const softErrors = errors.filter((e) => e.error_type === "soft");

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          Errors &amp; Failures
          {hardErrors.length > 0 && (
            <Badge variant="secondary" className="bg-red-900/50 text-red-400">
              {hardErrors.length} error{hardErrors.length !== 1 ? "s" : ""}
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
          {validationFailureCount > 0 && (
            <Badge
              variant="secondary"
              className="bg-yellow-900/50 text-yellow-400"
            >
              {validationFailureCount} validation
            </Badge>
          )}
        </CardTitle>
        <CardDescription className="text-gray-500 text-xs">
          Tool failures, auto-corrected errors, and SQL validation issues
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {hardErrors.slice(0, 5).map((e, i) => (
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
        {softErrors.slice(0, 5).map((e, i) => (
          <div
            key={`soft-${i}`}
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
            </div>
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
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
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
        <CardContent className="space-y-1">
          {events.slice(0, 8).map((e, i) => {
            const hasDetails = !!(e.intent || e.filename);
            const showBadge = e.feedback_type && e.feedback_type !== e.tool;
            return (
              <div key={i}>
                <button
                  onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                  className="flex items-center gap-2 text-xs w-full text-left hover:bg-gray-800/50 rounded px-1 py-0.5 transition-colors"
                >
                  <span className="text-green-500">✓</span>
                  <span className="text-gray-300 font-mono">{e.tool}</span>
                  {showBadge && (
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
                  <span className="text-gray-600 text-[10px]">
                    {expandedIdx === i ? "▾" : "▸"}
                  </span>
                </button>
                {expandedIdx === i && (
                  <div className="ml-5 mt-1 mb-1 pl-2 border-l border-gray-700 text-xs space-y-0.5">
                    {e.intent && (
                      <p className="text-gray-400">
                        <span className="text-gray-500">Intent:</span>{" "}
                        {e.intent}
                      </p>
                    )}
                    {e.filename && (
                      <p className="text-gray-500 font-mono text-[10px]">
                        {e.filename}
                      </p>
                    )}
                    {!hasDetails && (
                      <p className="text-gray-600 italic">
                        No additional details available
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
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

          {/* Semantic Layer + Tool Usage */}
          <div className="grid grid-cols-2 gap-4">
            <SemanticLayerCard status={analysis.knowledgeStatus} />
            <ToolUsageCard usage={analysis.toolUsage} />
          </div>

          {/* Knowledge Flow Insights */}
          {analysis.insights && (
            <KnowledgeFlowCard
              insights={analysis.insights}
              traceCount={analysis.traceCount}
            />
          )}

          {/* Vocabulary gaps — unmapped business terms */}
          {analysis.vocabularyGaps && analysis.vocabularyGaps.length > 0 && (
            <VocabularyGapsCard gaps={analysis.vocabularyGaps} />
          )}

          {/* Detail grid */}
          <div className="grid grid-cols-2 gap-4">
            <RepeatedQueriesCard queries={analysis.repeatedQueries} />
            <KnowledgeCaptureCard
              events={analysis.knowledgeEvents}
              count={analysis.knowledgeCaptureCount}
              traceCount={analysis.traceCount}
            />
            <ErrorsCard
              errors={analysis.errors}
              errorCount={analysis.errorCount}
              validationFailures={analysis.validationFailures}
              validationFailureCount={analysis.validationFailureCount}
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
