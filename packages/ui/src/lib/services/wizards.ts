import type { WizardState } from "@/lib/ui-types";

const storageKey = (wizardId: string, connection: string | null) =>
  `dbmcp.wizard.${wizardId}.${connection ?? "none"}`;

function isWizardState(value: unknown): value is WizardState {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.wizardId === "string" &&
    typeof candidate.step === "string" &&
    Array.isArray(candidate.completedSteps) &&
    Array.isArray(candidate.skippedSteps) &&
    (typeof candidate.connection === "string" || candidate.connection === null) &&
    typeof candidate.updatedAt === "string"
  );
}

function readLocalWizardState(
  wizardId: string,
  connection: string | null,
): WizardState | null {
  if (typeof window === "undefined") {
    return null;
  }

  const raw = window.localStorage.getItem(storageKey(wizardId, connection));
  if (!raw) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(raw);
    return isWizardState(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function writeLocalWizardState(state: WizardState): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(
    storageKey(state.wizardId, state.connection),
    JSON.stringify(state),
  );
}

export async function loadWizardState(
  call: <T = unknown>(method: string, params?: Record<string, unknown>) => Promise<T>,
  wizardId: WizardState["wizardId"],
  connection: string | null,
): Promise<WizardState | null> {
  try {
    const result = await call<WizardState | null>("wizard/state/get", {
      wizardId,
      connection,
    });
    if (result && isWizardState(result)) {
      writeLocalWizardState(result);
      return result;
    }
  } catch {
    // Fall through to local storage fallback.
  }

  return readLocalWizardState(wizardId, connection);
}

export async function persistWizardState(
  call: <T = unknown>(method: string, params?: Record<string, unknown>) => Promise<T>,
  state: WizardState,
): Promise<void> {
  try {
    await call("wizard/state/save", state as unknown as Record<string, unknown>);
  } catch {
    // Ignore backend persistence errors for now; local fallback is authoritative in UI.
  }

  writeLocalWizardState(state);
}
