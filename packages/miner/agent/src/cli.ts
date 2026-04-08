#!/usr/bin/env bun
/**
 * miner-agent — local daemon for AI trace collection.
 *
 * Commands:
 *   miner-agent scan      One-shot scan of all trace sources
 *   miner-agent status    Show discovered sources and counts
 *   miner-agent watch     Daemon mode — continuous scanning
 *   miner-agent ship      Ship pending batches to ingestor
 */

import { Command } from "commander";
import { homedir } from "node:os";
import { join } from "node:path";
import { discoverTraceSources, type TraceSource } from "./discover";
import { Shipper, type ShippedBatch } from "./shipper";
import { createHttpShipper } from "./http-shipper";
import { generateKeypair, loadKeypair } from "./identity";

const DEFAULT_STATE_DIR = join(homedir(), ".miner");
const DEFAULT_CLAUDE_DIR = join(homedir(), ".claude");
const DEFAULT_CODEX_DIR = join(homedir(), ".codex");
const DEFAULT_CURSOR_DIR = (() => {
  if (process.platform === "darwin") {
    return join(homedir(), "Library", "Application Support", "Cursor");
  }
  if (process.platform === "win32") {
    return join(process.env.APPDATA ?? "", "Cursor");
  }
  return join(homedir(), ".config", "Cursor");
})();

interface ScanOpts {
  claudeDir: string;
  codexDir: string;
  cursorDir: string;
  stateDir: string;
  redactSecrets: boolean;
  dryRun: boolean;
  developer?: string;
  endpoint?: string;
  apiKey?: string;
}

async function scanAction(opts: ScanOpts): Promise<void> {
  const sources = discoverTraceSources({
    claudeCodeDir: opts.claudeDir,
    codexDir: opts.codexDir,
    cursorDir: opts.cursorDir,
  });

  if (sources.length === 0) {
    console.log("No trace sources found.");
    return;
  }

  console.log(`Discovered ${sources.length} source(s):`);
  for (const s of sources) {
    console.log(`  ${s.agent} / ${s.project} — ${s.files.length} file(s)`);
  }

  if (opts.dryRun) {
    console.log("\n(dry run — not shipping)");

    // Still count entries per source
    let totalEntries = 0;
    for (const s of sources) {
      for (const f of s.files) {
        if (f.endsWith(".vscdb")) {
          // Cursor SQLite — count composerData keys
          try {
            const Database = require("better-sqlite3");
            const db = new Database(f, { readonly: true });
            const row = db.prepare(
              "SELECT COUNT(*) as cnt FROM cursorDiskKV WHERE key LIKE 'composerData:%'",
            ).get() as { cnt: number };
            totalEntries += row.cnt;
            db.close();
          } catch { /* skip */ }
        } else {
          // JSONL — count lines
          const { readFileSync } = require("node:fs");
          const content = readFileSync(f, "utf-8");
          totalEntries += content.split("\n").filter((l: string) => l.trim()).length;
        }
      }
    }
    console.log(`Total entries across all sources: ${totalEntries}`);
    return;
  }

  // Ensure keypair exists
  generateKeypair(opts.stateDir);
  const keypair = loadKeypair(opts.stateDir) ?? undefined;

  // Set up shipping — HTTP if endpoint configured, local logging otherwise
  const shipped: ShippedBatch[] = [];
  const shipFn = opts.endpoint
    ? createHttpShipper({
        endpoint: opts.endpoint,
        apiKey: opts.apiKey,
        keypair,
      })
    : async (batch: ShippedBatch) => { shipped.push(batch); };

  const shipper = new Shipper({
    developer: opts.developer,
    stateDir: opts.stateDir,
    redactSecrets: opts.redactSecrets,
    ship: shipFn,
  });

  console.log(`\nDeveloper: ${shipper.developer}`);
  console.log(`Machine: ${shipper.machine}`);
  if (opts.endpoint) {
    console.log(`Endpoint: ${opts.endpoint}`);
  }
  if (keypair) {
    console.log(`Signing: Ed25519 keypair loaded`);
  }
  console.log();

  let batchCount = 0;
  let entryCount = 0;
  let failCount = 0;

  for (const source of sources) {
    for (const file of source.files) {
      if (file.endsWith(".vscdb")) {
        console.log(`  [skip] ${source.agent}/${source.project}: SQLite shipping not yet wired`);
        continue;
      }
      const ok = await shipper.processFile(file, source.agent, source.project);
      if (ok) {
        batchCount++;
      }
    }
  }

  if (opts.endpoint) {
    console.log(`Shipped: ${batchCount} batch(es) to ${opts.endpoint}`);
    if (failCount > 0) {
      console.log(`  ${failCount} batch(es) failed — will retry on next scan`);
    }
  } else {
    const totalEntries = shipped.reduce((sum, b) => sum + b.entries.length, 0);
    console.log(`Scanned: ${shipped.length} batch(es), ${totalEntries} new entries`);
    if (shipped.length > 0) {
      console.log("Batches (no endpoint configured — local only):");
      for (const b of shipped) {
        console.log(`  ${b.agent}/${b.project}: ${b.entries.length} entries`);
      }
    }
  }
}

interface StatusOpts {
  claudeDir: string;
  codexDir: string;
  cursorDir: string;
  stateDir: string;
}

function statusAction(opts: StatusOpts): void {
  const sources = discoverTraceSources({
    claudeCodeDir: opts.claudeDir,
    codexDir: opts.codexDir,
    cursorDir: opts.cursorDir,
  });

  console.log(`Trace sources: ${sources.length}`);
  if (sources.length === 0) {
    console.log("  (none found — check agent directories)");
    return;
  }

  for (const s of sources) {
    const fileDesc = s.files[0]?.endsWith(".vscdb") ? "database(s)" : "file(s)";
    console.log(`  ${s.agent} / ${s.project}: ${s.files.length} ${fileDesc}`);
  }

  // Show shipper state
  const { existsSync, readFileSync } = require("node:fs");
  const cursorFile = join(opts.stateDir, "shipper-cursors.json");
  if (existsSync(cursorFile)) {
    const cursors = JSON.parse(readFileSync(cursorFile, "utf-8"));
    const tracked = Object.keys(cursors).length;
    console.log(`\nShipper: tracking ${tracked} file(s)`);
  } else {
    console.log("\nShipper: no state yet (run scan first)");
  }
}

// --- CLI wiring ---

const program = new Command();

program
  .name("miner-agent")
  .description("Local agent for AI trace collection and shipping")
  .version("0.1.0");

program
  .command("scan")
  .description("One-shot scan of all trace sources")
  .option("--claude-dir <path>", "Claude Code directory", DEFAULT_CLAUDE_DIR)
  .option("--codex-dir <path>", "Codex directory", DEFAULT_CODEX_DIR)
  .option("--cursor-dir <path>", "Cursor directory", DEFAULT_CURSOR_DIR)
  .option("--state-dir <path>", "State directory for cursors", DEFAULT_STATE_DIR)
  .option("--no-redact-secrets", "Disable secret redaction")
  .option("--dry-run", "Discover and count without shipping", false)
  .option("--developer <id>", "Developer identity override")
  .option("--endpoint <url>", "Ingestor endpoint URL (e.g. http://localhost:19900/api/ingest)")
  .option("--api-key <key>", "API key for ingestor auth")
  .action(scanAction);

program
  .command("status")
  .description("Show discovered trace sources and shipper state")
  .option("--claude-dir <path>", "Claude Code directory", DEFAULT_CLAUDE_DIR)
  .option("--codex-dir <path>", "Codex directory", DEFAULT_CODEX_DIR)
  .option("--cursor-dir <path>", "Cursor directory", DEFAULT_CURSOR_DIR)
  .option("--state-dir <path>", "State directory", DEFAULT_STATE_DIR)
  .action(statusAction);

program.parse();
