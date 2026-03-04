export type ViewMode = "essentials" | "advanced";

export interface ActionQueueItem {
  id: string;
  source: "insight" | "trace" | "setup";
  severity: "info" | "warn" | "critical";
  title: string;
  detail: string;
  ctaLabel: string;
  ctaUrl: string;
  status: "open" | "done" | "dismissed";
}

export interface WizardState {
  wizardId: "onboarding" | "triage" | "recovery";
  step: string;
  completedSteps: string[];
  skippedSteps: string[];
  connection: string | null;
  updatedAt: string;
}
