"use client";

import Link from "next/link";
import { SchemaExplorer } from "@/components/context/SchemaExplorer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { normalizeDbSegment, parseDbLink } from "./utils";
import type { WizardState } from "./useWizardState";

type Props = {
  state: WizardState;
  summaryCard: React.ReactNode;
};

export function SchemaStepContent({ state, summaryCard }: Props) {
  const {
    connectorType,
    currentName,
    discoverState,
    sampleLogs,
    sampleError,
    sampleRows,
    sampleLoading,
    selectedEndpoint,
    setSelectedEndpoint,
    setSampleSelection,
    handleSampleData,
    navigateToStep,
    queryPreview,
  } = state;

  return (
    <div className="space-y-6">
      <div className="items-start gap-4 xl:grid xl:grid-cols-[max-content_1px_minmax(0,1fr)]">
        <div className="space-y-6">
          {summaryCard}
          <div className="space-y-6 max-w-4xl">
            {/* Sample log + data panel */}
            <div className="rounded-xl border border-gray-800 bg-gray-950/80 p-4">
              <h2 className="text-lg font-semibold text-white">Sample data</h2>
              <div className="mt-4 space-y-2 text-sm text-gray-300">
                {sampleLogs.map((entry) => (
                  <p key={entry}>{entry}</p>
                ))}
                {sampleError && <p className="text-red-300">{sampleError}</p>}
                {!sampleLogs.length && !sampleError && (
                  <p>Select a table or endpoint, then fetch the first sample.</p>
                )}
              </div>

              {connectorType === "api" ? (
                <div className="mt-4 space-y-3">
                  {(discoverState.endpoints || []).map((endpoint) => (
                    <label
                      key={endpoint.name}
                      className="flex items-center justify-between rounded-lg border border-gray-800 px-3 py-2 text-sm text-gray-200"
                    >
                      <span>
                        <span className="font-medium">{endpoint.name}</span>
                        <span className="ml-2 text-gray-500">{endpoint.path}</span>
                      </span>
                      <input
                        type="radio"
                        name="endpoint"
                        checked={selectedEndpoint === endpoint.name}
                        onChange={() => setSelectedEndpoint(endpoint.name)}
                      />
                    </label>
                  ))}
                </div>
              ) : sampleRows.length > 0 ? (
                <div className="mt-4 overflow-x-auto rounded-lg border border-gray-800">
                  <table className="min-w-full divide-y divide-gray-800 text-sm">
                    <thead className="bg-gray-950">
                      <tr>
                        {Object.keys(sampleRows[0] || {}).map((column) => (
                          <th
                            key={column}
                            className="px-3 py-2 text-left font-medium text-gray-400"
                          >
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800">
                      {sampleRows.map((row, rowIndex) => (
                        <tr key={rowIndex}>
                          {Object.keys(sampleRows[0] || {}).map((column) => (
                            <td
                              key={`${rowIndex}-${column}`}
                              className="px-3 py-2 text-gray-200"
                            >
                              {String(row[column] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>

            {/* Selection preview + action */}
            <div className="flex items-start gap-6">
              <div className="min-w-0 flex-1 rounded-xl border border-gray-800 bg-gray-950/80 p-4">
                <p className="text-sm font-medium text-white">Selection</p>
                <pre className="mt-3 whitespace-pre-wrap text-sm text-gray-300">
                  {queryPreview}
                </pre>
              </div>
              <Button onClick={handleSampleData} disabled={sampleLoading}>
                {sampleLoading ? "Sampling..." : "Sample Data"}
              </Button>
            </div>

            {/* Navigation */}
            <div className="flex items-center justify-between">
              <Button variant="outline" onClick={() => navigateToStep("discover")}>
                &lt; Previous
              </Button>
              <Button asChild>
                <Link href={`/connection/${encodeURIComponent(currentName)}`}>Done</Link>
              </Button>
            </div>
          </div>
        </div>

        {/* Right panel: endpoints list (API) or schema explorer (SQL/file) */}
        {connectorType === "api" ? (
          <>
            <div className="hidden xl:block w-px self-stretch bg-gray-800" />
            <Card className="h-full border-gray-800 bg-gray-950/80">
              <CardHeader>
                <CardTitle className="text-white">Discovered endpoints</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-gray-300">
                {(discoverState.endpoints || []).map((endpoint) => (
                  <div
                    key={endpoint.name}
                    className="rounded-lg border border-gray-800 px-3 py-2"
                  >
                    <p className="font-medium text-white">{endpoint.name}</p>
                    <p className="text-gray-500">{endpoint.path}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          </>
        ) : (
          <>
            <div className="hidden xl:block w-px self-stretch bg-gray-800" />
            <div className="min-h-[44rem] min-w-0 overflow-hidden rounded-xl border border-gray-800 bg-gray-950/80 xl:h-full">
              <SchemaExplorer
                isOpen
                onClose={() => {}}
                onInsertLink={(link) => {
                  const nextSelection = parseDbLink(link);
                  if (!nextSelection.table) {
                    return;
                  }
                  setSampleSelection({
                    catalog: normalizeDbSegment(nextSelection.catalog),
                    schema: normalizeDbSegment(nextSelection.schema),
                    table: normalizeDbSegment(nextSelection.table),
                  });
                }}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
