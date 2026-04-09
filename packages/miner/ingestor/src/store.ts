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
  /** Per-developer dedup caches, loaded lazily. */
  private dedupByDev: Map<string, Set<string>> = new Map();

  constructor(dataDir: string) {
    this.dataDir = dataDir;
  }

  /**
   * Hash developer identity for partition key.
   */
  private devHash(developer: string): string {
    return createHash("sha256").update(developer).digest("hex").slice(0, 12);
  }

  /**
   * Get (or lazily load) the dedup set for a developer.
   * Each developer's dedup.log lives in their partition root.
   */
  private getDedupSet(devKey: string): Set<string> {
    if (this.dedupByDev.has(devKey)) {
      return this.dedupByDev.get(devKey)!;
    }

    // Scan all date partitions for this developer's dedup logs
    const ids = new Set<string>();
    const rawDir = join(this.dataDir, "raw");
    if (existsSync(rawDir)) {
      this.walkDedupLogs(rawDir, devKey, ids);
    }
    this.dedupByDev.set(devKey, ids);
    return ids;
  }

  private walkDedupLogs(dir: string, devKey: string, ids: Set<string>): void {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        this.walkDedupLogs(join(dir, entry.name), devKey, ids);
      } else if (entry.name === "dedup.log" && dir.includes(`dev=${devKey}`)) {
        try {
          const content = readFileSync(join(dir, entry.name), "utf-8");
          for (const line of content.split("\n")) {
            if (line.trim()) ids.add(line.trim());
          }
        } catch { /* skip */ }
      }
    }
  }

  /**
   * Record a batchId in the developer's partition dedup log.
   */
  private recordBatchId(batchId: string, partitionDir: string, devKey: string): void {
    appendFileSync(join(partitionDir, "dedup.log"), batchId + "\n");
    this.getDedupSet(devKey).add(batchId);
  }

  isDuplicate(batchId: string | undefined, developer?: string): boolean {
    if (!batchId) return false;
    if (!developer) return false;
    const devKey = this.devHash(developer);
    return this.getDedupSet(devKey).has(batchId);
  }

  saveBatch(batch: StoredBatch): SaveResult {
    const devKey = this.devHash(batch.developer);

    // Generate batchId if not provided
    const batchId = batch.batchId ?? createHash("sha256")
      .update(`${batch.developer}:${batch.shippedAt}:${batch.entries.length}:${Date.now()}`)
      .digest("hex")
      .slice(0, 16);

    // Per-developer dedup
    if (this.getDedupSet(devKey).has(batchId)) {
      return { entryCount: 0, filePath: "", duplicate: true };
    }

    // Parse date for partitioning
    const date = new Date(batch.shippedAt || batch.receivedAt);
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, "0");
    const day = String(date.getUTCDate()).padStart(2, "0");

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

    // Per-developer append-only dedup record
    this.recordBatchId(batchId, partitionDir, devKey);

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
