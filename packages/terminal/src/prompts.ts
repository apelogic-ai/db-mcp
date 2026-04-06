/**
 * Load prompt files from the prompts/ directory.
 */
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __promptsDir = dirname(fileURLToPath(import.meta.url));

/** Load a prompt file by name. Searches repo layout then bundle layout. */
export function loadPrompt(name: string): string {
  const candidates = [
    resolve(__promptsDir, "..", "prompts", name),   // repo: src/../prompts/
    resolve(__promptsDir, "prompts", name),          // bundle: terminal/prompts/
  ];
  for (const p of candidates) {
    try {
      return readFileSync(p, "utf8").trim();
    } catch {}
  }
  return "";
}
