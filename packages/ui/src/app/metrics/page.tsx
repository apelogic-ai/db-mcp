"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  bicpCall,
  listMetrics,
  addMetricOrDimension,
  updateMetricOrDimension,
  deleteMetricOrDimension,
  mineMetricsCandidates,
  approveCandidate,
  type MetricDefinition,
  type DimensionDefinition,
  type MetricCandidateResult,
} from "@/lib/bicp";

// =============================================================================
// Helpers
// =============================================================================

const DIM_TYPE_COLORS: Record<string, string> = {
  temporal: "bg-blue-900/50 text-blue-300",
  categorical: "bg-purple-900/50 text-purple-300",
  geographic: "bg-green-900/50 text-green-300",
  entity: "bg-brand/20 text-brand-light",
};

function TagFilter({
  tags,
  selected,
  onToggle,
}: {
  tags: string[];
  selected: Set<string>;
  onToggle: (tag: string) => void;
}) {
  if (tags.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mb-3">
      {tags.map((t) => (
        <button
          key={t}
          onClick={() => onToggle(t)}
          className={`px-2 py-0.5 text-[11px] rounded border transition-colors ${
            selected.has(t)
              ? "bg-blue-600 border-blue-500 text-white"
              : "bg-gray-800 border-gray-700 text-gray-400 hover:text-gray-200"
          }`}
        >
          {t}
        </button>
      ))}
      {selected.size > 0 && (
        <button
          onClick={() => selected.forEach((t) => onToggle(t))}
          className="px-2 py-0.5 text-[11px] text-gray-500 hover:text-gray-300"
        >
          clear
        </button>
      )}
    </div>
  );
}

async function getActiveConnection(): Promise<string | null> {
  try {
    const result = await bicpCall<{
      connections: Array<{ name: string; isActive: boolean }>;
      activeConnection: string | null;
    }>("connections/list", {});
    return result.activeConnection;
  } catch {
    return null;
  }
}

// =============================================================================
// Add/Edit Modal
// =============================================================================

function MetricForm({
  initial,
  onSave,
  onCancel,
  mode = "add",
  onUpdate,
  onReject,
}: {
  initial?: MetricDefinition;
  onSave: (data: MetricDefinition) => void;
  onCancel: () => void;
  mode?: "add" | "edit" | "candidate";
  onUpdate?: (data: MetricDefinition) => void;
  onReject?: () => void;
}) {
  const [name, setName] = useState(initial?.name || "");
  const [displayName, setDisplayName] = useState(initial?.display_name || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [sql, setSql] = useState(initial?.sql || "");
  const [tables, setTables] = useState(initial?.tables?.join(", ") || "");
  const [tags, setTags] = useState(initial?.tags?.join(", ") || "");
  const [dimensions, setDimensions] = useState(
    initial?.dimensions?.join(", ") || "",
  );
  const [notes, setNotes] = useState(initial?.notes || "");

  const buildData = (): MetricDefinition => ({
    name: name.trim().toLowerCase().replace(/\s+/g, "_"),
    display_name: displayName.trim() || undefined,
    description: description.trim(),
    sql: sql.trim(),
    tables: tables
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean),
    tags: tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean),
    dimensions: dimensions
      .split(",")
      .map((d) => d.trim())
      .filter(Boolean),
    notes: notes.trim() || undefined,
  });

  // Track dirty state for candidate mode
  const isDirty =
    mode === "candidate" &&
    initial &&
    (name !== (initial.name || "") ||
      displayName !== (initial.display_name || "") ||
      description !== (initial.description || "") ||
      sql !== (initial.sql || "") ||
      tables !== (initial.tables?.join(", ") || "") ||
      tags !== (initial.tags?.join(", ") || "") ||
      dimensions !== (initial.dimensions?.join(", ") || "") ||
      notes !== (initial.notes || ""));

  const baseValid = !!name.trim() && !!description.trim();
  const fullValid = baseValid && !!sql.trim();

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-400 block mb-1">Name *</label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. daily_active_users"
          />
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">
            Display Name
          </label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="e.g. Daily Active Users"
          />
        </div>
      </div>
      <div>
        <label className="text-xs text-gray-400 block mb-1">
          Description *
        </label>
        <textarea
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100 h-16"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What this metric measures"
        />
      </div>
      <div>
        <label className="text-xs text-gray-400 block mb-1">
          SQL{mode === "add" ? " *" : ""}
        </label>
        <textarea
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100 font-mono h-24"
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          placeholder="SELECT COUNT(DISTINCT user_id) FROM ..."
        />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-xs text-gray-400 block mb-1">
            Tables (comma-sep)
          </label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={tables}
            onChange={(e) => setTables(e.target.value)}
          />
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">
            Tags (comma-sep)
          </label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">
            Dimensions (comma-sep)
          </label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={dimensions}
            onChange={(e) => setDimensions(e.target.value)}
          />
        </div>
      </div>
      <div>
        <label className="text-xs text-gray-400 block mb-1">Notes</label>
        <input
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>
      <div className="flex items-center pt-2">
        {onReject && (
          <button
            onClick={onReject}
            className="px-3 py-1.5 text-xs text-gray-400 hover:text-red-400"
          >
            Reject
          </button>
        )}
        <div className="flex-1" />
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200"
          >
            Cancel
          </button>
          {mode === "candidate" ? (
            <>
              {isDirty && onUpdate && (
                <button
                  onClick={() => onUpdate(buildData())}
                  disabled={!baseValid}
                  className="px-3 py-1.5 text-sm text-white rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Update
                </button>
              )}
              <button
                onClick={() => onSave(buildData())}
                disabled={!baseValid}
                className="px-3 py-1.5 text-sm text-white rounded bg-brand hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isDirty ? "Update & Approve" : "Approve"}
              </button>
            </>
          ) : (
            <button
              onClick={() => onSave(buildData())}
              disabled={mode === "add" ? !fullValid : !baseValid}
              className="px-3 py-1.5 text-sm text-white rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {mode === "edit" ? "Update Metric" : "Add Metric"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Catalog Tab
// =============================================================================

function CatalogTab({
  metrics,
  dimensions,
  connection,
  onRefresh,
}: {
  metrics: MetricDefinition[];
  dimensions: DimensionDefinition[];
  connection: string;
  onRefresh: () => void;
}) {
  const [showAddMetric, setShowAddMetric] = useState(false);
  const [editingMetric, setEditingMetric] = useState<MetricDefinition | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());

  // Build dimension lookup for inline display
  const dimensionMap = new Map(dimensions.map((d) => [d.name, d]));

  // Collect all unique tags and filter metrics
  const allTags = [...new Set(metrics.flatMap((m) => m.tags || []))].sort();
  const filteredMetrics =
    selectedTags.size === 0
      ? metrics
      : metrics.filter((m) => m.tags?.some((t) => selectedTags.has(t)));

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  };

  const handleAddMetric = async (data: MetricDefinition) => {
    setError(null);
    const result = await addMetricOrDimension(
      connection,
      "metric",
      data as unknown as Record<string, unknown>,
    );
    if (result.success) {
      setShowAddMetric(false);
      onRefresh();
    } else {
      setError(result.error || "Failed to add metric");
    }
  };

  const handleUpdateMetric = async (data: MetricDefinition) => {
    if (!editingMetric) return;
    setError(null);
    const result = await updateMetricOrDimension(
      connection,
      "metric",
      editingMetric.name,
      data as unknown as Record<string, unknown>,
    );
    if (result.success) {
      setEditingMetric(null);
      onRefresh();
    } else {
      setError(result.error || "Failed to update metric");
    }
  };

  const handleDeleteMetric = async (name: string) => {
    const result = await deleteMetricOrDimension(connection, "metric", name);
    if (result.success) onRefresh();
  };

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Metrics Section */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-white text-base">Metrics</CardTitle>
              <CardDescription>
                {metrics.length} metric{metrics.length !== 1 ? "s" : ""} defined
              </CardDescription>
            </div>
            <button
              onClick={() => setShowAddMetric(true)}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-500"
            >
              + Add Metric
            </button>
          </div>
        </CardHeader>
        <CardContent>
          {showAddMetric && (
            <div className="mb-4 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
              <h4 className="text-sm font-medium text-white mb-3">
                New Metric
              </h4>
              <MetricForm
                onSave={handleAddMetric}
                onCancel={() => setShowAddMetric(false)}
              />
            </div>
          )}

          {editingMetric && (
            <div className="mb-4 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
              <h4 className="text-sm font-medium text-white mb-3">
                Edit: {editingMetric.name}
              </h4>
              <MetricForm
                key={editingMetric.name}
                initial={editingMetric}
                mode="edit"
                onSave={handleUpdateMetric}
                onCancel={() => setEditingMetric(null)}
              />
            </div>
          )}

          <TagFilter
            tags={allTags}
            selected={selectedTags}
            onToggle={toggleTag}
          />

          {filteredMetrics.length === 0 && !showAddMetric ? (
            <p className="text-sm text-gray-500">
              {metrics.length === 0
                ? "No metrics defined yet. Add one manually or mine the vault for candidates."
                : "No metrics match the selected tags."}
            </p>
          ) : (
            <div className="space-y-2">
              {filteredMetrics.map((m) => (
                <div
                  key={m.name}
                  className="bg-gray-800/50 rounded-lg border border-gray-700/50"
                >
                  <div
                    className="flex items-start gap-2 p-3 cursor-pointer"
                    onClick={() =>
                      setExpandedMetric(
                        expandedMetric === m.name ? null : m.name,
                      )
                    }
                  >
                    <span className="text-gray-500 text-xs mt-1 shrink-0">
                      {expandedMetric === m.name ? "▼" : "▶"}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-white">
                          {m.display_name || m.name}
                        </span>
                        <span className="text-xs text-gray-500 font-mono">
                          {m.name}
                        </span>
                        {m.tags?.map((t) => (
                          <Badge
                            key={t}
                            className="bg-gray-700 text-gray-300 text-[10px]"
                          >
                            {t}
                          </Badge>
                        ))}
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5 truncate">
                        {m.description}
                      </p>
                    </div>
                    <div className="flex items-center gap-1 ml-2 shrink-0">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingMetric(m);
                        }}
                        className="px-2 py-1 text-xs text-gray-400 hover:text-blue-400"
                      >
                        Edit
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteMetric(m.name);
                        }}
                        className="px-2 py-1 text-xs text-gray-400 hover:text-red-400"
                      >
                        Delete
                      </button>
                    </div>
                  </div>

                  {expandedMetric === m.name && (
                    <div className="px-3 pb-3 border-t border-gray-700/50 pt-2 ml-5 space-y-2">
                      <p className="text-xs text-gray-300">{m.description}</p>
                      {m.sql && (
                        <pre className="text-xs text-gray-300 font-mono bg-gray-900 p-2 rounded overflow-x-auto">
                          {m.sql}
                        </pre>
                      )}
                      {m.tables && m.tables.length > 0 && (
                        <div className="text-xs text-gray-500">
                          Tables: {m.tables.join(", ")}
                        </div>
                      )}
                      {m.dimensions && m.dimensions.length > 0 && (
                        <div className="space-y-1">
                          <div className="text-xs text-gray-500">
                            Dimensions:
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {m.dimensions.map((dName) => {
                              const dim = dimensionMap.get(dName);
                              return (
                                <div
                                  key={dName}
                                  className="flex items-center gap-1.5 px-2 py-1 bg-gray-900 rounded border border-gray-700/50"
                                >
                                  <span className="text-xs text-white">
                                    {dName}
                                  </span>
                                  {dim && (
                                    <Badge
                                      className={`text-[10px] ${DIM_TYPE_COLORS[dim.type] || "bg-gray-700 text-gray-300"}`}
                                    >
                                      {dim.type}
                                    </Badge>
                                  )}
                                  {dim?.column && (
                                    <span className="text-[10px] text-gray-500 font-mono">
                                      {dim.column}
                                    </span>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      {m.notes && (
                        <div className="text-xs text-gray-400 italic">
                          {m.notes}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// =============================================================================
// Candidates Tab
// =============================================================================

function CandidatesTab({
  connection,
  onRefresh,
  onCandidateCount,
}: {
  connection: string;
  onRefresh: () => void;
  onCandidateCount?: (count: number) => void;
}) {
  const [mining, setMining] = useState(false);
  const [mined, setMined] = useState(false);
  const [metricCandidates, setMetricCandidates] = useState<
    MetricCandidateResult[]
  >([]);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState<string | null>(null);
  const [approved, setApproved] = useState<Set<string>>(new Set());
  const [rejected, setRejected] = useState<Set<string>>(new Set());
  const [editingCandidate, setEditingCandidate] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  };

  const handleMine = useCallback(async () => {
    setMining(true);
    setError(null);
    try {
      const result = await mineMetricsCandidates(connection);
      if (result.success) {
        setMetricCandidates(result.metricCandidates);
        setMined(true);
        onCandidateCount?.(result.metricCandidates.length);
      } else {
        setError(result.error || "Mining failed");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setMining(false);
    }
  }, [connection, onCandidateCount]);

  // Auto-load candidates (mined + persisted) on mount
  useEffect(() => {
    handleMine();
  }, [handleMine]);

  const handleApprove = async (data: Record<string, unknown>, key: string) => {
    setApproving(key);
    try {
      const result = await approveCandidate(connection, "metric", data);
      if (result.success) {
        setApproved((prev) => new Set(prev).add(key));
        onRefresh();
      } else {
        setError(result.error || "Approve failed");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setApproving(null);
    }
  };

  const handleUpdate = async (data: Record<string, unknown>, name: string) => {
    setError(null);
    try {
      const result = await updateMetricOrDimension(connection, "metric", name, {
        ...data,
        status: "candidate",
      });
      if (result.success) {
        // Update local state with new data
        setMetricCandidates((prev) =>
          prev.map((c) =>
            c.metric.name === name
              ? {
                  ...c,
                  metric: {
                    ...c.metric,
                    ...(data as Partial<MetricDefinition>),
                  },
                }
              : c,
          ),
        );
        setEditingCandidate(null);
      } else {
        setError(result.error || "Update failed");
      }
    } catch (e) {
      setError(String(e));
    }
  };

  const handleReject = (key: string) => {
    setRejected((prev) => new Set(prev).add(key));
  };

  const visibleMetrics = metricCandidates.filter(
    (c) =>
      !approved.has(`m:${c.metric.name}`) &&
      !rejected.has(`m:${c.metric.name}`),
  );

  const allCandidateTags = [
    ...new Set(visibleMetrics.flatMap((c) => c.metric.tags || [])),
  ].sort();
  const filteredCandidates =
    selectedTags.size === 0
      ? visibleMetrics
      : visibleMetrics.filter((c) =>
          c.metric.tags?.some((t) => selectedTags.has(t)),
        );

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {mined && visibleMetrics.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          <p className="text-sm">
            No new candidates found. All candidates have been approved or
            rejected, or the vault has no material to mine.
          </p>
        </div>
      )}

      {/* Metric Candidates */}
      {visibleMetrics.length > 0 && (
        <Card className="bg-gray-900 border-gray-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-base">
              Metric Candidates ({visibleMetrics.length})
            </CardTitle>
            <CardDescription>
              Review and approve metric definitions discovered in the vault
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TagFilter
              tags={allCandidateTags}
              selected={selectedTags}
              onToggle={toggleTag}
            />
            <div className="space-y-2">
              {filteredCandidates.map((c) => {
                const key = `m:${c.metric.name}`;
                const isApproving = approving === key;
                const isEditing = editingCandidate === c.metric.name;
                return (
                  <div
                    key={key}
                    className="bg-gray-800/50 rounded-lg border border-gray-700/50"
                  >
                    <div
                      className="flex items-start gap-2 p-3 cursor-pointer"
                      onClick={() =>
                        setEditingCandidate(isEditing ? null : c.metric.name)
                      }
                    >
                      <span className="text-gray-500 text-xs mt-1 shrink-0">
                        {isEditing ? "▼" : "▶"}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-white">
                            {c.metric.display_name || c.metric.name}
                          </span>
                          {c.metric.tags?.map((t) => (
                            <Badge
                              key={t}
                              className="bg-gray-700 text-gray-300 text-[10px]"
                            >
                              {t}
                            </Badge>
                          ))}
                        </div>
                        <p className="text-xs text-gray-400 mt-0.5 truncate">
                          {c.metric.description}
                        </p>
                      </div>
                      <div className="flex items-center gap-1 ml-2 shrink-0">
                        {!isEditing && (
                          <>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleApprove(
                                  c.metric as unknown as Record<
                                    string,
                                    unknown
                                  >,
                                  key,
                                );
                              }}
                              disabled={isApproving}
                              className="px-2 py-1 text-xs bg-brand text-white rounded hover:bg-brand-dark disabled:opacity-50"
                            >
                              {isApproving ? "..." : "Approve"}
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleReject(key);
                              }}
                              className="px-2 py-1 text-xs text-gray-400 hover:text-red-400"
                            >
                              Reject
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    {isEditing && (
                      <div className="px-3 pb-3 border-t border-gray-700/50 pt-2 ml-5">
                        {c.evidence.length > 0 && (
                          <div className="text-[10px] text-gray-500 mb-3">
                            Evidence: {c.evidence.join(", ")}
                          </div>
                        )}
                        <MetricForm
                          key={c.metric.name}
                          initial={c.metric}
                          mode="candidate"
                          onSave={(data) => {
                            handleApprove(
                              data as unknown as Record<string, unknown>,
                              key,
                            );
                          }}
                          onUpdate={(data) => {
                            handleUpdate(
                              data as unknown as Record<string, unknown>,
                              c.metric.name,
                            );
                          }}
                          onCancel={() => setEditingCandidate(null)}
                          onReject={() => {
                            handleReject(key);
                            setEditingCandidate(null);
                          }}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// =============================================================================
// Main Page
// =============================================================================

export default function MetricsPage() {
  const [tab, setTab] = useState<"catalog" | "candidates">("catalog");
  const [loading, setLoading] = useState(true);
  const [connection, setConnection] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<MetricDefinition[]>([]);
  const [dimensions, setDimensions] = useState<DimensionDefinition[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [candidateCount, setCandidateCount] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    const conn = await getActiveConnection();
    setConnection(conn);
    if (!conn) {
      setLoading(false);
      return;
    }

    try {
      const [result, candidates] = await Promise.all([
        listMetrics(conn),
        mineMetricsCandidates(conn).catch(() => null),
      ]);
      if (result.success) {
        setMetrics(result.metrics);
        setDimensions(result.dimensions);
      } else {
        setError(result.error || "Failed to load metrics");
      }
      if (candidates?.success) {
        setCandidateCount(candidates.metricCandidates.length);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-400">Loading metrics...</p>
      </div>
    );
  }

  if (!connection) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-400">
          No active connection. Create or select a connection first.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Metrics</h1>
        <p className="text-sm text-gray-400 mt-1">
          Define business metrics with their dimensions. Mine the knowledge
          vault to discover candidates automatically.
        </p>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="inline-flex h-9 items-center justify-center rounded-lg bg-gray-900 p-1 text-gray-400">
        <button
          onClick={() => setTab("catalog")}
          className={`inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all ${
            tab === "catalog"
              ? "bg-gray-800 text-white shadow"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          Catalog ({metrics.length})
        </button>
        <button
          onClick={() => setTab("candidates")}
          className={`inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all ${
            tab === "candidates"
              ? "bg-gray-800 text-white shadow"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          Candidates{candidateCount !== null ? ` (${candidateCount})` : ""}
        </button>
      </div>

      {tab === "catalog" ? (
        <CatalogTab
          metrics={metrics}
          dimensions={dimensions}
          connection={connection}
          onRefresh={loadData}
        />
      ) : (
        <CandidatesTab
          connection={connection}
          onRefresh={loadData}
          onCandidateCount={setCandidateCount}
        />
      )}
    </div>
  );
}
