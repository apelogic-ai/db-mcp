import { Readable } from "node:stream";

export const parseNdjsonStream = (
  input: Readable,
  onMessage: (msg: unknown) => void,
  onError: (err: Error) => void,
): void => {
  let buffer = "";
  input.on("data", (chunk: Buffer | string) => {
    buffer += chunk.toString();
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim() === "") continue;
      try {
        onMessage(JSON.parse(line));
      } catch {
        onError(new Error(`Invalid NDJSON: ${line}`));
      }
    }
  });
};
