"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useBICP } from "@/lib/bicp-context";

export interface ConnectionSummary {
  name: string;
  isActive: boolean;
  dialect: string | null;
}

interface ConnectionsListResult {
  connections: ConnectionSummary[];
  activeConnection: string | null;
}

interface ConnectionContextValue {
  connections: ConnectionSummary[];
  activeConnection: string | null;
  isLoading: boolean;
  hasLoaded: boolean;
  error: string | null;
  refreshConnections: () => Promise<void>;
  switchConnection: (name: string) => Promise<void>;
}

const ConnectionContext = createContext<ConnectionContextValue | null>(null);

export function ConnectionProvider({ children }: { children: ReactNode }) {
  const { isInitialized, call } = useBICP();
  const [connections, setConnections] = useState<ConnectionSummary[]>([]);
  const [activeConnection, setActiveConnection] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshConnections = useCallback(async () => {
    if (!isInitialized) {
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const result = await call<ConnectionsListResult>("connections/list", {});
      setConnections(result.connections);
      setActiveConnection(result.activeConnection);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load connections");
    } finally {
      setIsLoading(false);
      setHasLoaded(true);
    }
  }, [isInitialized, call]);

  const switchConnection = useCallback(
    async (name: string) => {
      if (!isInitialized || name === activeConnection) {
        return;
      }

      setIsLoading(true);
      setError(null);
      try {
        await call("connections/switch", { name });
        setActiveConnection(name);
        await refreshConnections();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to switch connection");
      } finally {
        setIsLoading(false);
      }
    },
    [isInitialized, activeConnection, call, refreshConnections],
  );

  useEffect(() => {
    refreshConnections();
  }, [refreshConnections]);

  const value = useMemo(
    () => ({
      connections,
      activeConnection,
      isLoading,
      hasLoaded,
      error,
      refreshConnections,
      switchConnection,
    }),
    [
      connections,
      activeConnection,
      isLoading,
      hasLoaded,
      error,
      refreshConnections,
      switchConnection,
    ],
  );

  return <ConnectionContext.Provider value={value}>{children}</ConnectionContext.Provider>;
}

export function useConnections(): ConnectionContextValue {
  const context = useContext(ConnectionContext);
  if (!context) {
    throw new Error("useConnections must be used within ConnectionProvider");
  }
  return context;
}
