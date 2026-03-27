import { describe, expect, it } from "vitest";
import {
  applyApiEnvValueChange,
  buildApiTestParams,
  clearApiEnvEntry,
  getApiEnvRowState,
  isWizardStepLocked,
  normalizeApiEnvEntry,
  saveApiEnvEntry,
} from "@/features/connections/utils";

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

describe("buildApiTestParams", () => {
  it("includes saved connection context and auth metadata", () => {
    expect(
      buildApiTestParams({
        name: "lens",
        templateId: "metabase",
        baseUrl: "https://metabase.k8slens.dev",
        authType: "header",
        tokenEnv: "API_KEY",
        apiKey: "",
        headerName: "x-api-key",
        paramName: "",
        envVars: [
          {
            slot: "MB_API_KEY",
            name: "API_KEY",
            value: "",
            secret: true,
          },
        ],
      }),
    ).toEqual({
      name: "lens",
      templateId: "metabase",
      connectorType: "api",
      baseUrl: "https://metabase.k8slens.dev",
      authType: "header",
      tokenEnv: "API_KEY",
      headerName: "x-api-key",
      envVars: [
        {
          slot: "MB_API_KEY",
          name: "API_KEY",
          secret: true,
        },
      ],
    });
  });

  it("sends inline token values when provided", () => {
    expect(
      buildApiTestParams({
        name: "lens",
        templateId: "",
        baseUrl: "https://metabase.k8slens.dev",
        authType: "query_param",
        tokenEnv: "MB_API_KEY",
        apiKey: "secret-token",
        headerName: "",
        paramName: "api_key",
        envVars: [
          {
            slot: "MB_API_KEY",
            name: "MB_API_KEY",
            value: "secret-token",
            secret: true,
          },
        ],
      }),
    ).toEqual({
      name: "lens",
      connectorType: "api",
      baseUrl: "https://metabase.k8slens.dev",
      authType: "query_param",
      tokenEnv: "MB_API_KEY",
      apiKey: "secret-token",
      paramName: "api_key",
      envVars: [
        {
          slot: "MB_API_KEY",
          name: "MB_API_KEY",
          value: "secret-token",
          secret: true,
        },
      ],
    });
  });
});

describe("API env row helpers", () => {
  it("normalizes saved rows into masked saved state", () => {
    expect(
      normalizeApiEnvEntry({
        name: "MB_API_KEY",
        value: "",
        secret: true,
        hasSavedValue: true,
      }),
    ).toMatchObject({
      name: "MB_API_KEY",
      value: "",
      hasSavedValue: true,
      masked: true,
      removed: false,
    });
  });

  it("restores the saved placeholder when a saved row is cleared while editing", () => {
    expect(
      applyApiEnvValueChange(
        {
          name: "MB_API_KEY",
          value: "",
          secret: true,
          hasSavedValue: true,
          masked: true,
        },
        "",
      ),
    ).toMatchObject({
      value: "",
      hasSavedValue: true,
      masked: true,
    });
  });

  it("marks typed secrets as addable or saveable", () => {
    expect(
      getApiEnvRowState({
        name: "MB_API_KEY",
        value: "new-token",
        secret: true,
      }).primaryActionLabel,
    ).toBe("Add");

    expect(
      getApiEnvRowState({
        name: "MB_API_KEY",
        value: "replacement-token",
        secret: true,
        hasSavedValue: true,
        masked: false,
      }).primaryActionLabel,
    ).toBe("Save");
  });

  it("does not show an add action for rows that are already saved", () => {
    expect(
      getApiEnvRowState({
        name: "MB_API_KEY",
        value: "",
        secret: true,
        hasSavedValue: true,
        masked: true,
      }).primaryActionLabel,
    ).toBeNull();
  });

  it("masks a locally saved secret without losing its effective value", () => {
    expect(
      saveApiEnvEntry({
        name: "MB_API_KEY",
        value: "new-token",
        secret: true,
      }),
    ).toMatchObject({
      value: "new-token",
      hasSavedValue: true,
      masked: true,
    });
  });

  it("marks removed secrets so the backend can actually delete them", () => {
    expect(
      clearApiEnvEntry({
        name: "MB_API_KEY",
        value: "",
        secret: true,
        hasSavedValue: true,
        masked: true,
      }),
    ).toMatchObject({
      value: "",
      hasSavedValue: false,
      masked: false,
      removed: true,
    });
  });
});
