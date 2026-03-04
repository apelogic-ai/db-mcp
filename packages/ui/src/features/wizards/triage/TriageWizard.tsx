"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useBICP } from "@/lib/bicp-context";
import { loadWizardState, persistWizardState } from "@/lib/services/wizards";
import type { WizardState } from "@/lib/ui-types";

type StepId = "review-queue" | "resolve-vocab" | "capture-patterns" | "complete";

const STEP_ORDER: StepId[] = [
  "review-queue",
  "resolve-vocab",
  "capture-patterns",
  "complete",
];

const STEP_LABEL: Record<StepId, string> = {
  "review-queue": "Review Queue",
  "resolve-vocab": "Resolve Terms",
  "capture-patterns": "Capture Patterns",
  "complete": "Complete",
};

interface TriageWizardProps {
  enabled: boolean;
  activeConnection: string | null;
  openGapCount: number;
  unsavedPatternCount: number;
  unsavedErrorCount: number;
}

function nextStep(step: StepId): StepId | null {
  const idx = STEP_ORDER.indexOf(step);
  if (idx < 0 || idx === STEP_ORDER.length - 1) {
    return null;
  }
  return STEP_ORDER[idx + 1];
}

export function TriageWizard({
  enabled,
  activeConnection,
  openGapCount,
  unsavedPatternCount,
  unsavedErrorCount,
}: TriageWizardProps) {
  const { call } = useBICP();

  const [currentStep, setCurrentStep] = useState<StepId>("review-queue");
  const [completedSteps, setCompletedSteps] = useState<StepId[]>([]);
  const [skippedSteps, setSkippedSteps] = useState<StepId[]>([]);
  const [stateReady, setStateReady] = useState(false);
  const [baseline, setBaseline] = useState<{
    openGapCount: number;
    unsavedPatternCount: number;
    unsavedErrorCount: number;
  } | null>(null);

  const markCompleted = useCallback((step: StepId) => {
    setCompletedSteps((prev) => (prev.includes(step) ? prev : [...prev, step]));
    setSkippedSteps((prev) => prev.filter((item) => item !== step));
  }, []);

  const markSkipped = useCallback((step: StepId) => {
    setSkippedSteps((prev) => (prev.includes(step) ? prev : [...prev, step]));
  }, []);

  const goNext = useCallback((step: StepId) => {
    const next = nextStep(step);
    if (next) {
      setCurrentStep(next);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setStateReady(false);
      return;
    }

    let cancelled = false;

    const load = async () => {
      const persisted = await loadWizardState(call, "triage", activeConnection);
      if (cancelled) {
        return;
      }

      if (persisted) {
        const persistedStep = persisted.step as StepId;
        if (STEP_ORDER.includes(persistedStep)) {
          setCurrentStep(persistedStep);
        }
        setCompletedSteps(
          persisted.completedSteps.filter((step): step is StepId =>
            STEP_ORDER.includes(step as StepId),
          ),
        );
        setSkippedSteps(
          persisted.skippedSteps.filter((step): step is StepId =>
            STEP_ORDER.includes(step as StepId),
          ),
        );
      }

      setBaseline({ openGapCount, unsavedPatternCount, unsavedErrorCount });
      setStateReady(true);
    };

    load();

    return () => {
      cancelled = true;
    };
  }, [
    enabled,
    activeConnection,
    call,
    openGapCount,
    unsavedPatternCount,
    unsavedErrorCount,
  ]);

  useEffect(() => {
    if (!enabled || !stateReady) {
      return;
    }

    const state: WizardState = {
      wizardId: "triage",
      step: currentStep,
      completedSteps,
      skippedSteps,
      connection: activeConnection,
      updatedAt: new Date().toISOString(),
    };

    persistWizardState(call, state).catch(() => {
      // local fallback is handled in the service
    });
  }, [
    enabled,
    stateReady,
    currentStep,
    completedSteps,
    skippedSteps,
    activeConnection,
    call,
  ]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    markCompleted("review-queue");

    if (openGapCount === 0) {
      markCompleted("resolve-vocab");
    }

    if (unsavedPatternCount === 0 && unsavedErrorCount === 0) {
      markCompleted("capture-patterns");
    }
  }, [enabled, openGapCount, unsavedPatternCount, unsavedErrorCount, markCompleted]);

  if (!enabled) {
    return null;
  }

  const stepDone = (step: StepId) => completedSteps.includes(step);
  const stepSkipped = (step: StepId) => skippedSteps.includes(step);

  const renderStepBody = (step: StepId) => {
    switch (step) {
      case "review-queue":
        return (
          <div className="space-y-3 text-sm text-gray-300">
            <p>
              Start with the action queue. It aggregates term gaps and SQL patterns that
              need triage.
            </p>
            <div className="rounded border border-gray-800 bg-gray-950 p-3 text-xs text-gray-300">
              open terms: {openGapCount} | unsaved patterns: {unsavedPatternCount} | unsaved
              learnings: {unsavedErrorCount}
            </div>
            <div className="flex items-center gap-2">
              <Link
                href="#insights-action-queue"
                className="rounded-md border border-gray-700 px-3 py-2 text-xs text-gray-200 hover:bg-gray-800"
              >
                Open Action Queue
              </Link>
              <Button
                size="sm"
                className="bg-brand hover:bg-brand-dark text-white"
                onClick={() => {
                  markCompleted("review-queue");
                  goNext("review-queue");
                }}
              >
                Continue
              </Button>
            </div>
          </div>
        );

      case "resolve-vocab":
        return (
          <div className="space-y-3 text-sm text-gray-300">
            <p>
              Resolve unmapped terms first. Add business rules or dismiss false positives.
            </p>
            <div className="rounded border border-gray-800 bg-gray-950 p-3 text-xs text-gray-300">
              current open terms: {openGapCount}
            </div>
            <div className="flex items-center gap-2">
              <Link
                href="#queue-vocabulary"
                className="rounded-md border border-gray-700 px-3 py-2 text-xs text-gray-200 hover:bg-gray-800"
              >
                Review Vocabulary Item
              </Link>
              <Button
                size="sm"
                className="bg-brand hover:bg-brand-dark text-white"
                onClick={() => {
                  markCompleted("resolve-vocab");
                  goNext("resolve-vocab");
                }}
                disabled={openGapCount > 0}
              >
                {openGapCount > 0 ? "Clear Terms to Continue" : "Continue"}
              </Button>
            </div>
          </div>
        );

      case "capture-patterns":
        return (
          <div className="space-y-3 text-sm text-gray-300">
            <p>
              Convert repeated successful SQL into examples and recurring failures into
              learnings.
            </p>
            <div className="rounded border border-gray-800 bg-gray-950 p-3 text-xs text-gray-300">
              unsaved patterns: {unsavedPatternCount} | unsaved learnings: {unsavedErrorCount}
            </div>
            <div className="flex items-center gap-2">
              <Link
                href="#queue-sql-patterns"
                className="rounded-md border border-gray-700 px-3 py-2 text-xs text-gray-200 hover:bg-gray-800"
              >
                Review SQL Pattern Item
              </Link>
              <Link
                href="#queue-error-learnings"
                className="rounded-md border border-gray-700 px-3 py-2 text-xs text-gray-200 hover:bg-gray-800"
              >
                Review Error Learning Item
              </Link>
              <Button
                size="sm"
                className="bg-brand hover:bg-brand-dark text-white"
                onClick={() => {
                  markCompleted("capture-patterns");
                  goNext("capture-patterns");
                }}
                disabled={unsavedPatternCount + unsavedErrorCount > 0}
              >
                {unsavedPatternCount + unsavedErrorCount > 0
                  ? "Capture Knowledge to Continue"
                  : "Continue"}
              </Button>
            </div>
          </div>
        );

      case "complete": {
        const before = baseline ?? {
          openGapCount,
          unsavedPatternCount,
          unsavedErrorCount,
        };

        const rows = [
          {
            label: "Open terms",
            before: before.openGapCount,
            now: openGapCount,
          },
          {
            label: "Unsaved SQL patterns",
            before: before.unsavedPatternCount,
            now: unsavedPatternCount,
          },
          {
            label: "Unsaved error learnings",
            before: before.unsavedErrorCount,
            now: unsavedErrorCount,
          },
        ];

        return (
          <div className="space-y-3 text-sm text-gray-300">
            <p>Review before/after deltas for this triage session.</p>
            <div className="rounded border border-gray-800 bg-gray-950 p-3 text-xs space-y-2">
              {rows.map((row) => {
                const delta = row.before - row.now;
                return (
                  <div key={row.label} className="flex items-center gap-2">
                    <span className="text-gray-400 w-44">{row.label}</span>
                    <span className="text-gray-300">{`${row.before} -> ${row.now}`}</span>
                    <span className={delta > 0 ? "text-green-400" : "text-gray-500"}>
                      {delta > 0 ? `-${delta}` : "no change"}
                    </span>
                  </div>
                );
              })}
            </div>
            <Button
              size="sm"
              className="bg-brand hover:bg-brand-dark text-white"
              onClick={() => markCompleted("complete")}
            >
              Mark Triage Complete
            </Button>
          </div>
        );
      }

      default:
        return null;
    }
  };

  return (
    <div className="rounded-lg border border-[#EF8626] bg-[#EF8626]/5 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Insights Triage Wizard</h2>
          <p className="mt-1 text-sm text-gray-300">
            Close gaps and capture reusable knowledge from recent traces.
          </p>
        </div>
        <Link
          href="/insights"
          className="rounded-md border border-gray-700 px-3 py-1.5 text-xs text-gray-200 hover:bg-gray-800"
        >
          Exit Wizard
        </Link>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        {STEP_ORDER.map((step, idx) => (
          <button
            key={step}
            type="button"
            onClick={() => setCurrentStep(step)}
            className={`rounded border px-2 py-2 text-left text-xs transition-colors ${
              currentStep === step
                ? "border-brand bg-gray-900 text-white"
                : stepDone(step)
                  ? "border-green-700 bg-green-950/30 text-green-300"
                  : stepSkipped(step)
                    ? "border-yellow-700 bg-yellow-950/20 text-yellow-300"
                    : "border-gray-800 bg-gray-950 text-gray-400 hover:text-gray-200"
            }`}
          >
            <div className="font-medium">{idx + 1}. {STEP_LABEL[step]}</div>
            <div className="mt-1 text-[11px]">
              {stepDone(step) ? "completed" : stepSkipped(step) ? "skipped" : "pending"}
            </div>
          </button>
        ))}
      </div>

      <div className="mt-4 rounded border border-gray-800 bg-gray-950 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-white">{STEP_LABEL[currentStep]}</h3>
          {!stepDone(currentStep) && currentStep !== "complete" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                markSkipped(currentStep);
                goNext(currentStep);
              }}
              className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
            >
              Skip Step
            </Button>
          )}
        </div>

        {renderStepBody(currentStep)}
      </div>

      {stepDone("complete") && (
        <div className="mt-4 rounded border border-green-800 bg-green-950/20 p-3 text-sm text-green-300">
          Triage flow completed for this connection.
        </div>
      )}
    </div>
  );
}
