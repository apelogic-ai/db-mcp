/**
 * Store — persists received batches to the lakehouse (local filesystem).
 *
 * Layout:
 *   {dataDir}/raw/{agent}/{timestamp}-{developer}-{agent}.jsonl   (entries)
 *   {dataDir}/raw/{agent}/{timestamp}-{developer}-{agent}.meta.json (metadata)
 *
 * In production, this would write to S3. The local filesystem version
 * is the development/testing stand-in with the same interface.
 */

import { mkdirSync, writeFileSync, readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

export interface StoredBatch {
  batchId?: string;     // deterministic ID from agent — used for dedup
  developer: string;
  machine: string;
  agent: string;
  project: string;
  sourceFile: string;
  shippedAt: string;
  receivedAt: string;
  entries: string[];
}

export interface SaveResult {
  entryCount: number;
  filePath: string;
  duplicate?: boolean;
}

export interface BatchMeta {
  developer: string;
  machine: string;
  agent: string;
  project: string;
  shippedAt: string;
  receivedAt: string;
  entryCount: number;
  filePath: string;
}

function sanitize(s: string): string {
  return s.replace(/[^a-zA-Z0-9_@.\-]/g, "_").slice(0, 40);
}

export class Store {
  private dataDir: string;
  private seenBatchIds: Set<string>;

  constructor(dataDir: string) {
    this.dataDir = dataDir;
    this.seenBatchIds = this.loadSeenBatchIds();
  }

  private loadSeenBatchIds(): Set<string> {
    const dedupFile = join(this.dataDir, "dedup.json");
    if (existsSync(dedupFile)) {
      try {
        const ids = JSON.parse(readFileSync(dedupFile, "utf-8")) as string[];
        return new Set(ids);
      } catch { /* start fresh */ }
    }
    return new Set();
  }

  private saveSeenBatchIds(): void {
    mkdirSync(this.dataDir, { recursive: true });
    const dedupFile = join(this.dataDir, "dedup.json");
    // Keep last 10K IDs to bound memory
    const ids = [...this.seenBatchIds].slice(-10_000);
    writeFileSync(dedupFile, JSON.stringify(ids));
  }

  /**
   * Check if a batch was already received (by batchId).
   */
  isDuplicate(batchId: string | undefined): boolean {
    if (!batchId) return false;
    return this.seenBatchIds.has(batchId);
  }

  saveBatch(batch: StoredBatch): SaveResult {
    // Dedup by batchId
    if (batch.batchId && this.seenBatchIds.has(batch.batchId)) {
      return { entryCount: 0, filePath: "", duplicate: true };
    }

    const agentDir = join(this.dataDir, "raw", batch.agent);
    mkdirSync(agentDir, { recursive: true });

    const ts = batch.shippedAt.replace(/[:.]/g, "-").slice(0, 19);
    const dev = sanitize(batch.developer);
    const baseName = `${ts}-${dev}-${batch.agent}`;

    // Write entries as JSONL
    const entriesPath = join(agentDir, `${baseName}.jsonl`);
    writeFileSync(entriesPath, batch.entries.join("\n") + "\n");

    // Write metadata
    const meta: BatchMeta = {
      developer: batch.developer,
      machine: batch.machine,
      agent: batch.agent,
      project: batch.project,
      shippedAt: batch.shippedAt,
      receivedAt: batch.receivedAt,
      entryCount: batch.entries.length,
      filePath: entriesPath,
    };
    writeFileSync(
      join(agentDir, `${baseName}.meta.json`),
      JSON.stringify(meta, null, 2),
    );

    // Track batchId for dedup
    if (batch.batchId) {
      this.seenBatchIds.add(batch.batchId);
      this.saveSeenBatchIds();
    }

    return {
      entryCount: batch.entries.length,
      filePath: entriesPath,
    };
  }

  listBatches(): BatchMeta[] {
    const rawDir = join(this.dataDir, "raw");
    if (!existsSync(rawDir)) return [];

    const metas: BatchMeta[] = [];
    for (const agentDir of readdirSync(rawDir)) {
      const fullDir = join(rawDir, agentDir);
      for (const file of readdirSync(fullDir)) {
        if (!file.endsWith(".meta.json")) continue;
        try {
          const meta = JSON.parse(
            readFileSync(join(fullDir, file), "utf-8"),
          ) as BatchMeta;
          metas.push(meta);
        } catch { /* skip malformed */ }
      }
    }
    return metas;
  }
}
