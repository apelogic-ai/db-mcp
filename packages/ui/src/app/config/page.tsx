"use client";

import Link from "next/link";
import AgentConfig from "@/components/AgentConfig";
import { Button } from "@/components/ui/button";

export default function ConfigPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Configuration</h1>
          <p className="mt-1 text-gray-400">
            Manage agent integration. Connections now live under the dedicated
            connections workspace.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/connections">Open Connections</Link>
        </Button>
      </div>

      <AgentConfig />
    </div>
  );
}
