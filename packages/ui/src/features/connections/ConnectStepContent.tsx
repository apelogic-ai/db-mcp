"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getApiEnvRowState } from "./utils";
import type { WizardState } from "./useWizardState";

type Props = {
  state: WizardState;
  summaryCard: React.ReactNode;
};

export function ConnectStepContent({ state, summaryCard }: Props) {
  const {
    connectorType,
    setConnectorType,
    existingName,
    connectionName,
    setConnectionName,
    displayDatabaseUrl,
    setDisplayDatabaseUrl,
    setDatabaseUrl,
    directory,
    setDirectory,
    baseUrl,
    setBaseUrl,
    apiTemplateId,
    apiTemplates,
    selectedApiTemplate,
    handleApiTemplateSelect,
    apiAuthType,
    handleApiAuthTypeChange,
    apiHeaderName,
    setApiHeaderName,
    apiParamName,
    setApiParamName,
    apiEnvVars,
    apiEnvFeedback,
    updateApiEnvVar,
    handleApiEnvValueChange,
    addApiEnvVar,
    handleSaveApiEnvVar,
    handleRemoveApiEnvVar,
    connectorConfigExists,
    connectorConfigOpen,
    connectorConfigLoading,
    connectorConfigSaving,
    connectorConfigError: _connectorConfigError,
    connectorConfigContent,
    setConnectorConfigContent,
    connectorConfigOriginal,
    connectorConfigDirty,
    canManageConnectorConfig,
    openConnectorConfigEditor,
    saveConnectorConfig,
    testStatus,
    handleTest,
    saveLoading,
    handleConnectNext,
    setFormError,
  } = state;

  const configButtonLabel = connectorConfigLoading
    ? connectorConfigExists
      ? "Opening..."
      : "Creating..."
    : connectorConfigExists
      ? "Edit"
      : "Create";

  return (
    <div
      className={`items-stretch gap-6 ${connectorConfigOpen ? "xl:grid xl:grid-cols-[minmax(0,1fr)_1px_420px]" : "max-w-4xl"}`}
    >
      <div className="space-y-6">
        {summaryCard}

        {/* Type selector */}
        <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
          <span className="text-sm font-medium text-gray-300">Type</span>
          <select
            value={connectorType}
            onChange={(event) => setConnectorType(event.target.value as typeof connectorType)}
            disabled={Boolean(existingName)}
            className="h-10 rounded-md border border-gray-700 bg-gray-950 px-3 text-sm text-white"
          >
            <option value="sql">Database</option>
            <option value="api">API</option>
            <option value="file">Files</option>
          </select>
        </div>

        {/* Name */}
        <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
          <span className="text-sm font-medium text-gray-300">Name</span>
          <Input
            value={connectionName}
            onChange={(event) => setConnectionName(event.target.value)}
            disabled={Boolean(existingName)}
            placeholder="my-connection"
            data-testid="connection-name-input"
            className="border-gray-700 bg-gray-950 text-white"
          />
        </div>

        {/* SQL fields */}
        {connectorType === "sql" && (
          <>
            <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
              <span className="text-sm font-medium text-gray-300">DB URL</span>
              <Input
                value={displayDatabaseUrl}
                onChange={(event) => {
                  setDisplayDatabaseUrl(event.target.value);
                  setDatabaseUrl(event.target.value);
                }}
                placeholder="trino://user:pass@host:443/catalog/schema"
                data-testid="connection-url-input"
                className="border-gray-700 bg-gray-950 font-mono text-white"
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
              <span className="text-sm font-medium text-gray-300">Config</span>
              <div className="flex flex-wrap items-center gap-3">
                {connectorConfigExists && (
                  <span className="text-sm text-gray-200">connector.yaml</span>
                )}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={openConnectorConfigEditor}
                  disabled={!canManageConnectorConfig || connectorConfigLoading}
                >
                  {configButtonLabel}
                </Button>
                {!canManageConnectorConfig && (
                  <span className="text-xs text-gray-500">Enter a connection name first.</span>
                )}
              </div>
            </div>
          </>
        )}

        {/* File fields */}
        {connectorType === "file" && (
          <>
            <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
              <span className="text-sm font-medium text-gray-300">Directory</span>
              <Input
                value={directory}
                onChange={(event) => setDirectory(event.target.value)}
                placeholder="/path/to/data"
                data-testid="connection-directory-input"
                className="border-gray-700 bg-gray-950 text-white"
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
              <span className="text-sm font-medium text-gray-300">Config</span>
              <div className="flex flex-wrap items-center gap-3">
                {connectorConfigExists && (
                  <span className="text-sm text-gray-200">connector.yaml</span>
                )}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={openConnectorConfigEditor}
                  disabled={!canManageConnectorConfig || connectorConfigLoading}
                >
                  {configButtonLabel}
                </Button>
                {!canManageConnectorConfig && (
                  <span className="text-xs text-gray-500">Enter a connection name first.</span>
                )}
              </div>
            </div>
          </>
        )}

        {/* API fields */}
        {connectorType === "api" && (
          <>
            {/* Preset */}
            <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
              <span className="text-sm font-medium text-gray-300">Preset</span>
              <div className="space-y-2">
                <select
                  value={apiTemplateId}
                  onChange={(event) => handleApiTemplateSelect(event.target.value)}
                  className="h-10 rounded-md border border-gray-700 bg-gray-950 px-3 text-sm text-white"
                >
                  <option value="">Custom</option>
                  {apiTemplates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.title}
                    </option>
                  ))}
                </select>
                {selectedApiTemplate && (
                  <p className="text-xs text-gray-500">{selectedApiTemplate.description}</p>
                )}
              </div>
            </div>

            {/* Base URL */}
            <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
              <span className="text-sm font-medium text-gray-300">Base URL</span>
              <Input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder={selectedApiTemplate?.baseUrl || "https://api.example.com/v1"}
                data-testid="connection-url-input"
                className="border-gray-700 bg-gray-950 text-white"
              />
            </div>

            {/* Auth */}
            <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-start">
              <span className="pt-2 text-sm font-medium text-gray-300">Auth</span>
              <div className="space-y-3">
                <div className="grid gap-3 md:grid-cols-3">
                  <select
                    value={apiAuthType}
                    onChange={(event) => handleApiAuthTypeChange(event.target.value)}
                    disabled={Boolean(apiTemplateId)}
                    className="h-10 rounded-md border border-gray-700 bg-gray-950 px-3 text-sm text-white disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <option value="none">None</option>
                    <option value="bearer">Bearer</option>
                    <option value="header">Header</option>
                    <option value="query_param">Query param</option>
                    <option value="basic">Basic</option>
                  </select>
                  {apiAuthType === "none" ? (
                    <div className="md:col-span-2 flex items-center text-sm text-gray-500">
                      No auth headers or tokens required.
                    </div>
                  ) : apiAuthType === "header" ? (
                    <>
                      <Input
                        value={apiHeaderName}
                        onChange={(event) => setApiHeaderName(event.target.value)}
                        placeholder="x-api-key"
                        disabled={Boolean(apiTemplateId)}
                        className="border-gray-700 bg-gray-950 text-white disabled:cursor-not-allowed disabled:opacity-60"
                      />
                      <div className="flex items-center rounded-md border border-gray-800 bg-gray-950 px-3 text-sm text-gray-500">
                        Credentials come from the env rows below.
                      </div>
                    </>
                  ) : apiAuthType === "query_param" ? (
                    <>
                      <Input
                        value={apiParamName}
                        onChange={(event) => setApiParamName(event.target.value)}
                        placeholder="api_key"
                        disabled={Boolean(apiTemplateId)}
                        className="border-gray-700 bg-gray-950 text-white disabled:cursor-not-allowed disabled:opacity-60"
                      />
                      <div className="flex items-center rounded-md border border-gray-800 bg-gray-950 px-3 text-sm text-gray-500">
                        Credentials come from the env rows below.
                      </div>
                    </>
                  ) : apiAuthType === "basic" ? (
                    <div className="md:col-span-2 flex items-center rounded-md border border-gray-800 bg-gray-950 px-3 text-sm text-gray-500">
                      Username and password/token are taken from the env rows below.
                    </div>
                  ) : (
                    <div className="md:col-span-2 flex items-center rounded-md border border-gray-800 bg-gray-950 px-3 text-sm text-gray-500">
                      Uses an Authorization bearer token from the env rows below.
                    </div>
                  )}
                </div>
                {selectedApiTemplate && (
                  <p className="text-xs text-gray-500">
                    {selectedApiTemplate.title} locks auth type and protocol details so the wizard
                    stays aligned with the generated connector.yaml.
                  </p>
                )}
              </div>
            </div>

            {/* Config */}
            <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-start">
              <span className="pt-2 text-sm font-medium text-gray-300">Config</span>
              <div className="flex flex-wrap items-center gap-3">
                {connectorConfigExists && (
                  <span className="text-sm text-gray-200">connector.yaml</span>
                )}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={openConnectorConfigEditor}
                  disabled={!canManageConnectorConfig || connectorConfigLoading}
                >
                  {configButtonLabel}
                </Button>
                {!canManageConnectorConfig && (
                  <span className="text-xs text-gray-500">Enter a connection name first.</span>
                )}
              </div>
            </div>

            {/* Env vars */}
            <div className="grid gap-4 sm:grid-cols-[180px_1fr] sm:items-start">
              <span className="pt-2 text-sm font-medium text-gray-300">Env</span>
              <div className="space-y-3">
                {apiEnvVars.length === 0 ? (
                  <div className="rounded-md border border-dashed border-gray-800 bg-gray-950 px-3 py-2 text-sm text-gray-500">
                    No env vars required for this auth mode.
                  </div>
                ) : (
                  apiEnvVars.map((entry, index) => {
                    const rowState = getApiEnvRowState(entry);
                    return (
                      <div key={`${entry.slot || "env"}-${index}`} className="space-y-1">
                        <p className="text-xs text-gray-500">
                          {entry.prompt || entry.slot || "Environment variable"}
                        </p>
                        <div className="grid gap-2 md:grid-cols-[minmax(0,180px)_minmax(0,1fr)_auto]">
                          <Input
                            value={entry.name}
                            onChange={(event) =>
                              updateApiEnvVar(index, {
                                name: event.target.value,
                                removed: false,
                              })
                            }
                            placeholder={entry.slot || "API_KEY"}
                            className="border-gray-700 bg-gray-950 text-white"
                          />
                          <Input
                            type={entry.secret ? "password" : "text"}
                            value={rowState.displayValue}
                            onChange={(event) =>
                              handleApiEnvValueChange(index, event.target.value)
                            }
                            placeholder={rowState.placeholder}
                            className="border-gray-700 bg-gray-950 text-white"
                          />
                          <div className="flex items-center gap-2">
                            {rowState.primaryActionLabel && !rowState.isSaved && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => void handleSaveApiEnvVar(index)}
                                disabled={!entry.value?.trim()}
                              >
                                {rowState.primaryActionLabel}
                              </Button>
                            )}
                            {rowState.showTrash && (
                              <Button
                                type="button"
                                variant="outline"
                                size="icon"
                                onClick={() => void handleRemoveApiEnvVar(index)}
                                aria-label={`Remove ${entry.name || entry.slot || "environment variable"}`}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={addApiEnvVar}
                  aria-label="Add environment variable"
                  className="w-fit"
                >
                  <Plus className="h-4 w-4" />
                </Button>
                {apiEnvFeedback && (
                  <p className="text-xs text-emerald-300">{apiEnvFeedback}</p>
                )}
              </div>
            </div>
          </>
        )}

        {/* Test */}
        <div className="flex flex-wrap gap-3">
          <Button onClick={handleTest} disabled={testStatus?.testing}>
            {testStatus?.testing ? "Testing..." : "Test"}
          </Button>
          <Button
            variant="outline"
            onClick={() =>
              setFormError(
                "Double-check credentials, network reachability, and connector-specific SSL options.",
              )
            }
          >
            Troubleshooting
          </Button>
        </div>

        <div className="rounded-xl border border-gray-800 bg-gray-950/80 p-4 text-sm text-gray-300">
          <p>{testStatus?.message || "Run a connection test to validate the setup."}</p>
          {testStatus?.hint && <p className="mt-2 text-amber-300">{testStatus.hint}</p>}
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 text-sm text-gray-300">
            <span>Result:</span>
            <span>
              {testStatus?.success === true
                ? "Successfully connected"
                : testStatus?.success === false
                  ? "Needs attention"
                  : "Pending"}
            </span>
          </div>
          <Button onClick={handleConnectNext} disabled={saveLoading}>
            {saveLoading ? "Saving..." : "Next >"}
          </Button>
        </div>
      </div>

      {/* connector.yaml inline editor panel */}
      {connectorConfigOpen && (
        <>
          <div className="hidden xl:block w-px self-stretch bg-gray-800" />
          <div className="flex min-h-full flex-col space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-white">connector.yaml</p>
                <p className="text-xs text-gray-500">Connection-specific configuration</p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setConnectorConfigContent(connectorConfigOriginal)}
                  disabled={!connectorConfigDirty || connectorConfigSaving}
                >
                  Discard
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={saveConnectorConfig}
                  disabled={!connectorConfigDirty || connectorConfigSaving}
                >
                  {connectorConfigSaving ? "Saving..." : "Save"}
                </Button>
              </div>
            </div>
            <div className="flex-1 rounded-xl border border-gray-800 bg-gray-950/80">
              <textarea
                value={connectorConfigContent}
                onChange={(event) => setConnectorConfigContent(event.target.value)}
                spellCheck={false}
                className="h-full min-h-[44rem] w-full resize-none bg-transparent px-4 py-4 font-mono text-sm text-gray-200 outline-none"
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
