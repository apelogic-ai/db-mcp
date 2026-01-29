"use client";

import { useEffect, useState, useCallback } from "react";
import { useBICP } from "@/lib/bicp-context";

interface Connection {
  name: string;
  isActive: boolean;
  dialect: string | null;
}

interface ConnectionsListResult {
  connections: Connection[];
  activeConnection: string | null;
}

export function ConnectionSelector() {
  const { isInitialized, call } = useBICP();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);

  const fetchConnections = useCallback(async () => {
    try {
      const result = await call<ConnectionsListResult>("connections/list", {});
      setConnections(result.connections);
      setActive(result.activeConnection);
    } catch {
      // Silently handle — nav shouldn't break if this fails
    }
  }, [call]);

  useEffect(() => {
    if (isInitialized) {
      fetchConnections();
    }
  }, [isInitialized, fetchConnections]);

  const handleSwitch = async (name: string) => {
    if (name === active || switching) return;
    setSwitching(true);
    try {
      await call("connections/switch", { name });
      setActive(name);
      // Reload the page to pick up the new connection context
      window.location.reload();
    } catch {
      // ignore
    } finally {
      setSwitching(false);
    }
  };

  if (!isInitialized || connections.length === 0) {
    return null;
  }

  return (
    <select
      className="h-8 rounded-md bg-gray-900 border border-gray-700 text-sm text-gray-300 px-2 pr-7 appearance-none cursor-pointer hover:border-gray-600 transition-colors"
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 6px center",
      }}
      value={active || ""}
      onChange={(e) => handleSwitch(e.target.value)}
      disabled={switching}
    >
      {connections.map((conn) => (
        <option key={conn.name} value={conn.name}>
          {conn.name}
          {conn.dialect ? ` (${conn.dialect})` : ""}
        </option>
      ))}
    </select>
  );
}
