import type { InsightsAnalysis } from "@/lib/bicp";
import type { ActionQueueItem } from "@/lib/ui-types";

export interface DashboardSummary {
  setup: {
    hasConnection: boolean;
    activeConnection: string | null;
    hasSchema: boolean;
    hasDomain: boolean;
  };
  semantic: {
    score: number;
    maxScore: number;
    examples: number;
    rules: number;
    metrics: number;
  };
  queue: ActionQueueItem[];
  openItems: number;
  recent: {
    traces: number;
    errors: number;
    validationFailures: number;
    totalDurationMs: number;
    knowledgeCaptured?: number;
  };
}

export interface DashboardSummaryEndpointResult {
  setup?: {
    hasConnection?: boolean;
    activeConnection?: string | null;
    hasSchema?: boolean;
    hasDomain?: boolean;
  };
  semantic?: {
    score?: number;
    maxScore?: number;
    examples?: number;
    rules?: number;
    metrics?: number;
    hasSchema?: boolean;
    hasDomain?: boolean;
  };
  queue?: {
    openItems?: number;
    items?: ActionQueueItem[];
  };
  recent?: {
    traces?: number;
    errors?: number;
    validationFailures?: number;
    totalDurationMs?: number;
    knowledgeCaptured?: number;
  };
}

export function normalizeDashboardSummary(
  data: DashboardSummaryEndpointResult,
  activeConnection: string | null,
): DashboardSummary {
  return {
    setup: {
      hasConnection: data.setup?.hasConnection ?? Boolean(activeConnection),
      activeConnection: data.setup?.activeConnection ?? activeConnection,
      hasSchema: data.setup?.hasSchema ?? false,
      hasDomain: data.setup?.hasDomain ?? false,
    },
    semantic: {
      score: data.semantic?.score ?? 0,
      maxScore: data.semantic?.maxScore ?? 5,
      examples: data.semantic?.examples ?? 0,
      rules: data.semantic?.rules ?? 0,
      metrics: data.semantic?.metrics ?? 0,
    },
    queue: data.queue?.items ?? [],
    openItems: data.queue?.openItems ?? (data.queue?.items?.length ?? 0),
    recent: {
      traces: data.recent?.traces ?? 0,
      errors: data.recent?.errors ?? 0,
      validationFailures: data.recent?.validationFailures ?? 0,
      totalDurationMs: data.recent?.totalDurationMs ?? 0,
      knowledgeCaptured: data.recent?.knowledgeCaptured ?? 0,
    },
  };
}

export function buildActionQueue(analysis: InsightsAnalysis): ActionQueueItem[] {
  const queue: ActionQueueItem[] = [];

  const openVocabularyGaps = (analysis.vocabularyGaps || []).filter(
    (gap) => (gap.status ?? "open") === "open",
  );

  if (openVocabularyGaps.length > 0) {
    queue.push({
      id: "triage-gaps",
      source: "insight",
      severity: "warn",
      title: "Resolve vocabulary gaps",
      detail: `${openVocabularyGaps.length} unmapped term group${
        openVocabularyGaps.length === 1 ? "" : "s"
      } need review`,
      ctaLabel: "Open triage",
      ctaUrl: "/insights?wizard=triage&days=7",
      status: "open",
    });
  }

  if (analysis.errorCount > 0) {
    queue.push({
      id: "trace-errors",
      source: "trace",
      severity: "critical",
      title: "Investigate query execution errors",
      detail: `${analysis.errorCount} error${analysis.errorCount === 1 ? "" : "s"} in recent traces`,
      ctaLabel: "Open traces",
      ctaUrl: "/traces",
      status: "open",
    });
  }

  if (analysis.validationFailureCount > 0) {
    queue.push({
      id: "validation-failures",
      source: "trace",
      severity: "warn",
      title: "Review validation failures",
      detail: `${analysis.validationFailureCount} blocked SQL validation event${
        analysis.validationFailureCount === 1 ? "" : "s"
      }`,
      ctaLabel: "Review insights",
      ctaUrl: "/insights?wizard=triage&days=7",
      status: "open",
    });
  }

  if (!analysis.knowledgeStatus.hasSchema || !analysis.knowledgeStatus.hasDomain) {
    queue.push({
      id: "complete-knowledge-layer",
      source: "setup",
      severity: "info",
      title: "Complete semantic layer setup",
      detail: "Schema descriptions or domain model are incomplete",
      ctaLabel: "Open setup",
      ctaUrl: "/config?wizard=onboarding",
      status: "open",
    });
  }

  if (analysis.knowledgeStatus.ruleCount === 0) {
    queue.push({
      id: "add-business-rules",
      source: "setup",
      severity: "info",
      title: "Add business rules",
      detail: "No approved business rules yet",
      ctaLabel: "Open knowledge",
      ctaUrl: "/context",
      status: "open",
    });
  }

  return queue;
}

export function buildDashboardSummary(
  analysis: InsightsAnalysis,
  activeConnection: string | null,
): DashboardSummary {
  const queue = buildActionQueue(analysis);
  const semanticScore = [
    analysis.knowledgeStatus.hasSchema,
    analysis.knowledgeStatus.hasDomain,
    analysis.knowledgeStatus.exampleCount > 0,
    analysis.knowledgeStatus.ruleCount > 0,
    analysis.knowledgeStatus.metricCount > 0,
  ].filter(Boolean).length;

  return {
    setup: {
      hasConnection: Boolean(activeConnection),
      activeConnection,
      hasSchema: analysis.knowledgeStatus.hasSchema,
      hasDomain: analysis.knowledgeStatus.hasDomain,
    },
    semantic: {
      score: semanticScore,
      maxScore: 5,
      examples: analysis.knowledgeStatus.exampleCount,
      rules: analysis.knowledgeStatus.ruleCount,
      metrics: analysis.knowledgeStatus.metricCount,
    },
    queue,
    openItems: queue.length,
    recent: {
      traces: analysis.traceCount,
      errors: analysis.errorCount,
      validationFailures: analysis.validationFailureCount,
      totalDurationMs: analysis.totalDurationMs,
      knowledgeCaptured: analysis.knowledgeCaptureCount,
    },
  };
}
