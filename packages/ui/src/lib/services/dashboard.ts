import type { InsightsAnalysis } from "@/lib/bicp";
import type { ConnectionSummary } from "@/lib/connection-context";
import type { ActionQueueItem } from "@/lib/ui-types";
import { buildConnectionAppHref, buildWizardHref, getWizardResumeStep } from "@/features/connections/utils";

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
  recent: {
    traces: number;
    errors: number;
    validationFailures: number;
    totalDurationMs: number;
  };
}

export function buildActionQueue(
  analysis: InsightsAnalysis,
  activeConnection: string | null,
  connectionSummary?: Pick<
    ConnectionSummary,
    "onboardingPhase" | "hasSchema" | "hasDomain" | "hasCredentials" | "connectorType"
  > | null,
): ActionQueueItem[] {
  const queue: ActionQueueItem[] = [];
  const overviewUrl = activeConnection ? buildConnectionAppHref(activeConnection) : "/connections";
  const setupStep =
    activeConnection && connectionSummary ? getWizardResumeStep(connectionSummary) : "connect";
  const discoverUrl = activeConnection
    ? buildWizardHref(setupStep, { name: activeConnection })
    : "/connection/new#discover";
  const insightsUrl = activeConnection
    ? `${buildConnectionAppHref(activeConnection, "insights")}&wizard=triage&days=7`
    : "/connections";
  const knowledgeUrl = activeConnection
    ? buildConnectionAppHref(activeConnection, "knowledge")
    : "/connections";
  const metricsUrl = "/metrics";

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
      ctaUrl: insightsUrl,
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
      ctaUrl: insightsUrl,
      status: "open",
    });
  }

  if (!analysis.knowledgeStatus.hasSchema) {
    queue.push({
      id: "add-schema-descriptions",
      source: "setup",
      severity: "info",
      title: "Add schema descriptions",
      detail: "No schema descriptions file is available for this connection yet",
      ctaLabel: "Open setup",
      ctaUrl: discoverUrl,
      status: "open",
    });
  }

  if (!analysis.knowledgeStatus.hasDomain) {
    queue.push({
      id: "add-domain-model",
      source: "setup",
      severity: "info",
      title: "Add domain model",
      detail: "No domain model file is available yet",
      ctaLabel: "Open knowledge",
      ctaUrl: knowledgeUrl,
      status: "open",
    });
  }

  if (analysis.knowledgeStatus.exampleCount === 0) {
    queue.push({
      id: "add-training-examples",
      source: "setup",
      severity: "info",
      title: "Add training examples",
      detail: "No reusable query examples have been saved yet",
      ctaLabel: "Open knowledge",
      ctaUrl: knowledgeUrl,
      status: "open",
    });
  }

  if (analysis.knowledgeStatus.ruleCount === 0) {
    queue.push({
      id: "add-business-rules",
      source: "setup",
      severity: "info",
      title: "Add business rules",
      detail: "No approved business rules file is available yet",
      ctaLabel: "Open knowledge",
      ctaUrl: knowledgeUrl,
      status: "open",
    });
  }

  if ((analysis.knowledgeStatus.metricCount ?? 0) === 0) {
    queue.push({
      id: "define-metrics",
      source: "setup",
      severity: "info",
      title: "Define metrics",
      detail: "No approved metrics catalog entries are available yet",
      ctaLabel: "Open metrics",
      ctaUrl: metricsUrl,
      status: "open",
    });
  }

  return queue;
}

export function buildDashboardSummary(
  analysis: InsightsAnalysis,
  activeConnection: string | null,
  connectionSummary?: Pick<
    ConnectionSummary,
    "onboardingPhase" | "hasSchema" | "hasDomain" | "hasCredentials" | "connectorType"
  > | null,
): DashboardSummary {
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
    queue: buildActionQueue(analysis, activeConnection, connectionSummary),
    recent: {
      traces: analysis.traceCount,
      errors: analysis.errorCount,
      validationFailures: analysis.validationFailureCount,
      totalDurationMs: analysis.totalDurationMs,
    },
  };
}
