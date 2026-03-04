import type { ConnectArgs } from "./types";

export const parseConnectArgsFromUrl = (
  url: string,
): ConnectArgs | undefined => {
  try {
    const parsed = new URL(url);
    const params = parsed.searchParams;
    const httpScheme = params.get("http_scheme") ?? params.get("httpScheme");
    const verifyRaw = params.get("verify");
    const connectArgs: ConnectArgs = {};

    if (httpScheme) connectArgs.http_scheme = httpScheme;
    if (verifyRaw !== null) {
      const normalized = verifyRaw.trim().toLowerCase();
      connectArgs.verify = !["false", "0", "no", "off"].includes(normalized);
    }

    return Object.keys(connectArgs).length ? connectArgs : undefined;
  } catch {
    return undefined;
  }
};

export const maskDatabaseUrl = (url: string): string => {
  try {
    const match = url.match(/^(\w+):\/\/([^:]+):([^@]+)@(.+)$/);
    if (match) {
      const [, protocol, user, , rest] = match;
      return `${protocol}://${user}:****@${rest}`;
    }
    return url;
  } catch {
    return url;
  }
};
