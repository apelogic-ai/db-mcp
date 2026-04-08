/**
 * Shipper — cursor-based idempotent trace shipping.
 *
 * Tracks the last-shipped byte offset per file. On each processFile()
 * call, reads only new lines, optionally redacts secrets, and calls
 * the ship callback with a batch of raw (redacted) JSONL lines.
 */

import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  statSync,
} from "node:fs";
import { join, basename } from "node:path";
import { createHash } from "node:crypto";
import { redactSecrets } from "./security/scanner";

export interface ShippedBatch {
  agent: string;
  project: string;
  sourceFile: string;
  entries: string[];
}

export interface ShipperConfig {
  stateDir: string;
  redactSecrets?: boolean;
  ship: (batch: ShippedBatch) => Promise<void>;
}

type CursorMap = Record<string, number>; // fileHash → byte offset

function fileHash(path: string): string {
  return createHash("sha256").update(path).digest("hex").slice(0, 16);
}

export class Shipper {
  private config: ShipperConfig;
  private cursors: CursorMap;
  private cursorFile: string;

  constructor(config: ShipperConfig) {
    this.config = config;
    this.cursorFile = join(config.stateDir, "shipper-cursors.json");
    this.cursors = this.loadCursors();
  }

  private loadCursors(): CursorMap {
    if (existsSync(this.cursorFile)) {
      try {
        return JSON.parse(readFileSync(this.cursorFile, "utf-8"));
      } catch {
        return {};
      }
    }
    return {};
  }

  private saveCursors(): void {
    mkdirSync(this.config.stateDir, { recursive: true });
    writeFileSync(this.cursorFile, JSON.stringify(this.cursors, null, 2));
  }

  /**
   * Process a trace file — read new lines since last cursor, redact
   * secrets if configured, and ship the batch.
   */
  processFile(filePath: string, agent: string, project: string): void {
    if (!existsSync(filePath)) return;

    const key = fileHash(filePath);
    const cursor = this.cursors[key] ?? 0;
    const stat = statSync(filePath);

    if (stat.size <= cursor) return; // nothing new

    // Read from cursor to end
    const content = readFileSync(filePath, "utf-8");
    const newContent = content.slice(cursor);
    const lines = newContent.split("\n").filter((l) => l.trim());

    if (lines.length === 0) {
      this.cursors[key] = stat.size;
      this.saveCursors();
      return;
    }

    // Validate JSON + optionally redact
    const validEntries: string[] = [];
    for (const line of lines) {
      try {
        JSON.parse(line); // validate
        const processed = this.config.redactSecrets
          ? redactSecrets(line)
          : line;
        validEntries.push(processed);
      } catch {
        // Skip invalid JSON lines
      }
    }

    if (validEntries.length === 0) {
      this.cursors[key] = stat.size;
      this.saveCursors();
      return;
    }

    // Ship
    const batch: ShippedBatch = {
      agent,
      project,
      sourceFile: filePath,
      entries: validEntries,
    };

    // Note: processFile is sync for simplicity. The ship callback
    // is async but we fire-and-forget here. A production shipper
    // would await and retry on failure.
    this.config.ship(batch);

    // Update cursor
    this.cursors[key] = stat.size;
    this.saveCursors();
  }
}
