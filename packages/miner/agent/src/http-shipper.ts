/**
 * HTTP shipper — POSTs batches to the centralized ingestor API.
 */

import type { ShippedBatch } from "./shipper";
import type { Keypair } from "./identity";
import { signPayload, getPublicKeyFingerprint } from "./identity";

export interface HttpShipperConfig {
  endpoint: string;
  apiKey?: string;
  keypair?: Keypair;
  timeoutMs?: number;
}

/**
 * Create a ship function that POSTs batches to the ingestor endpoint.
 */
export function createHttpShipper(
  config: HttpShipperConfig,
): (batch: ShippedBatch) => Promise<void> {
  const timeout = config.timeoutMs ?? 30_000;

  return async (batch: ShippedBatch): Promise<void> => {
    const body = JSON.stringify(batch);
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (config.apiKey) {
      headers["Authorization"] = `Bearer ${config.apiKey}`;
    }
    if (config.keypair) {
      headers["X-Miner-Signature"] = signPayload(body, config.keypair);
      headers["X-Miner-Key-Fingerprint"] = getPublicKeyFingerprint(
        config.keypair.publicKeyPem,
      );
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(config.endpoint, {
        method: "POST",
        headers,
        body,
        signal: controller.signal,
      });

      if (!response.ok) {
        const body = await response.text().catch(() => "");
        throw new Error(
          `Ingestor returned ${response.status}: ${body.slice(0, 200)}`,
        );
      }
    } finally {
      clearTimeout(timer);
    }
  };
}
