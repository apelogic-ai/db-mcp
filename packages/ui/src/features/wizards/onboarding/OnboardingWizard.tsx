"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { useBICP } from "@/lib/bicp-context";
import { useConnections } from "@/lib/connection-context";
import {
  loadWizardState,
  persistWizardState,
} from "@/lib/services/wizards";
import type { WizardState } from "@/lib/ui-types";
import type { Connection, ConnectionsListResult } from "@/features/config/types";

interface Agent {
  id: string;
  name: string;
  installed: boolean;
  dbmcpConfigured: boolean;
}

interface AgentsListResult {
  agents: Agent[];
}

type StepId =
  | "select-source"
  | "verify-connection"
  | "discover-context"
  | "configure-agent"
  | "run-health-check";

const STEP_ORDER: StepId[] = [
  "select-source",
  "verify-connection",
  "discover-context",
  "configure-agent",
  "run-health-check",
];

const STEP_TITLE: Record<StepId, string> = {
  "select-source": "Select Source",
  "verify-connection": "Verify Connection",
  "discover-context": "Discover Context",
  "configure-agent": "Configure Agent",
  "run-health-check": "Run Health Check",
};

function nextStep(step: StepId): StepId | null {
  const idx = STEP_ORDER.indexOf(step);
  if (idx < 0 || idx === STEP_ORDER.length - 1) {
    return null;
  }
  return STEP_ORDER[idx + 1];
}

interface OnboardingWizardProps {
  enabled: boolean;
  connections: Connection[];
  activeConnection: string | null;
  refreshConnections: () => Promise<void>;
  onInstallPlayground: () => Promise<void>;
  playgroundInstalling: boolean;
  onOpenCreateDatabase: () => void;
}

export function OnboardingWizard({
  enabled,
  connections,
  activeConnection,
  refreshConnections,
  onInstallPlayground,
  playgroundInstalling,
  onOpenCreateDatabase,
}: OnboardingWizardProps) {
  const { call } = useBICP();
  const { switchConnection } = useConnections();

  const [currentStep, setCurrentStep] = useState<StepId>("select-source");
  const [completedSteps, setCompletedSteps] = useState<StepId[]>([]);
  const [skippedSteps, setSkippedSteps] = useState<StepId[]>([]);
  const [stateReady, setStateReady] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [stepMessage, setStepMessage] = useState<string | null>(null);

  const [agents, setAgents] = useState<Agent[]>([]);
  const [healthSummary, setHealthSummary] = useState<{
    traceCount: number;
    errorCount: number;
    validationFailures: number;
  } | null>(null);

  const activeConnectionMeta = useMemo(
    () => connections.find((conn) => conn.name === activeConnection) ?? null,
    [connections, activeConnection],
  );

  const configuredAgents = useMemo(
    () => agents.filter((agent) => agent.installed && agent.dbmcpConfigured),
    [agents],
  );

  const markCompleted = useCallback((step: StepId) => {
    setCompletedSteps((prev) => (prev.includes(step) ? prev : [...prev, step]));
    setSkippedSteps((prev) => prev.filter((item) => item !== step));
  }, []);

  const markSkipped = useCallback((step: StepId) => {
    setSkippedSteps((prev) => (prev.includes(step) ? prev : [...prev, step]));
  }, []);

  const jumpToNext = useCallback((step: StepId) => {
    const next = nextStep(step);
    if (next) {
      setCurrentStep(next);
    }
  }, []);

  const loadAgents = useCallback(async () => {
    try {
      const result = await call<AgentsListResult>("agents/list", {});
      setAgents(result.agents ?? []);
    } catch {
      setAgents([]);
    }
  }, [call]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    loadAgents();
  }, [enabled, loadAgents]);

  useEffect(() => {
    if (!enabled) {
      setStateReady(false);
      return;
    }

    let cancelled = false;

    const load = async () => {
      const persisted = await loadWizardState(call, "onboarding", activeConnection);
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
      wizardId: "onboarding",
      step: currentStep,
      completedSteps,
      skippedSteps,
      connection: activeConnection,
      updatedAt: new Date().toISOString(),
    };

    persistWizardState(call, state).catch(() => {
      // no-op; persistence uses local fallback
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

    if (activeConnection) {
      markCompleted("select-source");
    }

    if (activeConnectionMeta?.hasSchema && activeConnectionMeta?.hasDomain) {
      markCompleted("discover-context");
    }

    if (configuredAgents.length > 0) {
      markCompleted("configure-agent");
    }
  }, [
    enabled,
    activeConnection,
    activeConnectionMeta,
    configuredAgents.length,
    markCompleted,
  ]);

  if (!enabled) {
    return null;
  }

  const stepIsComplete = (step: StepId) => completedSteps.includes(step);
  const stepIsSkipped = (step: StepId) => skippedSteps.includes(step);

  const runInstallPlayground = async () => {
    setBusyAction("install-playground");
    setStepMessage(null);
    try {
      await onInstallPlayground();
      await refreshConnections();

      const result = await call<ConnectionsListResult>("connections/list", {});
      const hasPlayground = result.connections.some((conn) => conn.name === "playground");
      if (hasPlayground) {
        await switchConnection("playground");
      }
      markCompleted("select-source");
      jumpToNext("select-source");
      setStepMessage("Playground installed and selected.");
    } catch (err) {
      setStepMessage(err instanceof Error ? err.message : "Failed to install playground.");
    } finally {
      setBusyAction(null);
    }
  };

  const runVerifyConnection = async () => {
    if (!activeConnection) {
      setStepMessage("Select an active connection first.");
      return;
    }

    setBusyAction("verify-connection");
    setStepMessage(null);

    try {
      const result = await call<{
        success: boolean;
        message?: string;
        error?: string;
      }>("connections/test", { name: activeConnection });

      if (result.success) {
        markCompleted("verify-connection");
        jumpToNext("verify-connection");
        setStepMessage(result.message || "Connection verified.");
      } else {
        setStepMessage(result.error || "Connection test failed.");
      }
    } catch (err) {
      setStepMessage(err instanceof Error ? err.message : "Connection test failed.");
    } finally {
      setBusyAction(null);
    }
  };

  const runDiscoverCheck = async () => {
    if (!activeConnection) {
      setStepMessage("Select an active connection first.");
      return;
    }

    setBusyAction("discover-context");
    setStepMessage(null);

    try {
      await refreshConnections();
      const result = await call<ConnectionsListResult>("connections/list", {});
      const active = result.connections.find((conn) => conn.name === activeConnection);

      if (active?.hasSchema && active?.hasDomain) {
        markCompleted("discover-context");
        jumpToNext("discover-context");
        setStepMessage("Schema and domain artifacts detected.");
      } else {
        setStepMessage(
          "Schema/domain artifacts are still incomplete. Run onboarding workflow in your agent and refresh.",
        );
      }
    } catch (err) {
      setStepMessage(
        err instanceof Error ? err.message : "Failed to refresh onboarding status.",
      );
    } finally {
      setBusyAction(null);
    }
  };

  const runConfigureAgent = async () => {
    setBusyAction("configure-agent");
    setStepMessage(null);

    try {
      const result = await call<AgentsListResult>("agents/list", {});
      const target = result.agents.find((agent) => agent.installed && !agent.dbmcpConfigured);

      if (!target) {
        if (result.agents.some((agent) => agent.installed && agent.dbmcpConfigured)) {
          markCompleted("configure-agent");
          jumpToNext("configure-agent");
          setStepMessage("At least one agent is already configured.");
        } else {
          setStepMessage("No installed agent available for configuration.");
        }
        return;
      }

      const configureResult = await call<{ success: boolean; error?: string }>(
        "agents/configure",
        { agentId: target.id },
      );

      if (!configureResult.success) {
        setStepMessage(configureResult.error || "Agent configuration failed.");
        return;
      }

      await loadAgents();
      markCompleted("configure-agent");
      jumpToNext("configure-agent");
      setStepMessage(`Configured ${target.name}.`);
    } catch (err) {
      setStepMessage(err instanceof Error ? err.message : "Agent configuration failed.");
    } finally {
      setBusyAction(null);
    }
  };

  const runHealthCheck = async () => {
    setBusyAction("run-health-check");
    setStepMessage(null);

    try {
      const result = await call<{
        success: boolean;
        analysis?: {
          traceCount: number;
          errorCount: number;
          validationFailureCount: number;
        };
        error?: string;
      }>("insights/analyze", { days: 7 });

      if (!result.success || !result.analysis) {
        setStepMessage(result.error || "Health check failed.");
        return;
      }

      setHealthSummary({
        traceCount: result.analysis.traceCount,
        errorCount: result.analysis.errorCount,
        validationFailures: result.analysis.validationFailureCount,
      });

      markCompleted("run-health-check");
      setStepMessage("Health check completed.");
    } catch (err) {
      setStepMessage(err instanceof Error ? err.message : "Health check failed.");
    } finally {
      setBusyAction(null);
    }
  };

  const renderStepBody = (step: StepId) => {
    switch (step) {
      case "select-source":
        return (
          <div className="space-y-3">
            <p className="text-sm text-gray-300">
              Active connection: {activeConnection ?? "none"}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                onClick={runInstallPlayground}
                disabled={playgroundInstalling || busyAction === "install-playground"}
                className="bg-brand hover:bg-brand-dark text-white"
              >
                {playgroundInstalling || busyAction === "install-playground"
                  ? "Installing..."
                  : "Use Playground DB"}
              </Button>
              <Button
                variant="outline"
                className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-200"
                onClick={() => {
                  if (!activeConnection) {
                    setStepMessage("Set an active connection first.");
                    return;
                  }
                  markCompleted("select-source");
                  jumpToNext("select-source");
                }}
              >
                Use Current Connection
              </Button>
              <Button
                variant="outline"
                className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-200"
                onClick={onOpenCreateDatabase}
              >
                Create Database Connection
              </Button>
            </div>
          </div>
        );

      case "verify-connection":
        return (
          <div className="space-y-3">
            <p className="text-sm text-gray-300">
              Verify the selected connection is reachable and credentials are valid.
            </p>
            <Button
              onClick={runVerifyConnection}
              disabled={busyAction === "verify-connection" || !activeConnection}
              className="bg-brand hover:bg-brand-dark text-white"
            >
              {busyAction === "verify-connection" ? "Testing..." : "Run Connection Test"}
            </Button>
          </div>
        );

      case "discover-context":
        return (
          <div className="space-y-3">
            <p className="text-sm text-gray-300">
              Completion gate: both schema descriptions and domain model exist for the
              active connection.
            </p>
            <div className="text-xs text-gray-400">
              schema: {activeConnectionMeta?.hasSchema ? "yes" : "no"} · domain: {activeConnectionMeta?.hasDomain ? "yes" : "no"}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                onClick={runDiscoverCheck}
                disabled={busyAction === "discover-context" || !activeConnection}
                className="bg-brand hover:bg-brand-dark text-white"
              >
                {busyAction === "discover-context"
                  ? "Refreshing..."
                  : "Refresh Discovery Status"}
              </Button>
              <Link
                href="/context"
                className="rounded-md border border-gray-700 px-3 py-2 text-sm text-gray-200 hover:bg-gray-800"
              >
                Open Context Viewer
              </Link>
            </div>
          </div>
        );

      case "configure-agent":
        return (
          <div className="space-y-3">
            <p className="text-sm text-gray-300">
              Completion gate: at least one installed agent has db-mcp configured.
            </p>
            <div className="text-xs text-gray-400">
              configured agents: {configuredAgents.length}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                onClick={runConfigureAgent}
                disabled={busyAction === "configure-agent"}
                className="bg-brand hover:bg-brand-dark text-white"
              >
                {busyAction === "configure-agent"
                  ? "Configuring..."
                  : "Auto-Configure Agent"}
              </Button>
              <Link
                href="#agent-configuration"
                className="rounded-md border border-gray-700 px-3 py-2 text-sm text-gray-200 hover:bg-gray-800"
              >
                Open Agent Section
              </Link>
            </div>
          </div>
        );

      case "run-health-check":
        return (
          <div className="space-y-3">
            <p className="text-sm text-gray-300">
              Run a quick 7-day trace analysis to establish your initial quality baseline.
            </p>
            <Button
              onClick={runHealthCheck}
              disabled={busyAction === "run-health-check"}
              className="bg-brand hover:bg-brand-dark text-white"
            >
              {busyAction === "run-health-check" ? "Running..." : "Run Health Check"}
            </Button>
            {healthSummary && (
              <div className="rounded border border-gray-800 bg-gray-950 p-3 text-xs text-gray-300">
                traces: {healthSummary.traceCount} · errors: {healthSummary.errorCount} · validation failures: {healthSummary.validationFailures}
              </div>
            )}
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="rounded-lg border border-[#EF8626] bg-[#EF8626]/5 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Onboarding Wizard</h2>
          <p className="mt-1 text-sm text-gray-300">
            Complete the five-step setup journey for the active connection.
          </p>
        </div>
        <Link
          href="/config"
          className="rounded-md border border-gray-700 px-3 py-1.5 text-xs text-gray-200 hover:bg-gray-800"
        >
          Exit Wizard
        </Link>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-5">
        {STEP_ORDER.map((step, idx) => (
          <button
            key={step}
            type="button"
            onClick={() => setCurrentStep(step)}
            className={`rounded border px-2 py-2 text-left text-xs transition-colors ${
              currentStep === step
                ? "border-brand bg-gray-900 text-white"
                : stepIsComplete(step)
                  ? "border-green-700 bg-green-950/30 text-green-300"
                  : stepIsSkipped(step)
                    ? "border-yellow-700 bg-yellow-950/20 text-yellow-300"
                    : "border-gray-800 bg-gray-950 text-gray-400 hover:text-gray-200"
            }`}
          >
            <div className="font-medium">{idx + 1}. {STEP_TITLE[step]}</div>
            <div className="mt-1 text-[11px]">
              {stepIsComplete(step)
                ? "completed"
                : stepIsSkipped(step)
                  ? "skipped"
                  : "pending"}
            </div>
          </button>
        ))}
      </div>

      <div className="mt-4 rounded border border-gray-800 bg-gray-950 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-white">{STEP_TITLE[currentStep]}</h3>
          {!stepIsComplete(currentStep) && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                markSkipped(currentStep);
                jumpToNext(currentStep);
              }}
              className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
            >
              Skip Step
            </Button>
          )}
        </div>

        {renderStepBody(currentStep)}

        {stepMessage && (
          <p className="mt-3 text-xs text-gray-300">{stepMessage}</p>
        )}
      </div>

      {stepIsComplete("run-health-check") && (
        <div className="mt-4 rounded border border-green-800 bg-green-950/20 p-3 text-sm text-green-300">
          Onboarding flow completed for this connection.
        </div>
      )}
    </div>
  );
}
