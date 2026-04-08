/**
 * HTTP shipper — POSTs batches to the centralized ingestor API.
 */

import type { ShippedBatch } from "./shipper";

export interface HttpShipperConfig {
  endpoint: string;
  apiKey?: string;
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
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (config.apiKey) {
      headers["Authorization"] = `Bearer ${config.apiKey}`;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(config.endpoint, {
        method: "POST",
        headers,
        body: JSON.stringify(batch),
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
