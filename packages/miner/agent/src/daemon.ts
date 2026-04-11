/**
 * Daemon — continuous polling loop for trace collection.
 * Discovers sources, processes new entries, ships via the Shipper.
 */

import { discoverTraceSources } from "./discover";
import { Shipper, type ShippedBatch } from "./shipper";

export interface DaemonConfig {
  claudeDir: string;
  codexDir: string;
  cursorDir: string;
  stateDir: string;
  pollIntervalMs: number;
  redactSecrets: boolean;
  developer?: string;
  machine?: string;
  onShip: (batch: ShippedBatch) => Promise<void>;
  onProgress?: (message: string) => void;
}

export class Daemon {
  private config: DaemonConfig;
  private shipper: Shipper;
  private progress: (msg: string) => void;

  constructor(config: DaemonConfig) {
    this.config = config;
    this.progress = config.onProgress ?? (() => {});
    this.shipper = new Shipper({
      developer: config.developer,
      machine: config.machine,
      stateDir: config.stateDir,
      redactSecrets: config.redactSecrets,
      ship: config.onShip,
    });
  }

  /**
   * Run one poll cycle: discover sources, process new entries.
   */
  async pollOnce(): Promise<void> {
    const sources = discoverTraceSources({
      claudeCodeDir: this.config.claudeDir,
      codexDir: this.config.codexDir,
      cursorDir: this.config.cursorDir,
    });

    let shipped = 0;
    for (const source of sources) {
      for (const file of source.files) {
        if (file.endsWith(".vscdb")) continue;
        const ok = await this.shipper.processFile(file, source.agent, source.project);
        if (ok) shipped++;
      }
    }

    if (shipped > 0) {
      this.progress(`Shipped ${shipped} batch(es) from ${sources.length} source(s)`);
    }
  }

  /**
   * Start the continuous polling loop.
   */
  async run(): Promise<void> {
    this.progress("Starting daemon...");
    this.progress(`Developer: ${this.shipper.developer}`);
    this.progress(`Machine: ${this.shipper.machine}`);
    this.progress(`Poll interval: ${this.config.pollIntervalMs}ms`);

    // Initial poll
    await this.pollOnce();

    // Continuous polling
    setInterval(async () => {
      await this.pollOnce();
    }, this.config.pollIntervalMs);

    // Keep alive
    await new Promise(() => {});
  }
}
