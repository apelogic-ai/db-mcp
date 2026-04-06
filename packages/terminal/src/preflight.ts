/**
 * Preflight utilities for checking system prerequisites.
 */
import { existsSync } from "node:fs";
import { join } from "node:path";

/** Check if a binary exists on PATH. Returns the full path or null. */
export function which(name: string): string | null {
  const pathDirs = (process.env.PATH ?? "").split(":");
  for (const dir of pathDirs) {
    const candidate = join(dir, name);
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}
