import { describe, expect, it } from "vitest";
import { isWizardStepLocked } from "@/features/connections/utils";

describe("isWizardStepLocked", () => {
  it("locks non-connect steps when there is no connection name yet", () => {
    expect(isWizardStepLocked("connect", null)).toBe(false);
    expect(isWizardStepLocked("discover", null)).toBe(true);
    expect(isWizardStepLocked("sample", null)).toBe(true);
  });

  it("allows non-connect steps when the connection has been named locally", () => {
    expect(isWizardStepLocked("discover", "boost-new")).toBe(false);
    expect(isWizardStepLocked("sample", "boost-new")).toBe(false);
  });
});
