import { Suspense } from "react";
import { ConnectionWizardPageClient } from "@/features/connections/ConnectionWizardPageClient";

export default function NewConnectionPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center text-gray-400">
          Loading setup wizard...
        </div>
      }
    >
      <ConnectionWizardPageClient />
    </Suspense>
  );
}
