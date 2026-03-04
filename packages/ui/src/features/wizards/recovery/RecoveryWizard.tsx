"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useBICP } from "@/lib/bicp-context";
import { loadWizardState, persistWizardState } from "@/lib/services/wizards";
import type { WizardState } from "@/lib/ui-types";

type StepId = "review-incident" | "create-fix" | "retest-resolve";
type ArtifactType = "rule" | "example";

const STEP_ORDER: StepId[] = ["review-incident", "create-fix", "retest-resolve"];

const STEP_LABEL: Record<StepId, string> = {
  "review-incident": "Review Incident",
  "create-fix": "Create Fix",
  "retest-resolve": "Retest and Resolve",
};

interface RecoveryWizardProps {
  enabled: boolean;
  activeConnection: string | null;
  source: "trace" | "insight";
  artifact: ArtifactType;
  draft: string;
  returnTo: string;
  onCreateArtifact: (
    content: string,
    artifact: ArtifactType,
  ) => Promise<{ success: boolean; path?: string; error?: string }>;
}

function nextStep(step: StepId): StepId | null {
  const idx = STEP_ORDER.indexOf(step);
  if (idx < 0 || idx === STEP_ORDER.length - 1) {
    return null;
  }
  return STEP_ORDER[idx + 1];
}

export function RecoveryWizard({
  enabled,
  activeConnection,
  source,
  artifact,
  draft,
  returnTo,
  onCreateArtifact,
}: RecoveryWizardProps) {
  const { call } = useBICP();

  const [currentStep, setCurrentStep] = useState<StepId>("review-incident");
  const [completedSteps, setCompletedSteps] = useState<StepId[]>([]);
  const [skippedSteps, setSkippedSteps] = useState<StepId[]>([]);
  const [stateReady, setStateReady] = useState(false);

  const [artifactType, setArtifactType] = useState<ArtifactType>(artifact);
  const [draftContent, setDraftContent] = useState(draft);
  const [createdPath, setCreatedPath] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

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
      const persisted = await loadWizardState(call, "recovery", activeConnection);
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

      setStateReady(true);
    };

    load();

    return () => {
      cancelled = true;
    };
  }, [enabled, activeConnection, call]);

  useEffect(() => {
    if (!enabled || !stateReady) {
      return;
    }

    const state: WizardState = {
      wizardId: "recovery",
      step: currentStep,
      completedSteps,
      skippedSteps,
      connection: activeConnection,
      updatedAt: new Date().toISOString(),
    };

    persistWizardState(call, state).catch(() => {
      // local fallback is handled by the service
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

    setArtifactType(artifact);
    setDraftContent(draft);
    setCreatedPath(null);
    setMessage(null);
  }, [enabled, artifact, draft]);

  if (!enabled) {
    return null;
  }

  const stepDone = (step: StepId) => completedSteps.includes(step);
  const stepSkipped = (step: StepId) => skippedSteps.includes(step);

  const createFix = async () => {
    if (!draftContent.trim()) {
      setMessage("Draft content is empty.");
      return;
    }

    setBusy(true);
    setMessage(null);

    try {
      const result = await onCreateArtifact(draftContent.trim(), artifactType);
      if (!result.success) {
        setMessage(result.error || "Failed to create artifact.");
        return;
      }

      setCreatedPath(result.path || null);
      markCompleted("create-fix");
      goNext("create-fix");
      setMessage("Fix artifact created.");
    } finally {
      setBusy(false);
    }
  };

  const renderStepBody = (step: StepId) => {
    switch (step) {
      case "review-incident":
        return (
          <div className="space-y-3 text-sm text-gray-300">
            <p>
              Source: <span className="text-gray-100">{source}</span> | Suggested artifact:{" "}
              <span className="text-gray-100">{artifactType}</span>
            </p>
            <div className="rounded border border-gray-800 bg-gray-950 p-3 text-xs text-gray-300 max-h-36 overflow-auto whitespace-pre-wrap">
              {draftContent || "No draft provided."}
            </div>
            <Button
              size="sm"
              className="bg-brand hover:bg-brand-dark text-white"
              onClick={() => {
                markCompleted("review-incident");
                goNext("review-incident");
              }}
            >
              Continue
            </Button>
          </div>
        );

      case "create-fix":
        return (
          <div className="space-y-3 text-sm text-gray-300">
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant={artifactType === "rule" ? "default" : "outline"}
                className={
                  artifactType === "rule"
                    ? "bg-brand hover:bg-brand-dark text-white"
                    : "border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300"
                }
                onClick={() => setArtifactType("rule")}
              >
                Rule
              </Button>
              <Button
                size="sm"
                variant={artifactType === "example" ? "default" : "outline"}
                className={
                  artifactType === "example"
                    ? "bg-brand hover:bg-brand-dark text-white"
                    : "border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300"
                }
                onClick={() => setArtifactType("example")}
              >
                Example
              </Button>
            </div>
            <textarea
              value={draftContent}
              onChange={(e) => setDraftContent(e.target.value)}
              rows={10}
              className="w-full rounded border border-gray-700 bg-gray-950 p-3 text-xs text-gray-200"
            />
            <Button
              size="sm"
              className="bg-brand hover:bg-brand-dark text-white"
              onClick={createFix}
              disabled={busy || !activeConnection}
            >
              {busy ? "Creating..." : "Create Fix Artifact"}
            </Button>
          </div>
        );

      case "retest-resolve":
        return (
          <div className="space-y-3 text-sm text-gray-300">
            <p>Run the failing workflow again and verify the issue is resolved.</p>
            {createdPath && (
              <p className="text-xs text-gray-400">Created: {createdPath}</p>
            )}
            <div className="flex items-center gap-2">
              <Link
                href={returnTo}
                className="rounded-md border border-gray-700 px-3 py-2 text-xs text-gray-200 hover:bg-gray-800"
              >
                Return to Source
              </Link>
              <Link
                href="/traces"
                className="rounded-md border border-gray-700 px-3 py-2 text-xs text-gray-200 hover:bg-gray-800"
              >
                Open Traces
              </Link>
              <Button
                size="sm"
                className="bg-brand hover:bg-brand-dark text-white"
                onClick={() => markCompleted("retest-resolve")}
              >
                Mark Resolved
              </Button>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="mb-4 rounded-lg border border-[#EF8626] bg-[#EF8626]/5 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Recovery Wizard</h2>
          <p className="mt-1 text-sm text-gray-300">
            Close the loop from error trace to rule/example fix.
          </p>
        </div>
        <Link
          href="/context"
          className="rounded-md border border-gray-700 px-3 py-1.5 text-xs text-gray-200 hover:bg-gray-800"
        >
          Exit Wizard
        </Link>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-3">
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
          {!stepDone(currentStep) && currentStep !== "retest-resolve" && (
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

        {message && <p className="mt-3 text-xs text-gray-300">{message}</p>}
      </div>

      {stepDone("retest-resolve") && (
        <div className="mt-4 rounded border border-green-800 bg-green-950/20 p-3 text-sm text-green-300">
          Recovery flow completed for this connection.
        </div>
      )}
    </div>
  );
}
