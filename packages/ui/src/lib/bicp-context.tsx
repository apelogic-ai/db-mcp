"use client";

import {
  createContext,
  useContext,
  useCallback,
  ReactNode,
} from "react";

interface BICPContextValue {
  /** Always true — REST transport needs no initialization handshake. */
  isInitialized: true;
  call: <T = unknown>(
    method: string,
    params?: Record<string, unknown>
  ) => Promise<T>;
}

const BICPContext = createContext<BICPContextValue | null>(null);

interface BICPProviderProps {
  children: ReactNode;
}

export function BICPProvider({ children }: BICPProviderProps) {
  const call = useCallback(
    async <T = unknown>(
      method: string,
      params?: Record<string, unknown>
    ): Promise<T> => {
      const response = await fetch(`/api/${method}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: params ? JSON.stringify(params) : undefined,
      });
      if (!response.ok) {
        throw new Error(`API error: ${response.status} ${response.statusText}`);
      }
      return response.json() as Promise<T>;
    },
    []
  );

  return (
    <BICPContext.Provider value={{ isInitialized: true, call }}>
      {children}
    </BICPContext.Provider>
  );
}

export function useBICP(): BICPContextValue {
  const context = useContext(BICPContext);
  if (!context) {
    throw new Error("useBICP must be used within a BICPProvider");
  }
  return context;
}
