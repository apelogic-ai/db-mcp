"use client";

import { Button } from "@/components/ui/button";
import { hasDiscoveryData } from "./useWizardState";
import type { WizardState } from "./useWizardState";

type Props = {
  state: WizardState;
  summaryCard: React.ReactNode;
};

export function DiscoverStepContent({ state, summaryCard }: Props) {
  const { discoverState, runDiscovery, navigateToStep } = state;

  const isLoading = discoverState.status === "loading";
  const hasData = hasDiscoveryData(discoverState);

  return (
    <div className="max-w-4xl space-y-6">
      {summaryCard}

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={runDiscovery} disabled={isLoading}>
          {isLoading
            ? hasData
              ? "Re-discovering..."
              : "Discovering..."
            : hasData
              ? "Re-discover"
              : "Discover"}
        </Button>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-950/80 p-4">
        <div className="space-y-2 text-sm text-gray-300">
          {discoverState.logs.map((entry) => (
            <p key={entry}>{entry}</p>
          ))}
          {discoverState.errors.map((entry) => (
            <p key={entry} className="text-amber-300">
              {entry}
            </p>
          ))}
          {discoverState.logs.length === 0 && <p>No discovery data is available yet.</p>}
        </div>
      </div>

      <div className="flex flex-wrap gap-6 text-sm text-gray-300">
        {discoverState.catalogCount !== undefined && (
          <span>{discoverState.catalogCount} catalogs</span>
        )}
        {discoverState.schemaCount !== undefined && (
          <span>{discoverState.schemaCount} schemas</span>
        )}
        {discoverState.tableCount !== undefined && (
          <span>{discoverState.tableCount} tables</span>
        )}
        {discoverState.endpointCount !== undefined && (
          <span>{discoverState.endpointCount} endpoints</span>
        )}
      </div>

      <div className="flex items-center justify-between">
        <Button variant="outline" onClick={() => navigateToStep("connect")}>
          &lt; Previous
        </Button>
        <Button
          onClick={() => navigateToStep("sample")}
          disabled={discoverState.status === "idle" || discoverState.status === "loading"}
        >
          Next &gt;
        </Button>
      </div>
    </div>
  );
}
