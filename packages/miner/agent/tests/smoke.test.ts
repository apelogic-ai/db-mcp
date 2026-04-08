/**
 * Smoke tests against real agent trace data on this machine.
 * These tests read actual trace files — they skip if the data isn't present.
 */

import { describe, it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { discoverTraceSources } from "../src/discover";
import { parseClaudeEntry } from "../src/parsers/claude";
import { parseCodexEntry } from "../src/parsers/codex";
import { scanForSecrets } from "../src/security/scanner";

const CLAUDE_DIR = join(homedir(), ".claude");
const CODEX_DIR = join(homedir(), ".codex");

const hasClaude = existsSync(join(CLAUDE_DIR, "projects"));
const hasCodex = existsSync(join(CODEX_DIR, "sessions"));

describe("Smoke: discovery", () => {
  it("finds real sources on this machine", () => {
    const sources = discoverTraceSources({
      claudeCodeDir: CLAUDE_DIR,
      codexDir: CODEX_DIR,
    });

    if (!hasClaude && !hasCodex) {
      expect(sources).toEqual([]);
      return;
    }

    expect(sources.length).toBeGreaterThan(0);
    console.log(`  Found ${sources.length} source(s):`);
    for (const s of sources) {
      console.log(`    ${s.agent} / ${s.project}: ${s.files.length} file(s)`);
    }
  });
});

describe.skipIf(!hasClaude)("Smoke: Claude Code parser", () => {
  it("parses real Claude Code traces", () => {
    const sources = discoverTraceSources({ claudeCodeDir: CLAUDE_DIR });
    const firstSource = sources.find((s) => s.files.length > 0);
    if (!firstSource) return;

    const file = firstSource.files[0];
    const content = readFileSync(file, "utf-8");
    const lines = content.split("\n").filter((l) => l.trim()).slice(0, 50);

    let parsed = 0;
    let skipped = 0;
    const entryTypes: Record<string, number> = {};

    for (const line of lines) {
      try {
        const raw = JSON.parse(line);
        const entry = parseClaudeEntry(raw, "smoke-test");
        if (entry) {
          parsed++;
          entryTypes[entry.entryType] = (entryTypes[entry.entryType] ?? 0) + 1;
        } else {
          skipped++;
        }
      } catch {
        skipped++;
      }
    }

    console.log(`  Parsed ${parsed}/${lines.length} entries (${skipped} skipped)`);
    console.log(`  Entry types: ${JSON.stringify(entryTypes)}`);
    expect(parsed).toBeGreaterThan(0);
  });

  it("detects secrets in real Claude Code traces", () => {
    const sources = discoverTraceSources({ claudeCodeDir: CLAUDE_DIR });
    const allFiles = sources.flatMap((s) => s.files);

    let totalLines = 0;
    let totalFindings = 0;
    const findingTypes: Record<string, number> = {};

    for (const file of allFiles.slice(0, 5)) { // limit to 5 files
      const content = readFileSync(file, "utf-8");
      const lines = content.split("\n").filter((l) => l.trim());
      totalLines += lines.length;

      for (const line of lines) {
        const findings = scanForSecrets(line);
        totalFindings += findings.length;
        for (const f of findings) {
          findingTypes[f.type] = (findingTypes[f.type] ?? 0) + 1;
        }
      }
    }

    console.log(`  Scanned ${totalLines} lines across ${Math.min(allFiles.length, 5)} files`);
    console.log(`  Findings: ${totalFindings}`);
    if (totalFindings > 0) {
      console.log(`  Types: ${JSON.stringify(findingTypes)}`);
    }
    // Don't assert on finding count — clean machines may have none
  });
});

describe.skipIf(!hasCodex)("Smoke: Codex parser", () => {
  it("parses real Codex traces", () => {
    const sources = discoverTraceSources({ codexDir: CODEX_DIR });
    const firstSource = sources.find((s) => s.files.length > 0);
    if (!firstSource) return;

    // Pick a recent file
    const file = firstSource.files[firstSource.files.length - 1];
    const content = readFileSync(file, "utf-8");
    const lines = content.split("\n").filter((l) => l.trim()).slice(0, 50);

    let parsed = 0;
    let skipped = 0;
    const entryTypes: Record<string, number> = {};

    for (const line of lines) {
      try {
        const raw = JSON.parse(line);
        const entry = parseCodexEntry(raw, "smoke-test");
        if (entry) {
          parsed++;
          entryTypes[entry.entryType] = (entryTypes[entry.entryType] ?? 0) + 1;
        } else {
          skipped++;
        }
      } catch {
        skipped++;
      }
    }

    console.log(`  Parsed ${parsed}/${lines.length} entries (${skipped} skipped)`);
    console.log(`  Entry types: ${JSON.stringify(entryTypes)}`);
    expect(parsed).toBeGreaterThan(0);
  });
});
