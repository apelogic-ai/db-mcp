"use client";

import { Suspense } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { ConnectionDetailPageClient } from "@/features/connections/ConnectionDetailPageClient";
import { resolveConnectionName } from "@/features/connections/utils";

function ConnectionInsightsPageContent() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const name = resolveConnectionName(pathname, searchParams);

  if (!name) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-gray-400">
        Select a connection from the connections list.
      </div>
    );
  }

  return <ConnectionDetailPageClient name={name} view="insights" />;
}

export default function ConnectionInsightsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center text-gray-400">
          Loading connection...
        </div>
      }
    >
      <ConnectionInsightsPageContent />
    </Suspense>
  );
}
