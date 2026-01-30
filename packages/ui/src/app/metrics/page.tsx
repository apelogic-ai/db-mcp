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
  type DimensionCandidateResult,
} from "@/lib/bicp";

// =============================================================================
// Helpers
// =============================================================================

const DIM_TYPE_COLORS: Record<string, string> = {
  temporal: "bg-blue-900/50 text-blue-300",
  categorical: "bg-purple-900/50 text-purple-300",
  geographic: "bg-green-900/50 text-green-300",
  entity: "bg-orange-900/50 text-orange-300",
};

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70
      ? "bg-green-900/50 text-green-300"
      : pct >= 40
        ? "bg-yellow-900/50 text-yellow-300"
        : "bg-red-900/50 text-red-300";
  return <Badge className={color}>{pct}%</Badge>;
}

function SourceBadge({ source }: { source: string }) {
  const colors: Record<string, string> = {
    examples: "bg-blue-900/50 text-blue-300",
    rules: "bg-purple-900/50 text-purple-300",
    schema: "bg-gray-700 text-gray-300",
  };
  return (
    <Badge className={colors[source] || "bg-gray-700 text-gray-300"}>
      {source}
    </Badge>
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
}: {
  initial?: MetricDefinition;
  onSave: (data: MetricDefinition) => void;
  onCancel: () => void;
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

  const handleSubmit = () => {
    onSave({
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
  };

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
        <label className="text-xs text-gray-400 block mb-1">SQL *</label>
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
      <div className="flex justify-end gap-2 pt-2">
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200"
        >
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={!name.trim() || !description.trim() || !sql.trim()}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {initial ? "Update" : "Add"} Metric
        </button>
      </div>
    </div>
  );
}

function DimensionForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: DimensionDefinition;
  onSave: (data: DimensionDefinition) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name || "");
  const [displayName, setDisplayName] = useState(initial?.display_name || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [dimType, setDimType] = useState(initial?.type || "categorical");
  const [column, setColumn] = useState(initial?.column || "");
  const [tables, setTables] = useState(initial?.tables?.join(", ") || "");
  const [values, setValues] = useState(initial?.values?.join(", ") || "");
  const [synonyms, setSynonyms] = useState(initial?.synonyms?.join(", ") || "");

  const handleSubmit = () => {
    onSave({
      name: name.trim().toLowerCase().replace(/\s+/g, "_"),
      display_name: displayName.trim() || undefined,
      description: description.trim(),
      type: dimType as DimensionDefinition["type"],
      column: column.trim(),
      tables: tables
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      values: values
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean),
      synonyms: synonyms
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    });
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-400 block mb-1">Name *</label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. carrier"
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
            placeholder="e.g. Carrier"
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-400 block mb-1">Type *</label>
          <select
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={dimType}
            onChange={(e) =>
              setDimType(e.target.value as DimensionDefinition["type"])
            }
          >
            <option value="categorical">Categorical</option>
            <option value="temporal">Temporal</option>
            <option value="geographic">Geographic</option>
            <option value="entity">Entity</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">Column *</label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={column}
            onChange={(e) => setColumn(e.target.value)}
            placeholder="e.g. cdr_agg_day.carrier"
          />
        </div>
      </div>
      <div>
        <label className="text-xs text-gray-400 block mb-1">Description</label>
        <textarea
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100 h-16"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-xs text-gray-400 block mb-1">Tables</label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={tables}
            onChange={(e) => setTables(e.target.value)}
          />
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">
            Known Values
          </label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={values}
            onChange={(e) => setValues(e.target.value)}
            placeholder="tmo, helium_mobile"
          />
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">Synonyms</label>
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100"
            value={synonyms}
            onChange={(e) => setSynonyms(e.target.value)}
          />
        </div>
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200"
        >
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={!name.trim() || !column.trim()}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {initial ? "Update" : "Add"} Dimension
        </button>
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
  const [showAddDimension, setShowAddDimension] = useState(false);
  const [editingMetric, setEditingMetric] = useState<MetricDefinition | null>(
    null,
  );
  const [editingDimension, setEditingDimension] =
    useState<DimensionDefinition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null);

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

  const handleAddDimension = async (data: DimensionDefinition) => {
    setError(null);
    const result = await addMetricOrDimension(
      connection,
      "dimension",
      data as unknown as Record<string, unknown>,
    );
    if (result.success) {
      setShowAddDimension(false);
      onRefresh();
    } else {
      setError(result.error || "Failed to add dimension");
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

  const handleUpdateDimension = async (data: DimensionDefinition) => {
    if (!editingDimension) return;
    setError(null);
    const result = await updateMetricOrDimension(
      connection,
      "dimension",
      editingDimension.name,
      data as unknown as Record<string, unknown>,
    );
    if (result.success) {
      setEditingDimension(null);
      onRefresh();
    } else {
      setError(result.error || "Failed to update dimension");
    }
  };

  const handleDeleteMetric = async (name: string) => {
    const result = await deleteMetricOrDimension(connection, "metric", name);
    if (result.success) onRefresh();
  };

  const handleDeleteDimension = async (name: string) => {
    const result = await deleteMetricOrDimension(connection, "dimension", name);
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
                initial={editingMetric}
                onSave={handleUpdateMetric}
                onCancel={() => setEditingMetric(null)}
              />
            </div>
          )}

          {metrics.length === 0 && !showAddMetric ? (
            <p className="text-sm text-gray-500">
              No metrics defined yet. Add one manually or mine the vault for
              candidates.
            </p>
          ) : (
            <div className="space-y-2">
              {metrics.map((m) => (
                <div
                  key={m.name}
                  className="bg-gray-800/50 rounded-lg border border-gray-700/50"
                >
                  <div
                    className="flex items-start justify-between p-3 cursor-pointer"
                    onClick={() =>
                      setExpandedMetric(
                        expandedMetric === m.name ? null : m.name,
                      )
                    }
                  >
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
                      <span className="text-gray-600 text-xs">
                        {expandedMetric === m.name ? "▲" : "▼"}
                      </span>
                    </div>
                  </div>

                  {expandedMetric === m.name && (
                    <div className="px-3 pb-3 border-t border-gray-700/50 pt-2">
                      <pre className="text-xs text-gray-300 font-mono bg-gray-900 p-2 rounded overflow-x-auto">
                        {m.sql}
                      </pre>
                      {m.tables && m.tables.length > 0 && (
                        <div className="mt-2 text-xs text-gray-500">
                          Tables: {m.tables.join(", ")}
                        </div>
                      )}
                      {m.dimensions && m.dimensions.length > 0 && (
                        <div className="mt-1 text-xs text-gray-500">
                          Dimensions: {m.dimensions.join(", ")}
                        </div>
                      )}
                      {m.notes && (
                        <div className="mt-1 text-xs text-gray-400 italic">
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

      {/* Dimensions Section */}
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-white text-base">Dimensions</CardTitle>
              <CardDescription>
                {dimensions.length} dimension
                {dimensions.length !== 1 ? "s" : ""} defined
              </CardDescription>
            </div>
            <button
              onClick={() => setShowAddDimension(true)}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-500"
            >
              + Add Dimension
            </button>
          </div>
        </CardHeader>
        <CardContent>
          {showAddDimension && (
            <div className="mb-4 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
              <h4 className="text-sm font-medium text-white mb-3">
                New Dimension
              </h4>
              <DimensionForm
                onSave={handleAddDimension}
                onCancel={() => setShowAddDimension(false)}
              />
            </div>
          )}

          {editingDimension && (
            <div className="mb-4 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
              <h4 className="text-sm font-medium text-white mb-3">
                Edit: {editingDimension.name}
              </h4>
              <DimensionForm
                initial={editingDimension}
                onSave={handleUpdateDimension}
                onCancel={() => setEditingDimension(null)}
              />
            </div>
          )}

          {dimensions.length === 0 && !showAddDimension ? (
            <p className="text-sm text-gray-500">
              No dimensions defined yet. Add one manually or mine the vault for
              candidates.
            </p>
          ) : (
            <div className="space-y-2">
              {dimensions.map((d) => (
                <div
                  key={d.name}
                  className="flex items-start justify-between p-3 bg-gray-800/50 rounded-lg border border-gray-700/50"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white">
                        {d.display_name || d.name}
                      </span>
                      <Badge
                        className={
                          DIM_TYPE_COLORS[d.type] || "bg-gray-700 text-gray-300"
                        }
                      >
                        {d.type}
                      </Badge>
                      <span className="text-xs text-gray-500 font-mono">
                        {d.column}
                      </span>
                    </div>
                    {d.description && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        {d.description}
                      </p>
                    )}
                    {d.values && d.values.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {d.values.slice(0, 5).map((v) => (
                          <span
                            key={v}
                            className="text-[10px] px-1.5 py-0.5 bg-gray-700 text-gray-400 rounded"
                          >
                            {v}
                          </span>
                        ))}
                        {d.values.length > 5 && (
                          <span className="text-[10px] text-gray-500">
                            +{d.values.length - 5} more
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1 ml-2 shrink-0">
                    <button
                      onClick={() => setEditingDimension(d)}
                      className="px-2 py-1 text-xs text-gray-400 hover:text-blue-400"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDeleteDimension(d.name)}
                      className="px-2 py-1 text-xs text-gray-400 hover:text-red-400"
                    >
                      Delete
                    </button>
                  </div>
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
}: {
  connection: string;
  onRefresh: () => void;
}) {
  const [mining, setMining] = useState(false);
  const [mined, setMined] = useState(false);
  const [metricCandidates, setMetricCandidates] = useState<
    MetricCandidateResult[]
  >([]);
  const [dimensionCandidates, setDimensionCandidates] = useState<
    DimensionCandidateResult[]
  >([]);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState<string | null>(null);
  const [approved, setApproved] = useState<Set<string>>(new Set());
  const [rejected, setRejected] = useState<Set<string>>(new Set());
  const [typeFilters, setTypeFilters] = useState<Set<string>>(
    new Set(["temporal", "categorical", "geographic", "entity"]),
  );
  const [sourceFilters, setSourceFilters] = useState<Set<string>>(
    new Set(["examples", "rules", "schema"]),
  );
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const handleMine = async () => {
    setMining(true);
    setError(null);
    try {
      const result = await mineMetricsCandidates(connection);
      if (result.success) {
        setMetricCandidates(result.metricCandidates);
        setDimensionCandidates(result.dimensionCandidates);
        setMined(true);
      } else {
        setError(result.error || "Mining failed");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setMining(false);
    }
  };

  const handleApprove = async (
    type: "metric" | "dimension",
    data: Record<string, unknown>,
    key: string,
  ) => {
    setApproving(key);
    try {
      const result = await approveCandidate(connection, type, data);
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

  const handleReject = (key: string) => {
    setRejected((prev) => new Set(prev).add(key));
  };

  const visibleMetrics = metricCandidates.filter(
    (c) =>
      !approved.has(`m:${c.metric.name}`) &&
      !rejected.has(`m:${c.metric.name}`),
  );
  const visibleDimensions = dimensionCandidates.filter(
    (c) =>
      !approved.has(`d:${c.dimension.name}`) &&
      !rejected.has(`d:${c.dimension.name}`),
  );

  // Apply type + source filters
  const filteredDimensions = visibleDimensions.filter(
    (c) => typeFilters.has(c.dimension.type) && sourceFilters.has(c.source),
  );

  // Group by semantic category
  const groupedDimensions = new Map<string, DimensionCandidateResult[]>();
  for (const c of filteredDimensions) {
    const cat = c.category || "Other";
    const group = groupedDimensions.get(cat) || [];
    group.push(c);
    groupedDimensions.set(cat, group);
  }
  // Sort groups by size (largest first)
  const sortedGroups = [...groupedDimensions.entries()].sort(
    (a, b) => b[1].length - a[1].length,
  );

  const toggleFilter = (
    set: Set<string>,
    setter: (s: Set<string>) => void,
    value: string,
  ) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    setter(next);
  };

  const toggleGroup = (table: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(table)) next.delete(table);
      else next.add(table);
      return next;
    });
  };

  const handleBulkApprove = async (candidates: DimensionCandidateResult[]) => {
    for (const c of candidates) {
      const key = `d:${c.dimension.name}`;
      if (!approved.has(key) && !rejected.has(key)) {
        await handleApprove(
          "dimension",
          c.dimension as unknown as Record<string, unknown>,
          key,
        );
      }
    }
  };

  const handleBulkReject = (candidates: DimensionCandidateResult[]) => {
    setRejected((prev) => {
      const next = new Set(prev);
      for (const c of candidates) {
        next.add(`d:${c.dimension.name}`);
      }
      return next;
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-400">
            Mine the knowledge vault to discover metric and dimension candidates
            from training examples, business rules, and schema descriptions.
          </p>
        </div>
        <button
          onClick={handleMine}
          disabled={mining}
          className="px-4 py-2 text-sm bg-purple-600 text-white rounded hover:bg-purple-500 disabled:opacity-50 shrink-0"
        >
          {mining ? "Mining..." : "Mine Vault"}
        </button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {mined &&
        visibleMetrics.length === 0 &&
        visibleDimensions.length === 0 && (
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
          <CardContent className="space-y-2">
            {visibleMetrics.map((c) => {
              const key = `m:${c.metric.name}`;
              const isApproving = approving === key;
              return (
                <div
                  key={key}
                  className="p-3 bg-gray-800/50 rounded-lg border border-gray-700/50"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-white">
                          {c.metric.display_name || c.metric.name}
                        </span>
                        <ConfidenceBadge value={c.confidence} />
                        <SourceBadge source={c.source} />
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {c.metric.description}
                      </p>
                      {c.metric.sql && !c.metric.sql.startsWith("--") && (
                        <pre className="text-xs text-gray-500 font-mono mt-1 truncate">
                          {c.metric.sql.slice(0, 120)}
                          {c.metric.sql.length > 120 ? "..." : ""}
                        </pre>
                      )}
                      {c.evidence.length > 0 && (
                        <div className="text-[10px] text-gray-600 mt-1">
                          Evidence: {c.evidence.join(", ")}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-1 ml-2 shrink-0">
                      <button
                        onClick={() =>
                          handleApprove(
                            "metric",
                            c.metric as unknown as Record<string, unknown>,
                            key,
                          )
                        }
                        disabled={isApproving}
                        className="px-2 py-1 text-xs bg-green-700 text-green-100 rounded hover:bg-green-600 disabled:opacity-50"
                      >
                        {isApproving ? "..." : "Approve"}
                      </button>
                      <button
                        onClick={() => handleReject(key)}
                        className="px-2 py-1 text-xs text-gray-400 hover:text-red-400"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* Dimension Candidates */}
      {visibleDimensions.length > 0 && (
        <Card className="bg-gray-900 border-gray-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-base">
              Dimension Candidates ({visibleDimensions.length})
            </CardTitle>
            <CardDescription>
              Review and approve dimension definitions discovered in the vault
            </CardDescription>

            {/* Filter bar */}
            <div className="flex flex-wrap items-center gap-3 mt-3">
              <span className="text-xs text-gray-500">Type:</span>
              {(
                ["temporal", "categorical", "geographic", "entity"] as const
              ).map((t) => (
                <button
                  key={t}
                  onClick={() => toggleFilter(typeFilters, setTypeFilters, t)}
                  className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                    typeFilters.has(t)
                      ? `${DIM_TYPE_COLORS[t]} border-transparent`
                      : "border-gray-600 text-gray-500 bg-transparent"
                  }`}
                >
                  {t}
                </button>
              ))}

              <span className="text-xs text-gray-600 mx-1">|</span>

              <span className="text-xs text-gray-500">Source:</span>
              {(["examples", "rules", "schema"] as const).map((s) => {
                const sourceColors: Record<string, string> = {
                  examples: "bg-blue-900/50 text-blue-300",
                  rules: "bg-purple-900/50 text-purple-300",
                  schema: "bg-gray-700 text-gray-300",
                };
                return (
                  <button
                    key={s}
                    onClick={() =>
                      toggleFilter(sourceFilters, setSourceFilters, s)
                    }
                    className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                      sourceFilters.has(s)
                        ? `${sourceColors[s]} border-transparent`
                        : "border-gray-600 text-gray-500 bg-transparent"
                    }`}
                  >
                    {s}
                  </button>
                );
              })}

              <span className="text-xs text-gray-500 ml-auto">
                Showing {filteredDimensions.length} of{" "}
                {visibleDimensions.length}
              </span>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {sortedGroups.map(([table, candidates]) => {
              const isExpanded = expandedGroups.has(table);
              return (
                <div
                  key={table}
                  className="rounded-lg border border-gray-700/50 overflow-hidden"
                >
                  {/* Group header */}
                  <div
                    className="flex items-center justify-between px-3 py-2 bg-gray-800/80 cursor-pointer hover:bg-gray-800"
                    onClick={() => toggleGroup(table)}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500 text-xs">
                        {isExpanded ? "▼" : "▶"}
                      </span>
                      <span className="text-sm font-medium text-gray-200">
                        {table}
                      </span>
                      <span className="text-xs text-gray-500">
                        ({candidates.length})
                      </span>
                    </div>
                    <div
                      className="flex items-center gap-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        onClick={() => handleBulkApprove(candidates)}
                        className="px-2 py-0.5 text-[10px] bg-green-800/50 text-green-300 rounded hover:bg-green-700/50"
                      >
                        Approve All
                      </button>
                      <button
                        onClick={() => handleBulkReject(candidates)}
                        className="px-2 py-0.5 text-[10px] text-gray-500 hover:text-red-400"
                      >
                        Reject All
                      </button>
                    </div>
                  </div>

                  {/* Group contents */}
                  {isExpanded && (
                    <div className="space-y-1 p-2">
                      {candidates.map((c) => {
                        const key = `d:${c.dimension.name}`;
                        const isApprovingThis = approving === key;
                        return (
                          <div
                            key={key}
                            className="p-2 bg-gray-800/30 rounded border border-gray-700/30"
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm font-medium text-white">
                                    {c.dimension.display_name ||
                                      c.dimension.name}
                                  </span>
                                  <Badge
                                    className={
                                      DIM_TYPE_COLORS[c.dimension.type] ||
                                      "bg-gray-700 text-gray-300"
                                    }
                                  >
                                    {c.dimension.type}
                                  </Badge>
                                  <ConfidenceBadge value={c.confidence} />
                                  <SourceBadge source={c.source} />
                                </div>
                                {c.dimension.description && (
                                  <p className="text-xs text-gray-400 mt-0.5">
                                    {c.dimension.description}
                                  </p>
                                )}
                                <div className="flex items-center gap-2 mt-0.5">
                                  <span className="text-xs text-gray-500 font-mono">
                                    {c.dimension.column}
                                  </span>
                                  {c.dimension.tables &&
                                    c.dimension.tables.length > 0 && (
                                      <span className="text-[10px] text-gray-600">
                                        table: {c.dimension.tables.join(", ")}
                                      </span>
                                    )}
                                </div>
                              </div>
                              <div className="flex items-center gap-1 ml-2 shrink-0">
                                <button
                                  onClick={() =>
                                    handleApprove(
                                      "dimension",
                                      c.dimension as unknown as Record<
                                        string,
                                        unknown
                                      >,
                                      key,
                                    )
                                  }
                                  disabled={isApprovingThis}
                                  className="px-2 py-1 text-xs bg-green-700 text-green-100 rounded hover:bg-green-600 disabled:opacity-50"
                                >
                                  {isApprovingThis ? "..." : "Approve"}
                                </button>
                                <button
                                  onClick={() => handleReject(key)}
                                  className="px-2 py-1 text-xs text-gray-400 hover:text-red-400"
                                >
                                  Reject
                                </button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
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

  const loadData = useCallback(async () => {
    const conn = await getActiveConnection();
    setConnection(conn);
    if (!conn) {
      setLoading(false);
      return;
    }

    try {
      const result = await listMetrics(conn);
      if (result.success) {
        setMetrics(result.metrics);
        setDimensions(result.dimensions);
      } else {
        setError(result.error || "Failed to load metrics");
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Metrics & Dimensions
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Define business metrics and the dimensions they can be sliced by.
            Mine the knowledge vault to discover candidates automatically.
          </p>
        </div>
        <Badge className="bg-gray-700 text-gray-300">{connection}</Badge>
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
          Catalog ({metrics.length + dimensions.length})
        </button>
        <button
          onClick={() => setTab("candidates")}
          className={`inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all ${
            tab === "candidates"
              ? "bg-gray-800 text-white shadow"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          Candidates
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
        <CandidatesTab connection={connection} onRefresh={loadData} />
      )}
    </div>
  );
}
