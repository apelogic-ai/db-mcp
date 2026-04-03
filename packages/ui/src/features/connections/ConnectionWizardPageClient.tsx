"use client";

import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConnectionStatusSteps } from "./ConnectionStatusSteps";
import { ConnectionWorkspaceShell } from "./ConnectionWorkspaceShell";
import { ConnectStepContent } from "./ConnectStepContent";
import { DiscoverStepContent } from "./DiscoverStepContent";
import { SchemaStepContent } from "./SchemaStepContent";
import { useWizardState } from "./useWizardState";
import { WIZARD_STEPS, isWizardStepLocked } from "./utils";

// ─── FloatingAlert ────────────────────────────────────────────────────────────

function FloatingAlert({
  message,
  onClose,
}: {
  message: string | null;
  onClose: () => void;
}) {
  if (!message) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex max-w-md items-start gap-3 rounded-md border border-red-500/40 bg-red-950/95 px-4 py-3 text-sm text-red-100 shadow-xl">
      <div className="min-w-0 flex-1">{message}</div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onClose}
        aria-label="Dismiss alert"
        className="h-7 w-7 shrink-0 text-red-100 hover:bg-red-900/70 hover:text-white"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function ConnectionWizardPageClient() {
  const state = useWizardState();

  const {
    step,
    navigateToStep,
    currentName,
    formError,
    setFormError,
    connectorConfigError,
    setConnectorConfigError,
    wizardStatuses,
    summaryPrimaryLabel,
    summaryPrimaryValue,
    summaryDialect,
  } = state;

  const summaryCard = (
    <div className="max-w-4xl rounded-xl border border-gray-800 bg-gray-950/80 p-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Name</p>
          <p className="text-sm text-gray-200">{currentName || "Unsaved"}</p>
        </div>
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.2em] text-gray-500">
            {summaryPrimaryLabel}
          </p>
          <p className="break-all text-sm text-gray-200">{summaryPrimaryValue}</p>
        </div>
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Status</p>
          <ConnectionStatusSteps statuses={wizardStatuses} />
        </div>
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.2em] text-gray-500">Dialect</p>
          <p className="text-sm text-gray-200">{summaryDialect}</p>
        </div>
      </div>
    </div>
  );

  return (
    <ConnectionWorkspaceShell selectedName={currentName || null} currentView={null}>
      <div className="space-y-6">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-white">Connection Setup Wizard</h1>
          <p className="text-sm text-gray-400">
            Create the connection, inspect what db-mcp can discover, then validate the first
            sample.
          </p>
        </div>

        <div className="space-y-8">
          {/* Step navigation tabs */}
          <div className="space-y-4">
            <nav className="flex flex-wrap items-center gap-3 text-lg font-medium">
              {WIZARD_STEPS.map((wizardStep, index) => {
                const isActive = step === wizardStep.id;
                const isLocked = isWizardStepLocked(wizardStep.id, currentName);
                return (
                  <span key={wizardStep.id} className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        if (!isLocked) {
                          navigateToStep(wizardStep.id);
                        }
                      }}
                      disabled={isLocked}
                      className={`${
                        isActive ? "text-brand" : "text-gray-200"
                      } ${isLocked ? "cursor-not-allowed text-gray-600" : "hover:text-brand"}`}
                    >
                      {index + 1}. {wizardStep.label}
                    </button>
                    {index < WIZARD_STEPS.length - 1 && (
                      <span className="text-gray-600">•</span>
                    )}
                  </span>
                );
              })}
            </nav>
          </div>

          {/* Step content */}
          {step === "connect" && (
            <ConnectStepContent state={state} summaryCard={summaryCard} />
          )}
          {step === "discover" && (
            <DiscoverStepContent state={state} summaryCard={summaryCard} />
          )}
          {step === "sample" && (
            <SchemaStepContent state={state} summaryCard={summaryCard} />
          )}

          <FloatingAlert
            message={formError || connectorConfigError}
            onClose={() => {
              setFormError(null);
              setConnectorConfigError(null);
            }}
          />
        </div>
      </div>
    </ConnectionWorkspaceShell>
  );
}
