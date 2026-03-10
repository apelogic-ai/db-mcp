"use client";

import { WIZARD_STEPS } from "./utils";
import type { WizardStep } from "./types";

export type ConnectionStepStatus = "idle" | "active" | "done";

const STATUS_STYLES: Record<ConnectionStepStatus, string> = {
  done: "bg-emerald-950/80 text-emerald-300",
  active: "bg-orange-950/80 text-orange-300",
  idle: "bg-gray-900 text-gray-500",
};

export function ConnectionStatusSteps({
  statuses,
}: {
  statuses: Record<WizardStep, ConnectionStepStatus>;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {WIZARD_STEPS.map((step) => {
        const label = step.id === "connect" ? "Connect" : step.id === "discover" ? "Discover" : "Sample";
        return (
          <div
            key={step.id}
            className={`w-20 px-3 py-2 text-center text-[13px] font-medium ${STATUS_STYLES[statuses[step.id]]}`}
          >
            {label}
          </div>
        );
      })}
    </div>
  );
}
