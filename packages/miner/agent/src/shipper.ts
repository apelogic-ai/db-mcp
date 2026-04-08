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
import { join } from "node:path";
import { createHash } from "node:crypto";
import { hostname } from "node:os";
import { execSync } from "node:child_process";
import { redactSecrets } from "./security/scanner";

export interface ShippedBatch {
  batchId: string;      // deterministic: hash(filePath + cursor + entryCount)
  developer: string;
  machine: string;
  agent: string;
  project: string;
  sourceFile: string;
  shippedAt: string;
  entries: string[];
}

export interface ShipperConfig {
  developer?: string;  // explicit override; defaults to git config user.email
  machine?: string;    // machine identifier; defaults to os.hostname()
  stateDir: string;
  redactSecrets?: boolean;
  ship: (batch: ShippedBatch) => Promise<void>;
}

type CursorMap = Record<string, number>; // fileHash → byte offset

function fileHash(path: string): string {
  return createHash("sha256").update(path).digest("hex").slice(0, 16);
}

/**
 * Resolve developer identity. Priority:
 * 1. Explicit config value
 * 2. git config user.email
 * 3. git config user.name
 * 4. OS username
 */
function resolveDeveloper(explicit?: string): string {
  if (explicit) return explicit;
  try {
    const email = execSync("git config --global user.email", {
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
    if (email) return email;
  } catch { /* no git or no config */ }
  try {
    const name = execSync("git config --global user.name", {
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
    if (name) return name;
  } catch { /* no git or no config */ }
  return process.env.USER ?? process.env.USERNAME ?? "unknown";
}

export class Shipper {
  private config: ShipperConfig;
  private cursors: CursorMap;
  private cursorFile: string;
  readonly developer: string;
  readonly machine: string;

  constructor(config: ShipperConfig) {
    this.config = config;
    this.developer = resolveDeveloper(config.developer);
    this.machine = config.machine ?? hostname();
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
   * secrets if configured, ship the batch, and advance cursor only
   * on successful shipment.
   */
  async processFile(filePath: string, agent: string, project: string): Promise<boolean> {
    if (!existsSync(filePath)) return false;

    const key = fileHash(filePath);
    const cursor = this.cursors[key] ?? 0;
    const stat = statSync(filePath);

    if (stat.size <= cursor) return false; // nothing new

    // Read from cursor to end
    const content = readFileSync(filePath, "utf-8");
    const newContent = content.slice(cursor);
    const lines = newContent.split("\n").filter((l) => l.trim());

    if (lines.length === 0) {
      this.cursors[key] = stat.size;
      this.saveCursors();
      return false;
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
      return false;
    }

    // Deterministic batch ID for ingestor-side dedup
    const batchId = createHash("sha256")
      .update(`${filePath}:${cursor}:${stat.size}:${validEntries.length}`)
      .digest("hex")
      .slice(0, 16);

    const batch: ShippedBatch = {
      batchId,
      developer: this.developer,
      machine: this.machine,
      agent,
      project,
      sourceFile: filePath,
      shippedAt: new Date().toISOString(),
      entries: validEntries,
    };

    // Ship — only advance cursor on success
    try {
      await this.config.ship(batch);
      this.cursors[key] = stat.size;
      this.saveCursors();
      return true;
    } catch {
      // Ship failed — cursor NOT advanced, will retry on next poll
      return false;
    }
  }
}
