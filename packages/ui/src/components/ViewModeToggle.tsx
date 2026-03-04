"use client";

import { cn } from "@/lib/utils";
import { useViewMode } from "@/lib/view-mode-context";

export function ViewModeToggle() {
  const { viewMode, setViewMode } = useViewMode();

  return (
    <div
      className="inline-flex h-8 items-center rounded-md border border-gray-700 bg-gray-900 p-0.5"
      role="group"
      aria-label="View mode"
    >
      <button
        type="button"
        onClick={() => setViewMode("essentials")}
        className={cn(
          "rounded px-2 py-1 text-xs font-medium transition-colors",
          viewMode === "essentials"
            ? "bg-gray-800 text-white"
            : "text-gray-400 hover:text-gray-200",
        )}
      >
        Essentials
      </button>
      <button
        type="button"
        onClick={() => setViewMode("advanced")}
        className={cn(
          "rounded px-2 py-1 text-xs font-medium transition-colors",
          viewMode === "advanced"
            ? "bg-gray-800 text-white"
            : "text-gray-400 hover:text-gray-200",
        )}
      >
        Advanced
      </button>
    </div>
  );
}
