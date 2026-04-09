/**
 * Store — persists received batches to the lakehouse.
 *
 * Hive-style partitioned layout:
 *   {dataDir}/raw/year=YYYY/month=MM/day=DD/agent=X/dev=HASH/{batchId}.jsonl
 *   {dataDir}/raw/year=YYYY/month=MM/day=DD/agent=X/dev=HASH/{batchId}.meta.json
 *
 * Partitioned by: date (ship date), agent, developer (SHA-256 prefix for privacy).
 *
 * All files are immutable (write-once, never updated).
 * Dedup state is append-only (one ID per line in dedup.log).
 *
 * Cross-boundary sessions: a session spanning midnight (or month boundary)
 * ships as one batch partitioned by shippedAt. The normalized Parquet zone
 * (built by a downstream batch job) uses per-entry timestamps for accurate
 * time-range queries.
 *
 * In production, maps to S3:
 *   s3://bucket/raw/year=2026/month=04/day=08/agent=claude_code/dev=a1b2c3d4/{batchId}.jsonl
 */

import { mkdirSync, writeFileSync, readdirSync, readFileSync, existsSync, appendFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";

export interface StoredBatch {
  batchId?: string;
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
  batchId: string;
  developer: string;
  machine: string;
  agent: string;
  project: string;
  shippedAt: string;
  receivedAt: string;
  entryCount: number;
  filePath: string;
}

export class Store {
  private dataDir: string;
  private seenBatchIds: Set<string>;
  private dedupLogPath: string;

  constructor(dataDir: string) {
    this.dataDir = dataDir;
    this.dedupLogPath = join(dataDir, "dedup.log");
    this.seenBatchIds = this.loadSeenBatchIds();
  }

  /**
   * Load seen batch IDs from the append-only dedup log.
   * One batchId per line — no JSON parsing, no rewrite.
   */
  private loadSeenBatchIds(): Set<string> {
    if (!existsSync(this.dedupLogPath)) return new Set();
    try {
      const content = readFileSync(this.dedupLogPath, "utf-8");
      const ids = content.split("\n").filter((l) => l.trim());
      return new Set(ids);
    } catch {
      return new Set();
    }
  }

  /**
   * Append a batchId to the dedup log (append-only, no rewrite).
   */
  private recordBatchId(batchId: string): void {
    mkdirSync(this.dataDir, { recursive: true });
    appendFileSync(this.dedupLogPath, batchId + "\n");
    this.seenBatchIds.add(batchId);
  }

  isDuplicate(batchId: string | undefined): boolean {
    if (!batchId) return false;
    return this.seenBatchIds.has(batchId);
  }

  saveBatch(batch: StoredBatch): SaveResult {
    // Generate batchId if not provided
    const batchId = batch.batchId ?? createHash("sha256")
      .update(`${batch.developer}:${batch.shippedAt}:${batch.entries.length}:${Date.now()}`)
      .digest("hex")
      .slice(0, 16);

    // Dedup
    if (this.seenBatchIds.has(batchId)) {
      return { entryCount: 0, filePath: "", duplicate: true };
    }

    // Parse date for partitioning
    const date = new Date(batch.shippedAt || batch.receivedAt);
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, "0");
    const day = String(date.getUTCDate()).padStart(2, "0");

    // Developer partition key — hash for privacy, or raw for internal use
    const devKey = createHash("sha256")
      .update(batch.developer)
      .digest("hex")
      .slice(0, 12);

    // Hive-style partitioned path: date + agent + developer
    const partitionDir = join(
      this.dataDir, "raw",
      `year=${year}`,
      `month=${month}`,
      `day=${day}`,
      `agent=${batch.agent}`,
      `dev=${devKey}`,
    );
    mkdirSync(partitionDir, { recursive: true });

    // Immutable files named by batchId (guaranteed unique)
    const entriesPath = join(partitionDir, `${batchId}.jsonl`);
    writeFileSync(entriesPath, batch.entries.join("\n") + "\n");

    const meta: BatchMeta = {
      batchId,
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
      join(partitionDir, `${batchId}.meta.json`),
      JSON.stringify(meta, null, 2),
    );

    // Append-only dedup record
    this.recordBatchId(batchId);

    return {
      entryCount: batch.entries.length,
      filePath: entriesPath,
    };
  }

  listBatches(): BatchMeta[] {
    const rawDir = join(this.dataDir, "raw");
    if (!existsSync(rawDir)) return [];
    return this.walkMeta(rawDir);
  }

  private walkMeta(dir: string): BatchMeta[] {
    const metas: BatchMeta[] = [];
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        metas.push(...this.walkMeta(join(dir, entry.name)));
      } else if (entry.name.endsWith(".meta.json")) {
        try {
          const meta = JSON.parse(
            readFileSync(join(dir, entry.name), "utf-8"),
          ) as BatchMeta;
          metas.push(meta);
        } catch { /* skip */ }
      }
    }
    return metas;
  }
}
